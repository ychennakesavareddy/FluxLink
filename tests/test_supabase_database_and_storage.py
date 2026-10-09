import os
import io
import json
import uuid
import hashlib
import sqlite3
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from backend.main import app
from backend.storage import StorageService
from backend.repository import get_repository, SqliteRepository, SQLITE_SCHEMA
from backend.migrate_sqlite_to_supabase import migrate

client = TestClient(app)

@pytest.fixture
def temp_repo(tmp_path):
    db_file = str(tmp_path / "test_repo.db")
    repo = SqliteRepository(db_path=db_file)
    return repo

@pytest.fixture
def temp_storage(tmp_path):
    storage = StorageService()
    storage.local_storage_dir = str(tmp_path / "storage_local")
    return storage

# =====================================================================
# 1. STORAGE SERVICE TESTS
# =====================================================================

def test_storage_exact_byte_fidelity(temp_storage):
    """Verify private storage guarantees 100% byte fidelity without stripping."""
    python_code = """
def sample_algo(data):
    # CRITICAL: Preserve all indentation levels
    if not data:
        return None
    for item in data:
        if item > 10:
            print("Found:", item)
    return True
"""
    raw_bytes = python_code.encode("utf-8")
    expected_sha = hashlib.sha256(raw_bytes).hexdigest()
    session_id = str(uuid.uuid4())

    storage_path, bucket = temp_storage.upload_file(
        session_id=session_id,
        filename="sample.py",
        data=raw_bytes,
        content_type="text/x-python"
    )

    assert bucket == "chennalink-files"
    assert session_id in storage_path

    # Download and verify exact bytes
    downloaded = temp_storage.download_file(storage_path)
    assert downloaded == raw_bytes
    assert hashlib.sha256(downloaded).hexdigest() == expected_sha
    assert downloaded.decode("utf-8") == python_code

def test_storage_binary_and_unicode_fidelity(temp_storage):
    """Verify binary data with multibyte UTF-8 and control characters is preserved."""
    test_data = "🚀 Telugu: నమస్కారం | Japanese: こんにちは | Special: \t\r\n\x00\xff".encode("utf-8")
    expected_sha = hashlib.sha256(test_data).hexdigest()
    session_id = str(uuid.uuid4())

    storage_path, _ = temp_storage.upload_file(
        session_id=session_id,
        filename="unicode_test.bin",
        data=test_data
    )

    downloaded = temp_storage.download_file(storage_path)
    assert downloaded == test_data
    assert hashlib.sha256(downloaded).hexdigest() == expected_sha

def test_storage_signed_url_fallback(temp_storage):
    """Verify signed URL generator returns a valid download URL."""
    session_id = str(uuid.uuid4())
    dummy_data = b"Hello Storage"
    storage_path, _ = temp_storage.upload_file(session_id, "test.txt", dummy_data)

    signed_url = temp_storage.create_signed_url(storage_path)
    assert signed_url is not None
    assert storage_path in signed_url

def test_storage_nonexistent_file_raises(temp_storage):
    with pytest.raises(FileNotFoundError):
        temp_storage.download_file("nonexistent_session/missing.bin")

# =====================================================================
# 2. REPOSITORY SESSION & PARTICIPANT LIFECYCLE TESTS
# =====================================================================

def test_session_lifecycle_and_role_management(temp_repo):
    """Test session creation, participant joins, state transitions, and host termination."""
    code = "SES123"
    
    # 1. Host creates session
    session, host_part = temp_repo.create_session(
        session_code=code,
        host_device_id="HOST-DEV-01",
        host_display_name="Host User",
        host_email="host@example.com",
        host_device_type="cli"
    )
    assert session["session_code"] == code
    assert session["status"] == "waiting"
    assert host_part["role"] == "host"
    assert host_part["status"] == "connected"

    session_id = session["id"]

    # 2. Participant 2 joins -> session activates
    sess2, p2 = temp_repo.join_session(
        session_code=code,
        device_id="PEER-DEV-02",
        display_name="Peer 2",
        device_type="web",
        active_count=1,
        max_limit=4
    )
    assert sess2["status"] == "active"
    assert p2["role"] == "participant"

    # 3. Participant 3 and 4 join successfully
    sess3, p3 = temp_repo.join_session(code, "PEER-DEV-03", "Peer 3", active_count=2, max_limit=4)
    sess4, p4 = temp_repo.join_session(code, "PEER-DEV-04", "Peer 4", active_count=3, max_limit=4)

    participants = temp_repo.get_participants(session_id)
    assert len(participants) == 4

    # 4. 5th participant connection rejected
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        temp_repo.join_session(code, "PEER-DEV-05", "Peer 5", active_count=4, max_limit=4)
    assert exc_info.value.status_code == 403

    # 5. Non-host cannot terminate session
    with pytest.raises(HTTPException) as exc_info:
        temp_repo.end_session(code, "PEER-DEV-02")
    assert exc_info.value.status_code == 403

    # 6. Host terminates session
    ended_sess = temp_repo.end_session(code, "HOST-DEV-01")
    assert ended_sess["status"] == "ended"
    assert ended_sess["ended_at"] is not None

    # 7. Joining ended session rejected
    with pytest.raises(HTTPException) as exc_info:
        temp_repo.join_session(code, "PEER-DEV-06", "Peer 6", active_count=0, max_limit=4)
    assert exc_info.value.status_code == 400

