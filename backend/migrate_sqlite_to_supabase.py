import os
import sys
import sqlite3
import json
import logging
import argparse
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.repository import get_repository, PostgresRepository, SqliteRepository

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("chennalink.migration")

def migrate(sqlite_db_path: str, target_repo=None):
    if not os.path.isfile(sqlite_db_path):
        logger.warning(f"No SQLite database found at {sqlite_db_path}. Nothing to migrate.")
        return {"sessions": 0, "participants": 0, "messages": 0}

    logger.info(f"Connecting to source SQLite database: {sqlite_db_path}")
    source_conn = sqlite3.connect(sqlite_db_path)
    source_conn.row_factory = sqlite3.Row
    s_cur = source_conn.cursor()

    # Verify tables
    s_cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row["name"] for row in s_cur.fetchall()]
    logger.info(f"Found source tables: {tables}")

    if target_repo is None:
        target_repo = get_repository()

    counts = {"sessions": 0, "participants": 0, "messages": 0, "file_transfers": 0}

    # 1. Migrate Sessions
    if "sessions" in tables:
        s_cur.execute("SELECT * FROM sessions")
        session_rows = s_cur.fetchall()
        logger.info(f"Found {len(session_rows)} sessions in source SQLite.")
        for row in session_rows:
            r = dict(row)
            session_id = r.get("id")
            session_code = r.get("session_code", "").upper()
            host_device_id = r.get("created_by") or r.get("host_device_id") or "UNKNOWN"
            raw_status = (r.get("status") or "waiting").lower()
            status = "active" if raw_status in ["connected", "active"] else ("ended" if raw_status == "ended" else "waiting")
            created_at = r.get("created_at") or datetime.now(timezone.utc).isoformat()

            # Insert into target
            if hasattr(target_repo, "pool"):  # Postgres
                with target_repo.pool.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """INSERT INTO public.sessions (id, session_code, host_device_id, status, max_participants, created_at, updated_at)
                               VALUES (%s, %s, %s, %s, 4, %s, %s)
                               ON CONFLICT (session_code) DO NOTHING""",
                            (session_id, session_code, host_device_id, status, created_at, created_at)
                        )
                    conn.commit()
            elif isinstance(target_repo, SqliteRepository):
                with target_repo._get_conn() as conn:
                    cur = conn.cursor()
                    cur.execute(
                        """INSERT OR IGNORE INTO sessions (id, session_code, host_device_id, status, max_participants, created_at, updated_at)
                           VALUES (?, ?, ?, ?, 4, ?, ?)""",
                        (session_id, session_code, host_device_id, status, created_at, created_at)
                    )
                    conn.commit()
            counts["sessions"] += 1

    # 2. Migrate Devices / Participants
    if "devices" in tables:
        s_cur.execute("SELECT * FROM devices")
        device_rows = s_cur.fetchall()
        logger.info(f"Found {len(device_rows)} devices in source SQLite.")
        for row in device_rows:
            r = dict(row)
            p_id = r.get("id")
            session_id = r.get("session_id")
            device_id = r.get("device_id")
            display_name = r.get("device_name") or r.get("name") or "Device"
            role = "participant"
            joined_at = r.get("connected_at") or datetime.now(timezone.utc).isoformat()
            last_seen = r.get("last_seen") or joined_at

            if hasattr(target_repo, "pool"):
                with target_repo.pool.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """INSERT INTO public.participants (id, session_id, device_id, display_name, role, status, joined_at, last_seen_at)
                               VALUES (%s, %s, %s, %s, %s, 'disconnected', %s, %s)
                               ON CONFLICT (session_id, device_id) DO NOTHING""",
                            (p_id, session_id, device_id, display_name, role, joined_at, last_seen)
                        )
                    conn.commit()
            elif isinstance(target_repo, SqliteRepository):
                with target_repo._get_conn() as conn:
                    cur = conn.cursor()
                    cur.execute(
                        """INSERT OR IGNORE INTO participants (id, session_id, device_id, display_name, role, status, joined_at, last_seen_at)
                           VALUES (?, ?, ?, ?, ?, 'disconnected', ?, ?)""",
                        (p_id, session_id, device_id, display_name, role, joined_at, last_seen)
                    )
                    cur.execute(
                        """INSERT OR REPLACE INTO devices (id, session_id, device_id, device_name, name, device_type, connected_at, last_seen)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (p_id, session_id, device_id, display_name, display_name, "cli", joined_at, last_seen)
                    )
                    conn.commit()
            counts["participants"] += 1

    # 3. Migrate History into Canonical Messages
    if "history" in tables:
        # Group by unique message ID to deduplicate the dual sent/received rows
        s_cur.execute("""SELECT id, session_id, sender_device_id, peer_name, file_name, language, content, size_bytes, sha256, created_at, status
                         FROM history GROUP BY session_id, id""")
        history_rows = s_cur.fetchall()
        logger.info(f"Found {len(history_rows)} unique history records in source SQLite.")
        for row in history_rows:
            r = dict(row)
            msg_id = r.get("id")
            session_id = r.get("session_id")
            sender_id = r.get("sender_device_id") or "REMOTE"
            content = r.get("content", "")
            meta = {
                "file_name": r.get("file_name", "message.txt"),
                "language": r.get("language", "python"),
                "peer_name": r.get("peer_name", sender_id),
                "size_bytes": r.get("size_bytes", len(content.encode("utf-8"))),
                "sha256": r.get("sha256", "")
            }
            target_repo.save_message(
                session_id=session_id,
                sender_device_id=sender_id,
                client_message_id=msg_id,
                message_type="code",
                content=content,
                metadata=meta,
                recipient_device_id=None,
                delivery_status=r.get("status") or "delivered"
            )
            counts["messages"] += 1

    source_conn.close()
    logger.info(f"Migration completed successfully! Summary: {counts}")
    return counts

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate Chennalink SQLite database to Supabase PostgreSQL")
    parser.add_argument("--db", default=os.path.join(os.path.dirname(__file__), "chennalink.db"), help="Path to sqlite db")
    args = parser.parse_args()
    migrate(args.db)
