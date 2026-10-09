import os
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from abc import ABC, abstractmethod

logger = logging.getLogger("chennalink.repository")

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

class BaseRepository(ABC):
    @abstractmethod
    def init_schema(self) -> None:
        pass

    @abstractmethod
    def get_session(self, session_code_or_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def create_session(
        self,
        session_code: str,
        host_device_id: str,
        host_display_name: str,
        host_email: str = "",
        host_device_type: str = "cli"
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        pass

    @abstractmethod
    def get_participants(self, session_id: str) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_participant(self, session_id: str, device_id_or_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def join_session(
        self,
        session_code: str,
        device_id: str,
        display_name: str,
        email: str = "",
        device_type: str = "cli",
        active_count: int = 0,
        max_limit: int = 4
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        pass

    @abstractmethod
    def end_session(self, session_code: str, device_id: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def update_participant_status(self, session_id: str, device_id: str, status: str) -> None:
        pass

    @abstractmethod
    def save_message(
        self,
        session_id: str,
        sender_device_id: str,
        client_message_id: str,
        message_type: str,
        content: str,
        metadata: Dict[str, Any],
        recipient_device_id: Optional[str] = None,
        delivery_status: str = "stored"
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    def update_message_delivery(self, session_id: str, client_message_id: str, delivery_status: str) -> None:
        pass

    @abstractmethod
    def get_history(
        self,
        session_code_or_id: str,
        device_id: str,
        limit: int = 50,
        offset: int = 0,
        search: Optional[str] = None
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_message(self, session_code_or_id: str, message_id: str, device_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def delete_message(self, session_code_or_id: str, message_id: str, device_id: str) -> bool:
        pass

    @abstractmethod
    def save_file_transfer(
        self,
        session_id: str,
        sender_device_id: str,
        file_name: str,
        size_bytes: int,
        sha256: str,
        storage_path: str,
        storage_bucket: str = "chennalink-files",
        content_type: str = "application/octet-stream",
        message_id: Optional[str] = None,
        transfer_status: str = "completed"
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_file_transfer(self, session_id: str, identifier: str) -> Optional[Dict[str, Any]]:
        pass

    def create_file_transfer(
        self,
        session_id: str,
        sender_device_id: str,
        file_name: str,
        size_bytes: int,
        sha256: str,
        storage_path: str,
        storage_bucket: str = "chennalink-files",
        content_type: str = "application/octet-stream",
        message_id: Optional[str] = None,
        transfer_status: str = "completed"
    ) -> Dict[str, Any]:
        return self.save_file_transfer(
            session_id=session_id,
            sender_device_id=sender_device_id,
            file_name=file_name,
            size_bytes=size_bytes,
            sha256=sha256,
            storage_path=storage_path,
            storage_bucket=storage_bucket,
            content_type=content_type,
            message_id=message_id,
            transfer_status=transfer_status
        )


# =====================================================================
# SQL SCHEMA DEFINITIONS (PostgreSQL & SQLite compatible)
# =====================================================================

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    session_code TEXT NOT NULL UNIQUE,
    host_device_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'waiting' CHECK (status IN ('waiting', 'active', 'ended')),
    max_participants INTEGER NOT NULL DEFAULT 4 CHECK (max_participants BETWEEN 2 AND 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS participants (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    device_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'participant' CHECK (role IN ('host', 'participant')),
    status TEXT NOT NULL DEFAULT 'disconnected' CHECK (status IN ('connected', 'disconnected')),
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (session_id, device_id)
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    sender_device_id TEXT NOT NULL,
    recipient_device_id TEXT,
    client_message_id TEXT NOT NULL,
    message_type TEXT NOT NULL CHECK (message_type IN ('text', 'code', 'file')),
    content TEXT NOT NULL DEFAULT '',
    metadata TEXT NOT NULL DEFAULT '{}',
    delivery_status TEXT NOT NULL DEFAULT 'stored' CHECK (delivery_status IN ('stored', 'sent', 'delivered', 'failed')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (session_id, sender_device_id, client_message_id)
);

CREATE TABLE IF NOT EXISTS file_transfers (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    message_id TEXT REFERENCES messages(id) ON DELETE SET NULL,
    sender_device_id TEXT NOT NULL,
    file_name TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
    size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
    sha256 TEXT,
    storage_bucket TEXT NOT NULL DEFAULT 'chennalink-files',
    storage_path TEXT NOT NULL,
    transfer_status TEXT NOT NULL DEFAULT 'pending' CHECK (transfer_status IN ('pending', 'uploading', 'completed', 'failed')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    UNIQUE (storage_bucket, storage_path)
);
"""

PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS public.sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_code TEXT NOT NULL UNIQUE,
    host_device_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'waiting' CHECK (status IN ('waiting', 'active', 'ended')),
    max_participants SMALLINT NOT NULL DEFAULT 4 CHECK (max_participants BETWEEN 2 AND 4),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS public.participants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES public.sessions(id) ON DELETE CASCADE,
    device_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'participant' CHECK (role IN ('host', 'participant')),
    status TEXT NOT NULL DEFAULT 'disconnected' CHECK (status IN ('connected', 'disconnected')),
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (session_id, device_id)
);

CREATE TABLE IF NOT EXISTS public.messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES public.sessions(id) ON DELETE CASCADE,
    sender_device_id TEXT NOT NULL,
    recipient_device_id TEXT,
    client_message_id TEXT NOT NULL,
    message_type TEXT NOT NULL CHECK (message_type IN ('text', 'code', 'file')),
    content TEXT NOT NULL DEFAULT '',
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    delivery_status TEXT NOT NULL DEFAULT 'stored' CHECK (delivery_status IN ('stored', 'sent', 'delivered', 'failed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (session_id, sender_device_id, client_message_id)
);

CREATE TABLE IF NOT EXISTS public.file_transfers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES public.sessions(id) ON DELETE CASCADE,
    message_id UUID REFERENCES public.messages(id) ON DELETE SET NULL,
    sender_device_id TEXT NOT NULL,
    file_name TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
    size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
    sha256 TEXT,
    storage_bucket TEXT NOT NULL DEFAULT 'chennalink-files',
    storage_path TEXT NOT NULL,
    transfer_status TEXT NOT NULL DEFAULT 'pending' CHECK (transfer_status IN ('pending', 'uploading', 'completed', 'failed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    UNIQUE (storage_bucket, storage_path)
);
"""


# =====================================================================
# SQLITE REPOSITORY (Local / Test / Offline Fallback)
# =====================================================================

class SqliteRepository(BaseRepository):
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.path.join(os.path.dirname(__file__), "chennalink.db")
        self.init_schema()

    def _get_conn(self):
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self) -> None:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            conn.executescript(SQLITE_SCHEMA)
            
            # Check existing columns in sessions table
            cursor.execute("PRAGMA table_info(sessions)")
            s_cols = [c[1] for c in cursor.fetchall()]
            if "host_device_id" not in s_cols:
                cursor.execute("ALTER TABLE sessions ADD COLUMN host_device_id TEXT")
                if "created_by" in s_cols:
                    cursor.execute("UPDATE sessions SET host_device_id = created_by WHERE host_device_id IS NULL")
            if "created_by" not in s_cols:
                cursor.execute("ALTER TABLE sessions ADD COLUMN created_by TEXT")
                cursor.execute("UPDATE sessions SET created_by = host_device_id WHERE created_by IS NULL")
            if "max_participants" not in s_cols:
                cursor.execute("ALTER TABLE sessions ADD COLUMN max_participants INTEGER DEFAULT 4")
            if "updated_at" not in s_cols:
                cursor.execute("ALTER TABLE sessions ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
            if "ended_at" not in s_cols:
                cursor.execute("ALTER TABLE sessions ADD COLUMN ended_at TIMESTAMP")
                
            # Ensure legacy tables exist for backward compatibility with old tests
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS devices (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    device_id TEXT,
                    device_name TEXT,
                    name TEXT,
                    email TEXT,
                    device_type TEXT,
                    connected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS history (
                    owner_device_id TEXT,
                    direction TEXT,
                    id TEXT,
                    session_id TEXT,
                    sender_device_id TEXT,
                    receiver_device_id TEXT,
                    peer_name TEXT,
                    file_name TEXT,
                    language TEXT,
                    content TEXT,
                    size_bytes INTEGER,
                    sha256 TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT,
                    PRIMARY KEY (owner_device_id, id)
                )
            ''')
            conn.commit()

    def get_session(self, session_code_or_id: str) -> Optional[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM sessions WHERE id = ? OR session_code = ?",
                (session_code_or_id, session_code_or_id.upper())
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def create_session(
        self,
        session_code: str,
        host_device_id: str,
        host_display_name: str,
        host_email: str = "",
        host_device_type: str = "cli"
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        session_id = str(uuid.uuid4())
        participant_id = str(uuid.uuid4())
        session_code = session_code.upper()
        now = now_iso()

        with self._get_conn() as conn:
            cursor = conn.cursor()
            # Verify code uniqueness
            cursor.execute("SELECT id, status FROM sessions WHERE session_code = ?", (session_code,))
            existing = cursor.fetchone()
            if existing:
                from fastapi import HTTPException
                raise HTTPException(status_code=400, detail="Session code already in use")

            cursor.execute(
                """INSERT INTO sessions (id, session_code, host_device_id, created_by, status, max_participants, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'waiting', 4, ?, ?)""",
                (session_id, session_code, host_device_id, host_device_id, now, now)
            )
            cursor.execute(
                """INSERT INTO participants (id, session_id, device_id, display_name, role, status, joined_at, last_seen_at)
                   VALUES (?, ?, ?, ?, 'host', 'connected', ?, ?)""",
                (participant_id, session_id, host_device_id, host_display_name, now, now)
            )
            cursor.execute(
                """INSERT OR REPLACE INTO devices (id, session_id, device_id, device_name, name, email, device_type, connected_at, last_seen)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (participant_id, session_id, host_device_id, host_display_name, host_display_name, host_email, host_device_type, now, now)
            )
            conn.commit()

            cursor.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
            s_row = dict(cursor.fetchone())
            cursor.execute("SELECT * FROM participants WHERE id = ?", (participant_id,))
            p_row = dict(cursor.fetchone())
            return s_row, p_row

    def get_participants(self, session_id: str) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT p.*, d.device_type as d_type
                FROM participants p
                LEFT JOIN devices d ON p.id = d.id OR p.device_id = d.device_id
                WHERE p.session_id = ?
            """, (session_id,))
            res = []
            for r in cursor.fetchall():
                item = dict(r)
                if not item.get("device_type"):
                    item["device_type"] = item.get("d_type") or "cli"
                res.append(item)
            return res

    def get_participant(self, session_id: str, device_id_or_id: str) -> Optional[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM participants WHERE session_id = ? AND (device_id = ? OR id = ?)",
                (session_id, device_id_or_id, device_id_or_id)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def join_session(
        self,
        session_code: str,
        device_id: str,
        display_name: str,
        email: str = "",
        device_type: str = "cli",
        active_count: int = 0,
        max_limit: int = 4
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        from fastapi import HTTPException
        session_code = session_code.upper()
        now = now_iso()

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sessions WHERE session_code = ?", (session_code,))
            s_row = cursor.fetchone()
            if not s_row:
                raise HTTPException(status_code=404, detail="Session not found")

            session = dict(s_row)
            if session["status"] == "ended":
                raise HTTPException(status_code=400, detail="This session has ended")

            session_id = session["id"]

            # Check if participant already in session
            cursor.execute(
                "SELECT * FROM participants WHERE session_id = ? AND device_id = ?",
                (session_id, device_id)
            )
            p_row = cursor.fetchone()

            cursor.execute("SELECT COUNT(*) as count FROM participants WHERE session_id = ?", (session_id,))
            total_count = cursor.fetchone()["count"]

            if p_row:
                # Reconnecting device
                participant_id = p_row["id"]
                cursor.execute(
                    "UPDATE participants SET status = 'connected', last_seen_at = ? WHERE id = ?",
                    (now, participant_id)
                )
                conn.commit()
                cursor.execute("SELECT * FROM participants WHERE id = ?", (participant_id,))
                return session, dict(cursor.fetchone())

            # New participant join
            if active_count >= max_limit:
                raise HTTPException(status_code=403, detail="SESSION FULL")

            participant_id = str(uuid.uuid4())
            cursor.execute(
                """INSERT INTO participants (id, session_id, device_id, display_name, role, status, joined_at, last_seen_at)
                   VALUES (?, ?, ?, ?, 'participant', 'connected', ?, ?)""",
                (participant_id, session_id, device_id, display_name, now, now)
            )
            cursor.execute(
                """INSERT OR REPLACE INTO devices (id, session_id, device_id, device_name, name, email, device_type, connected_at, last_seen)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (participant_id, session_id, device_id, display_name, display_name, email, device_type, now, now)
            )

            # Check if count reached min required (2) to activate session
            if total_count + 1 >= 2 and session["status"] == "waiting":
                cursor.execute("UPDATE sessions SET status = 'active', updated_at = ? WHERE id = ?", (now, session_id))
                session["status"] = "active"

            conn.commit()
            cursor.execute("SELECT * FROM participants WHERE id = ?", (participant_id,))
            return session, dict(cursor.fetchone())

    def end_session(self, session_code: str, device_id: str) -> Dict[str, Any]:
        from fastapi import HTTPException
        session_code = session_code.upper()
        now = now_iso()

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sessions WHERE session_code = ?", (session_code,))
            s_row = cursor.fetchone()
            if not s_row:
                raise HTTPException(status_code=404, detail="Session not found")

            session = dict(s_row)
            session_id = session["id"]

            cursor.execute(
                "SELECT * FROM participants WHERE session_id = ? AND (device_id = ? OR id = ?)",
                (session_id, device_id, device_id)
            )
            dev = cursor.fetchone()
            if not dev:
                raise HTTPException(status_code=403, detail="Device not found in session")

            # Validate host permission
            if session["host_device_id"] not in [dev["id"], dev["device_id"], device_id] and dev["role"] != "host":
                raise HTTPException(status_code=403, detail="Only the session host can terminate the session")

            cursor.execute(
                "UPDATE sessions SET status = 'ended', ended_at = ?, updated_at = ? WHERE id = ?",
                (now, now, session_id)
            )
            conn.commit()
            cursor.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
            return dict(cursor.fetchone())

    def update_participant_status(self, session_id: str, device_id: str, status: str) -> None:
        now = now_iso()
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE participants SET status = ?, last_seen_at = ? WHERE session_id = ? AND (device_id = ? OR id = ?)",
                (status, now, session_id, device_id, device_id)
            )
            conn.commit()

    def save_message(
        self,
        session_id: str,
        sender_device_id: str,
        client_message_id: str,
        message_type: str,
        content: str,
        metadata: Dict[str, Any],
        recipient_device_id: Optional[str] = None,
        delivery_status: str = "stored"
    ) -> Dict[str, Any]:
        msg_id = str(uuid.uuid4())
        meta_json = json.dumps(metadata)
        now = metadata.get("created_at") or now_iso()

        with self._get_conn() as conn:
            cursor = conn.cursor()
            # Insert or replace for deduplication and idempotency
            cursor.execute(
                """INSERT OR REPLACE INTO messages
                   (id, session_id, sender_device_id, recipient_device_id, client_message_id, message_type, content, metadata, delivery_status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (msg_id, session_id, sender_device_id, recipient_device_id, client_message_id, message_type, content, meta_json, delivery_status, now)
            )

            # Sync legacy history table for backward compatibility
            peer_name = metadata.get("peer_name") or sender_device_id
            fname = metadata.get("file_name", "message.txt")
            lang = metadata.get("language", "python")
            sz = metadata.get("size_bytes", len(content.encode("utf-8")))
            sha = metadata.get("sha256", "")

            # Resolve sender aliases (canonical id and device_id)
            cursor.execute(
                "SELECT id, device_id FROM participants WHERE session_id = ? AND (id = ? OR device_id = ?)",
                (session_id, sender_device_id, sender_device_id)
            )
            sender_part = cursor.fetchone()
            sender_aliases = {sender_device_id}
            if sender_part:
                if sender_part["id"]:
                    sender_aliases.add(sender_part["id"])
                if sender_part["device_id"]:
                    sender_aliases.add(sender_part["device_id"])

            for s_owner in sender_aliases:
                cursor.execute(
                    """INSERT OR REPLACE INTO history
                       (owner_device_id, direction, id, session_id, sender_device_id, receiver_device_id, peer_name, file_name, language, content, size_bytes, sha256, created_at, status)
                       VALUES (?, 'sent', ?, ?, ?, '', ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (s_owner, client_message_id, session_id, sender_device_id, peer_name, fname, lang, content, sz, sha, now, delivery_status)
                )

            # Query all participants in session to record 'received' for non-sender peers
            cursor.execute("SELECT id, device_id FROM participants WHERE session_id = ?", (session_id,))
            all_parts = cursor.fetchall()
            for peer in all_parts:
                p_id = peer["id"]
                p_dev = peer["device_id"]
                if p_id in sender_aliases or p_dev in sender_aliases:
                    continue
                # If a specific recipient was targeted, only record for that recipient
                if recipient_device_id and recipient_device_id not in (p_id, p_dev):
                    continue

                for p_owner in set(filter(None, [p_id, p_dev])):
                    cursor.execute(
                        """INSERT OR REPLACE INTO history
                           (owner_device_id, direction, id, session_id, sender_device_id, receiver_device_id, peer_name, file_name, language, content, size_bytes, sha256, created_at, status)
                           VALUES (?, 'received', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (p_owner, client_message_id, session_id, sender_device_id, p_owner, peer_name, fname, lang, content, sz, sha, now, delivery_status)
                    )

            conn.commit()
            cursor.execute("SELECT * FROM messages WHERE session_id = ? AND sender_device_id = ? AND client_message_id = ?",
                           (session_id, sender_device_id, client_message_id))
            row = dict(cursor.fetchone())
            row["metadata"] = json.loads(row["metadata"]) if isinstance(row["metadata"], str) else row["metadata"]
            return row

    def update_message_delivery(self, session_id: str, client_message_id: str, delivery_status: str) -> None:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE messages SET delivery_status = ? WHERE session_id = ? AND (client_message_id = ? OR id = ?)",
                (delivery_status, session_id, client_message_id, client_message_id)
            )
            conn.commit()

    def get_history(
        self,
        session_code_or_id: str,
        device_id: str,
        limit: int = 50,
        offset: int = 0,
        search: Optional[str] = None
    ) -> Dict[str, Any]:
        session = self.get_session(session_code_or_id)
        if not session:
            return {"items": [], "total": 0, "limit": limit, "offset": offset}

        session_id = session["id"]
        # Find device alias IDs
        participant = self.get_participant(session_id, device_id)
        dev_ids = [device_id]
        if participant:
            dev_ids = list(set([participant["id"], participant["device_id"], device_id]))

        dev_placeholders = ",".join(["?"] * len(dev_ids))

        with self._get_conn() as conn:
            cursor = conn.cursor()
            # Allowed messages: user is sender, OR recipient is NULL (broadcast to room), OR user is recipient
            where_sql = f"""session_id = ? AND (
                sender_device_id IN ({dev_placeholders})
                OR recipient_device_id IS NULL
                OR recipient_device_id IN ({dev_placeholders})
            )"""
            params: List[Any] = [session_id] + dev_ids + dev_ids

            if search:
                where_sql += " AND (metadata LIKE ? OR content LIKE ?)"
                params.extend([f"%{search}%", f"%{search}%"])

            # Total count
            cursor.execute(f"SELECT COUNT(*) as count FROM messages WHERE {where_sql}", params)
            total = cursor.fetchone()["count"]

            # Query items
            query_sql = f"""SELECT * FROM messages WHERE {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?"""
            cursor.execute(query_sql, params + [limit, offset])
            rows = cursor.fetchall()

            items = []
            for r in rows:
                row = dict(r)
                meta = json.loads(row["metadata"]) if isinstance(row["metadata"], str) else (row["metadata"] or {})
                direction = "sent" if row["sender_device_id"] in dev_ids else "received"
                
                # Format to match Chennalink's exact history schema
                items.append({
                    "id": row["client_message_id"] or row["id"],
                    "session_id": row["session_id"],
                    "sender_device_id": row["sender_device_id"],
                    "peer_name": meta.get("peer_name") or row["sender_device_id"],
                    "file_name": meta.get("file_name", "message.txt"),
                    "language": meta.get("language", "python"),
                    "content": row["content"],
                    "created_at": row["created_at"],
                    "status": row["delivery_status"],
                    "direction": direction,
                    "size_bytes": meta.get("size_bytes", len(row["content"].encode("utf-8"))),
                    "sha256": meta.get("sha256", ""),
                    "preview": row["content"][:200]
                })

            return {
                "items": items,
                "total": total,
                "limit": limit,
                "offset": offset
            }

    def get_message(self, session_code_or_id: str, message_id: str, device_id: str) -> Optional[Dict[str, Any]]:
        session = self.get_session(session_code_or_id)
        if not session:
            return None
        session_id = session["id"]

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM messages WHERE session_id = ? AND (id = ? OR client_message_id = ?)",
                (session_id, message_id, message_id)
            )
            r = cursor.fetchone()
            if not r:
                return None
            row = dict(r)
            meta = json.loads(row["metadata"]) if isinstance(row["metadata"], str) else (row["metadata"] or {})
            direction = "sent" if row["sender_device_id"] == device_id else "received"
            return {
                "id": row["client_message_id"] or row["id"],
                "session_id": row["session_id"],
                "sender_device_id": row["sender_device_id"],
                "peer_name": meta.get("peer_name") or row["sender_device_id"],
                "file_name": meta.get("file_name", "message.txt"),
                "language": meta.get("language", "python"),
                "content": row["content"],
                "created_at": row["created_at"],
                "status": row["delivery_status"],
                "direction": direction,
                "size_bytes": meta.get("size_bytes", len(row["content"].encode("utf-8"))),
                "sha256": meta.get("sha256", ""),
                "preview": row["content"][:200]
            }

    def delete_message(self, session_code_or_id: str, message_id: str, device_id: str) -> bool:
        session = self.get_session(session_code_or_id)
        if not session:
            return False
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM messages WHERE session_id = ? AND (id = ? OR client_message_id = ?)",
                (session["id"], message_id, message_id)
            )
            conn.commit()
            return cursor.rowcount > 0

    def save_file_transfer(
        self,
        session_id: str,
        sender_device_id: str,
        file_name: str,
        size_bytes: int,
        sha256: str,
        storage_path: str,
        storage_bucket: str = "chennalink-files",
        content_type: str = "application/octet-stream",
        message_id: Optional[str] = None,
        transfer_status: str = "completed"
    ) -> Dict[str, Any]:
        transfer_id = str(uuid.uuid4())
        now = now_iso()
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT OR REPLACE INTO file_transfers
                   (id, session_id, message_id, sender_device_id, file_name, content_type, size_bytes, sha256, storage_bucket, storage_path, transfer_status, created_at, completed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (transfer_id, session_id, message_id, sender_device_id, file_name, content_type, size_bytes, sha256, storage_bucket, storage_path, transfer_status, now, now)
            )
            conn.commit()
            cursor.execute("SELECT * FROM file_transfers WHERE id = ?", (transfer_id,))
            return dict(cursor.fetchone())

    def get_file_transfer(self, session_id: str, identifier: str) -> Optional[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM file_transfers WHERE session_id = ? AND (id = ? OR message_id = ? OR storage_path = ?)",
                (session_id, identifier, identifier, identifier)
            )
            r = cursor.fetchone()
            return dict(r) if r else None


# =====================================================================
# POSTGRESQL REPOSITORY (Direct / Connection Pooling / Supabase PG)
# =====================================================================

class PostgresRepository(BaseRepository):
    def __init__(self, database_url: str):
        # Sanitize connection string (strip Prisma-specific pgbouncer query param for psycopg compatibility)
        cleaned_url = database_url
        if "pgbouncer=true" in cleaned_url:
            cleaned_url = cleaned_url.replace("?pgbouncer=true&", "?").replace("&pgbouncer=true", "").replace("?pgbouncer=true", "")
        self.database_url = cleaned_url

        from psycopg_pool import ConnectionPool
        self.pool = ConnectionPool(
            conninfo=self.database_url,
            min_size=1,
            max_size=10,
            timeout=5.0,
            open=False
        )
        self.pool.open()
        self.init_schema()

    def init_schema(self) -> None:
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(PG_SCHEMA)
            conn.commit()

    def get_session(self, session_code_or_id: str) -> Optional[Dict[str, Any]]:
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                # Support UUID or 6-char session code
                cur.execute(
                    """SELECT id, session_code, host_device_id, status, max_participants, created_at, updated_at, ended_at
                       FROM public.sessions
                       WHERE id::text = %s OR session_code = %s""",
                    (session_code_or_id, session_code_or_id.upper())
                )
                row = cur.fetchone()
                if not row:
                    return None
                cols = [desc[0] for desc in cur.description]
                res = dict(zip(cols, row))
                res["id"] = str(res["id"])
                return res

    def create_session(
        self,
        session_code: str,
        host_device_id: str,
        host_display_name: str,
        host_email: str = "",
        host_device_type: str = "cli"
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        from fastapi import HTTPException
        session_code = session_code.upper()

        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM public.sessions WHERE session_code = %s", (session_code,))
                if cur.fetchone():
                    raise HTTPException(status_code=400, detail="Session code already in use")

                cur.execute(
                    """INSERT INTO public.sessions (session_code, host_device_id, status, max_participants)
                       VALUES (%s, %s, 'waiting', 4)
                       RETURNING id, session_code, host_device_id, status, max_participants, created_at, updated_at, ended_at""",
                    (session_code, host_device_id)
                )
                s_row = cur.fetchone()
                s_cols = [desc[0] for desc in cur.description]
                session_dict = dict(zip(s_cols, s_row))
                session_dict["id"] = str(session_dict["id"])
                session_id = session_dict["id"]

                cur.execute(
                    """INSERT INTO public.participants (session_id, device_id, display_name, role, status)
                       VALUES (%s, %s, %s, 'host', 'connected')
                       RETURNING id, session_id, device_id, display_name, role, status, joined_at, last_seen_at""",
                    (session_id, host_device_id, host_display_name)
                )
                p_row = cur.fetchone()
                p_cols = [desc[0] for desc in cur.description]
                participant_dict = dict(zip(p_cols, p_row))
                participant_dict["id"] = str(participant_dict["id"])
                participant_dict["session_id"] = str(participant_dict["session_id"])
            conn.commit()
            return session_dict, participant_dict

    def get_participants(self, session_id: str) -> List[Dict[str, Any]]:
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, session_id, device_id, display_name, role, status, joined_at, last_seen_at FROM public.participants WHERE session_id = %s",
                    (session_id,)
                )
                cols = [desc[0] for desc in cur.description]
                res = []
                for row in cur.fetchall():
                    item = dict(zip(cols, row))
                    item["id"] = str(item["id"])
                    item["session_id"] = str(item["session_id"])
                    res.append(item)
                return res

    def get_participant(self, session_id: str, device_id_or_id: str) -> Optional[Dict[str, Any]]:
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, session_id, device_id, display_name, role, status, joined_at, last_seen_at
                       FROM public.participants
                       WHERE session_id = %s AND (device_id = %s OR id::text = %s)""",
                    (session_id, device_id_or_id, device_id_or_id)
                )
                row = cur.fetchone()
                if not row:
                    return None
                cols = [desc[0] for desc in cur.description]
                res = dict(zip(cols, row))
                res["id"] = str(res["id"])
                res["session_id"] = str(res["session_id"])
                return res

    def join_session(
        self,
        session_code: str,
        device_id: str,
        display_name: str,
        email: str = "",
        device_type: str = "cli",
        active_count: int = 0,
        max_limit: int = 4
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        from fastapi import HTTPException
        session_code = session_code.upper()

        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM public.sessions WHERE session_code = %s FOR UPDATE", (session_code,))
                s_row = cur.fetchone()
                if not s_row:
                    raise HTTPException(status_code=404, detail="Session not found")

                s_cols = [desc[0] for desc in cur.description]
                session = dict(zip(s_cols, s_row))
                session["id"] = str(session["id"])
                session_id = session["id"]

                if session["status"] == "ended":
                    raise HTTPException(status_code=400, detail="This session has ended")

                cur.execute(
                    "SELECT * FROM public.participants WHERE session_id = %s AND device_id = %s",
                    (session_id, device_id)
                )
                p_row = cur.fetchone()

                cur.execute("SELECT COUNT(*) FROM public.participants WHERE session_id = %s", (session_id,))
                total_count = cur.fetchone()[0]

                if p_row:
                    p_cols = [desc[0] for desc in cur.description]
                    participant = dict(zip(p_cols, p_row))
                    participant["id"] = str(participant["id"])
                    participant["session_id"] = str(participant["session_id"])
                    cur.execute(
                        "UPDATE public.participants SET status = 'connected', last_seen_at = NOW() WHERE id = %s",
                        (participant["id"],)
                    )
                    conn.commit()
                    return session, participant

                if active_count >= max_limit:
                    raise HTTPException(status_code=403, detail="SESSION FULL")

                cur.execute(
                    """INSERT INTO public.participants (session_id, device_id, display_name, role, status)
                       VALUES (%s, %s, %s, 'participant', 'connected')
                       RETURNING id, session_id, device_id, display_name, role, status, joined_at, last_seen_at""",
                    (session_id, device_id, display_name)
                )
                p_row = cur.fetchone()
                p_cols = [desc[0] for desc in cur.description]
                participant = dict(zip(p_cols, p_row))
                participant["id"] = str(participant["id"])
                participant["session_id"] = str(participant["session_id"])

                if total_count + 1 >= 2 and session["status"] == "waiting":
                    cur.execute("UPDATE public.sessions SET status = 'active', updated_at = NOW() WHERE id = %s", (session_id,))
                    session["status"] = "active"

            conn.commit()
            return session, participant

    def end_session(self, session_code: str, device_id: str) -> Dict[str, Any]:
        from fastapi import HTTPException
        session_code = session_code.upper()

        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM public.sessions WHERE session_code = %s FOR UPDATE", (session_code,))
                s_row = cur.fetchone()
                if not s_row:
                    raise HTTPException(status_code=404, detail="Session not found")

                s_cols = [desc[0] for desc in cur.description]
                session = dict(zip(s_cols, s_row))
                session["id"] = str(session["id"])
                session_id = session["id"]

                cur.execute(
                    "SELECT * FROM public.participants WHERE session_id = %s AND (device_id = %s OR id::text = %s)",
                    (session_id, device_id, device_id)
                )
                dev = cur.fetchone()
                if not dev:
                    raise HTTPException(status_code=403, detail="Device not found in session")

                p_cols = [desc[0] for desc in cur.description]
                dev_dict = dict(zip(p_cols, dev))

                if session["host_device_id"] not in [dev_dict["id"], dev_dict["device_id"], device_id] and dev_dict["role"] != "host":
                    raise HTTPException(status_code=403, detail="Only the session host can terminate the session")

                cur.execute(
                    "UPDATE public.sessions SET status = 'ended', ended_at = NOW(), updated_at = NOW() WHERE id = %s RETURNING *",
                    (session_id,)
                )
                updated_s = cur.fetchone()
                res = dict(zip(s_cols, updated_s))
                res["id"] = str(res["id"])
            conn.commit()
            return res

    def update_participant_status(self, session_id: str, device_id: str, status: str) -> None:
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE public.participants
                       SET status = %s, last_seen_at = NOW()
                       WHERE session_id = %s AND (device_id = %s OR id::text = %s)""",
                    (status, session_id, device_id, device_id)
                )
            conn.commit()

    def save_message(
        self,
        session_id: str,
        sender_device_id: str,
        client_message_id: str,
        message_type: str,
        content: str,
        metadata: Dict[str, Any],
        recipient_device_id: Optional[str] = None,
        delivery_status: str = "stored"
    ) -> Dict[str, Any]:
        meta_json = json.dumps(metadata)
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO public.messages
                       (session_id, sender_device_id, recipient_device_id, client_message_id, message_type, content, metadata, delivery_status)
                       VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                       ON CONFLICT (session_id, sender_device_id, client_message_id)
                       DO UPDATE SET content = EXCLUDED.content, metadata = EXCLUDED.metadata, delivery_status = EXCLUDED.delivery_status
                       RETURNING id, session_id, sender_device_id, recipient_device_id, client_message_id, message_type, content, metadata, delivery_status, created_at""",
                    (session_id, sender_device_id, recipient_device_id, client_message_id, message_type, content, meta_json, delivery_status)
                )
                row = cur.fetchone()
                cols = [desc[0] for desc in cur.description]
                res = dict(zip(cols, row))
                res["id"] = str(res["id"])
                res["session_id"] = str(res["session_id"])
            conn.commit()
            return res

    def update_message_delivery(self, session_id: str, client_message_id: str, delivery_status: str) -> None:
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE public.messages
                       SET delivery_status = %s
                       WHERE session_id = %s AND (client_message_id = %s OR id::text = %s)""",
                    (delivery_status, session_id, client_message_id, client_message_id)
                )
            conn.commit()

    def get_history(
        self,
        session_code_or_id: str,
        device_id: str,
        limit: int = 50,
        offset: int = 0,
        search: Optional[str] = None
    ) -> Dict[str, Any]:
        session = self.get_session(session_code_or_id)
        if not session:
            return {"items": [], "total": 0, "limit": limit, "offset": offset}

        session_id = session["id"]
        participant = self.get_participant(session_id, device_id)
        dev_ids = [device_id]
        if participant:
            dev_ids = list(set([participant["id"], participant["device_id"], device_id]))

        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                where_sql = """session_id = %s AND (
                    sender_device_id = ANY(%s)
                    OR recipient_device_id IS NULL
                    OR recipient_device_id = ANY(%s)
                )"""
                params: List[Any] = [session_id, dev_ids, dev_ids]

                if search:
                    where_sql += " AND (metadata::text ILIKE %s OR content ILIKE %s)"
                    params.extend([f"%{search}%", f"%{search}%"])

                cur.execute(f"SELECT COUNT(*) FROM public.messages WHERE {where_sql}", params)
                total = cur.fetchone()[0]

                cur.execute(
                    f"SELECT * FROM public.messages WHERE {where_sql} ORDER BY created_at DESC LIMIT %s OFFSET %s",
                    params + [limit, offset]
                )
                cols = [desc[0] for desc in cur.description]
                rows = cur.fetchall()

                items = []
                for r in rows:
                    row = dict(zip(cols, r))
                    row["id"] = str(row["id"])
                    row["session_id"] = str(row["session_id"])
                    meta = row["metadata"] if isinstance(row["metadata"], dict) else json.loads(row["metadata"] or "{}")
                    direction = "sent" if row["sender_device_id"] in dev_ids else "received"
                    created_str = row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else str(row["created_at"])
                    items.append({
                        "id": row["client_message_id"] or row["id"],
                        "session_id": row["session_id"],
                        "sender_device_id": row["sender_device_id"],
                        "peer_name": meta.get("peer_name") or row["sender_device_id"],
                        "file_name": meta.get("file_name", "message.txt"),
                        "language": meta.get("language", "python"),
                        "content": row["content"],
                        "created_at": created_str,
                        "status": row["delivery_status"],
                        "direction": direction,
                        "size_bytes": meta.get("size_bytes", len(row["content"].encode("utf-8"))),
                        "sha256": meta.get("sha256", ""),
                        "preview": row["content"][:200]
                    })

                return {"items": items, "total": total, "limit": limit, "offset": offset}

    def get_message(self, session_code_or_id: str, message_id: str, device_id: str) -> Optional[Dict[str, Any]]:
        session = self.get_session(session_code_or_id)
        if not session:
            return None
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM public.messages WHERE session_id = %s AND (id::text = %s OR client_message_id = %s)",
                    (session["id"], message_id, message_id)
                )
                row = cur.fetchone()
                if not row:
                    return None
                cols = [desc[0] for desc in cur.description]
                res = dict(zip(cols, row))
                res["id"] = str(res["id"])
                res["session_id"] = str(res["session_id"])
                meta = res["metadata"] if isinstance(res["metadata"], dict) else json.loads(res["metadata"] or "{}")
                direction = "sent" if res["sender_device_id"] == device_id else "received"
                created_str = res["created_at"].isoformat() if hasattr(res["created_at"], "isoformat") else str(res["created_at"])
                return {
                    "id": res["client_message_id"] or res["id"],
                    "session_id": res["session_id"],
                    "sender_device_id": res["sender_device_id"],
                    "peer_name": meta.get("peer_name") or res["sender_device_id"],
                    "file_name": meta.get("file_name", "message.txt"),
                    "language": meta.get("language", "python"),
                    "content": res["content"],
                    "created_at": created_str,
                    "status": res["delivery_status"],
                    "direction": direction,
                    "size_bytes": meta.get("size_bytes", len(res["content"].encode("utf-8"))),
                    "sha256": meta.get("sha256", ""),
                    "preview": res["content"][:200]
                }

    def delete_message(self, session_code_or_id: str, message_id: str, device_id: str) -> bool:
        session = self.get_session(session_code_or_id)
        if not session:
            return False
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM public.messages WHERE session_id = %s AND (id::text = %s OR client_message_id = %s)",
                    (session["id"], message_id, message_id)
                )
                affected = cur.rowcount
            conn.commit()
            return affected > 0

    def save_file_transfer(
        self,
        session_id: str,
        sender_device_id: str,
        file_name: str,
        size_bytes: int,
        sha256: str,
        storage_path: str,
        storage_bucket: str = "chennalink-files",
        content_type: str = "application/octet-stream",
        message_id: Optional[str] = None,
        transfer_status: str = "completed"
    ) -> Dict[str, Any]:
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO public.file_transfers
                       (session_id, message_id, sender_device_id, file_name, content_type, size_bytes, sha256, storage_bucket, storage_path, transfer_status, completed_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                       ON CONFLICT (storage_bucket, storage_path)
                       DO UPDATE SET transfer_status = EXCLUDED.transfer_status, completed_at = NOW()
                       RETURNING *""",
                    (session_id, message_id, sender_device_id, file_name, content_type, size_bytes, sha256, storage_bucket, storage_path, transfer_status)
                )
                row = cur.fetchone()
                cols = [desc[0] for desc in cur.description]
                res = dict(zip(cols, row))
                res["id"] = str(res["id"])
                res["session_id"] = str(res["session_id"])
            conn.commit()
            return res

    def get_file_transfer(self, session_id: str, identifier: str) -> Optional[Dict[str, Any]]:
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT * FROM public.file_transfers
                       WHERE session_id = %s AND (id::text = %s OR message_id::text = %s OR storage_path = %s)""",
                    (session_id, identifier, identifier, identifier)
                )
                row = cur.fetchone()
                if not row:
                    return None
                cols = [desc[0] for desc in cur.description]
                res = dict(zip(cols, row))
                res["id"] = str(res["id"])
                res["session_id"] = str(res["session_id"])
                return res


# =====================================================================
# GLOBAL REPOSITORY INSTANTIATION
# =====================================================================

_repo_instance: Optional[BaseRepository] = None

def reset_repository() -> None:
    global _repo_instance
    _repo_instance = None

def get_repository() -> BaseRepository:
    global _repo_instance
    if _repo_instance is not None:
        return _repo_instance

    from backend.config import settings
    database_url = settings.database_url or os.environ.get("DATABASE_URL")

    # Production Mode or PostgreSQL explicitly requested
    if settings.is_production() or settings.db_backend == "postgres":
        if not database_url or not database_url.startswith("postgres"):
            raise RuntimeError(
                "PRODUCTION CONFIGURATION ERROR: 'DATABASE_URL' is required for Supabase PostgreSQL. "
                "Silent local SQLite fallback is strictly prohibited in production."
            )
        try:
            logger.info("Initializing PostgresRepository via DATABASE_URL connection pool...")
            _repo_instance = PostgresRepository(database_url)
            return _repo_instance
        except Exception as e:
            logger.error(f"Failed to connect to Supabase PostgreSQL: {e}")
            raise RuntimeError(
                f"Production database connection failure: Unable to establish PostgreSQL connection pool ({e}). "
                "Local SQLite fallback is strictly prohibited in production."
            )

    # Non-production / test / development mode
    if not settings.allow_local_fallback and settings.db_backend != "sqlite":
        raise RuntimeError(
            f"Database configuration error: DB_BACKEND is set to '{settings.db_backend}' but no valid DATABASE_URL provided."
        )

    logger.warning("Non-production environment: Initializing SqliteRepository for test/dev.")
    _repo_instance = SqliteRepository()
    return _repo_instance