# =====================================================================
# 3. MESSAGE PRESERVATION, DEDUPLICATION & HISTORY TESTS
# =====================================================================

def test_message_indentation_preservation_and_deduplication(temp_repo):
    """Test exact code indentation preservation and idempotent deduplication."""
    code = "MSG456"
    session, host = temp_repo.create_session(code, "HOST-01", "Host")
    _, peer = temp_repo.join_session(code, "PEER-02", "Peer")

    raw_code = """class DataProcessor:
    def process(self):
        items = [1, 2, 3]
        for i in items:
            print(f"Item: {i}")
        return True
"""
    client_msg_id = "msg-unique-001"
    meta = {
        "file_name": "processor.py",
        "language": "python",
        "peer_name": "Host",
        "size_bytes": len(raw_code.encode("utf-8")),
        "sha256": hashlib.sha256(raw_code.encode("utf-8")).hexdigest()
    }

    # 1. Save message
    msg = temp_repo.save_message(
        session_id=session["id"],
        sender_device_id="HOST-01",
        client_message_id=client_msg_id,
        message_type="code",
        content=raw_code,
        metadata=meta,
        recipient_device_id=None,
        delivery_status="stored"
    )
    assert msg["content"] == raw_code

    # 2. Duplicate retry with same client_message_id does not fail
    msg_retry = temp_repo.save_message(
        session_id=session["id"],
        sender_device_id="HOST-01",
        client_message_id=client_msg_id,
        message_type="code",
        content=raw_code,
        metadata=meta,
        recipient_device_id=None,
        delivery_status="delivered"
    )
    assert msg_retry["delivery_status"] == "delivered"

    # 3. Verify history for Host (direction == 'sent')
    host_hist = temp_repo.get_history(code, "HOST-01")
    assert host_hist["total"] == 1
    assert host_hist["items"][0]["direction"] == "sent"
    assert host_hist["items"][0]["content"] == raw_code
    assert host_hist["items"][0]["file_name"] == "processor.py"

    # 4. Verify history for Peer (direction == 'received')
    peer_hist = temp_repo.get_history(code, "PEER-02")
    assert peer_hist["total"] == 1
    assert peer_hist["items"][0]["direction"] == "received"
    assert peer_hist["items"][0]["content"] == raw_code

    # 5. Search filtering
    search_hit = temp_repo.get_history(code, "HOST-01", search="DataProcessor")
    assert search_hit["total"] == 1
    search_miss = temp_repo.get_history(code, "HOST-01", search="NonExistentTerm")
    assert search_miss["total"] == 0

# =====================================================================
# 4. FILE TRANSFER RECORD TRACKING
# =====================================================================

def test_file_transfer_tracking(temp_repo):
    session, host = temp_repo.create_session("FIL123", "HOST-01", "Host")
    session_id = session["id"]

    transfer = temp_repo.create_file_transfer(
        session_id=session_id,
        sender_device_id="HOST-01",
        file_name="bundle.zip",
        size_bytes=1048576,
        sha256="abc123sha",
        storage_bucket="chennalink-files",
        storage_path=f"{session_id}/bundle.zip",
        content_type="application/zip",
        transfer_status="completed"
    )
    assert transfer["file_name"] == "bundle.zip"
    assert transfer["size_bytes"] == 1048576

    fetched = temp_repo.get_file_transfer(session_id, transfer["id"])
    assert fetched is not None
    assert fetched["sha256"] == "abc123sha"

    fetched_by_path = temp_repo.get_file_transfer(session_id, f"{session_id}/bundle.zip")
    assert fetched_by_path is not None
    assert fetched_by_path["id"] == transfer["id"]

# =====================================================================
# 5. API ENDPOINTS: HEALTH & FILE DOWNLOAD
# =====================================================================

def test_api_health_endpoint():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "database" in data
    assert data["storage_bucket"] == "chennalink-files"
    assert data["max_file_size_mb"] >= 10

def test_api_authorized_file_download(temp_storage, monkeypatch):
    """Test authorized download of file with SHA-256 verification."""
    from backend.routers import files as files_module
    monkeypatch.setattr(files_module, "storage_service", temp_storage)

    # 1. Create session and peer
    code = "DL" + uuid.uuid4().hex[:4].upper()
    r_create = client.post("/api/sessions/create", json={
        "email": "h@test.com", "name": "Host", "device_id": "HOST-DWN-01",
        "device_name": "Host", "session_code": code, "device_type": "cli"
    })
    assert r_create.status_code == 200
    host_uuid = r_create.json()["device_id"]
    sess_id = r_create.json()["session_id"]

    r_join = client.post("/api/sessions/join", json={
        "email": "p@test.com", "name": "Peer", "device_id": "PEER-DWN-02",
        "device_name": "Peer", "session_code": code, "device_type": "web"
    })
    assert r_join.status_code == 200
    peer_uuid = r_join.json()["device_id"]

    # 2. Upload sample file to storage
    test_content = b"Exact bytes for file download API test"
    test_sha = hashlib.sha256(test_content).hexdigest()
    storage_path, bucket = temp_storage.upload_file(sess_id, "download_test.txt", test_content)

    # 3. Create transfer record in repo
    repo = get_repository()
    transfer = repo.create_file_transfer(
        session_id=sess_id,
        sender_device_id=host_uuid,
        file_name="download_test.txt",
        size_bytes=len(test_content),
        sha256=test_sha,
        storage_bucket=bucket,
        storage_path=storage_path,
        content_type="text/plain",
        transfer_status="completed"
    )

    # 4. Authorized download by peer
    resp_dl = client.get(f"/api/files/download/{sess_id}/{transfer['id']}?device_id={peer_uuid}")
    assert resp_dl.status_code == 200
    assert resp_dl.content == test_content
    assert hashlib.sha256(resp_dl.content).hexdigest() == test_sha

    # 5. Unauthorized device rejected
    resp_unauth = client.get(f"/api/files/download/{sess_id}/{transfer['id']}?device_id=STRANGER-DEV")
    assert resp_unauth.status_code == 403

    # 6. Signed URL generation
    resp_signed = client.get(f"/api/files/signed-url/{sess_id}/{transfer['id']}?device_id={peer_uuid}")
    assert resp_signed.status_code == 200
    assert "signed_url" in resp_signed.json()
    assert resp_signed.json()["sha256"] == test_sha

# =====================================================================
# 6. SQLITE TO SUPABASE MIGRATION SCRIPT TEST
# =====================================================================

def test_migration_utility(tmp_path, temp_repo):
    """Verify migrate_sqlite_to_supabase extracts and deduplicates old SQLite records."""
    source_db_path = str(tmp_path / "legacy_source.db")
    with sqlite3.connect(source_db_path) as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE sessions (
            id TEXT PRIMARY KEY, session_code TEXT, host_device_id TEXT, status TEXT, created_at TIMESTAMP
        )""")
        c.execute("""CREATE TABLE devices (
            id TEXT PRIMARY KEY, session_id TEXT, device_id TEXT, name TEXT, device_type TEXT, connected_at TIMESTAMP
        )""")
        c.execute("""CREATE TABLE history (
            owner_device_id TEXT, direction TEXT, id TEXT, session_id TEXT, sender_device_id TEXT,
            receiver_device_id TEXT, peer_name TEXT, file_name TEXT, language TEXT, content TEXT,
            size_bytes INTEGER, sha256 TEXT, created_at TIMESTAMP, status TEXT
        )""")

        c.execute("INSERT INTO sessions VALUES ('s1', 'MIG001', 'DEV-HOST', 'active', '2026-01-01T00:00:00Z')")
        c.execute("INSERT INTO devices VALUES ('p1', 's1', 'DEV-HOST', 'Host', 'cli', '2026-01-01T00:00:00Z')")
        c.execute("INSERT INTO devices VALUES ('p2', 's1', 'DEV-PEER', 'Peer', 'web', '2026-01-01T00:00:00Z')")

        # Two history rows for the same message (one sent, one received)
        c.execute("""INSERT INTO history VALUES
            ('DEV-HOST', 'sent', 'msg-1', 's1', 'DEV-HOST', 'DEV-PEER', 'Host', 'migrated.py', 'python',
             'def migrated(): pass', 20, 'sha1', '2026-01-01T00:01:00Z', 'delivered')""")
        c.execute("""INSERT INTO history VALUES
            ('DEV-PEER', 'received', 'msg-1', 's1', 'DEV-HOST', 'DEV-PEER', 'Host', 'migrated.py', 'python',
             'def migrated(): pass', 20, 'sha1', '2026-01-01T00:01:00Z', 'delivered')""")
        conn.commit()

    summary = migrate(source_db_path, target_repo=temp_repo)
    assert summary["sessions"] == 1
    assert summary["participants"] == 2
    # Dual history rows must be deduplicated into 1 canonical message
    assert summary["messages"] == 1

    # Verify message exists in target repo
    history = temp_repo.get_history("MIG001", "DEV-HOST")
    assert history["total"] == 1
    assert history["items"][0]["file_name"] == "migrated.py"
    assert history["items"][0]["content"] == "def migrated(): pass"
