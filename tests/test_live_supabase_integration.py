import os
import uuid
import hashlib
import pytest
from datetime import datetime, timezone

from backend.config import Settings
from backend.repository import PostgresRepository
from backend.storage import StorageService

# Retrieve live configuration
LIVE_DATABASE_URL = os.environ.get("DATABASE_URL")
LIVE_SUPABASE_URL = os.environ.get("SUPABASE_URL")
LIVE_SECRET_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not LIVE_DATABASE_URL or not LIVE_SUPABASE_URL or not LIVE_SECRET_KEY:
    # Try reading from .env file
    from dotenv import dotenv_values
    env_vals = dotenv_values(".env")
    LIVE_DATABASE_URL = LIVE_DATABASE_URL or env_vals.get("DATABASE_URL")
    LIVE_SUPABASE_URL = LIVE_SUPABASE_URL or env_vals.get("SUPABASE_URL")
    LIVE_SECRET_KEY = LIVE_SECRET_KEY or env_vals.get("SUPABASE_SERVICE_ROLE_KEY")

SKIP_LIVE = not (LIVE_DATABASE_URL and LIVE_SUPABASE_URL and LIVE_SECRET_KEY)

@pytest.fixture(scope="module")
def live_repo():
    repo = PostgresRepository(LIVE_DATABASE_URL)
    yield repo
    repo.pool.close()

@pytest.fixture(scope="module")
def live_storage():
    storage = StorageService(
        supabase_url=LIVE_SUPABASE_URL,
        supabase_key=LIVE_SECRET_KEY,
        bucket_name="chennalink-files"
    )
    return storage

@pytest.mark.skipif(SKIP_LIVE, reason="Live Supabase credentials not provided")
class TestLiveSupabaseIntegration:
    def test_live_postgres_connectivity_and_tables(self, live_repo):
        """Verify PostgreSQL connectivity and schema existence in live Supabase."""
        with live_repo.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                """)
                tables = {row[0] for row in cur.fetchall()}
                assert "sessions" in tables
                assert "participants" in tables
                assert "messages" in tables
                assert "file_transfers" in tables

    def test_live_session_and_participant_lifecycle(self, live_repo):
        """Verify live session creation, joins, and state progression."""
        code = "LV" + uuid.uuid4().hex[:4].upper()
        host_device = "TEST-HOST-" + uuid.uuid4().hex[:6]
        
        # 1. Create Session
        session, host = live_repo.create_session(
            session_code=code,
            host_device_id=host_device,
            host_display_name="Live Host",
            host_device_type="cli"
        )
        assert session["session_code"] == code
        assert session["status"] == "waiting"
        session_id = session["id"]

        try:
            # 2. Peer Joins (session activates)
            peer_device = "TEST-PEER-" + uuid.uuid4().hex[:6]
            sess_active, peer = live_repo.join_session(
                session_code=code,
                device_id=peer_device,
                display_name="Live Peer",
                device_type="web",
                active_count=1,
                max_limit=4
            )
            assert sess_active["status"] == "active"
            assert peer["role"] == "participant"

            # 3. Retrieve session & participants
            fetched_sess = live_repo.get_session(code)
            assert fetched_sess["id"] == session_id
            parts = live_repo.get_participants(session_id)
            assert len(parts) >= 2

            # 4. Host ends session
            ended = live_repo.end_session(code, host_device)
            assert ended["status"] == "ended"

        finally:
            # Cleanup test records
            with live_repo.pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM public.sessions WHERE id = %s", (session_id,))
                conn.commit()

    def test_live_message_indentation_preservation_and_deduplication(self, live_repo):
        """Verify live multiline Python code indentation preservation and deduplication."""
        code = "LM" + uuid.uuid4().hex[:4].upper()
        host_device = "HOST-" + uuid.uuid4().hex[:6]
        session, host = live_repo.create_session(code, host_device, "Host")
        session_id = session["id"]

        raw_python = (
            "def test_algorithm():\n"
            "    # Exact 4-space indentation\n"
            "    matrix = [\n"
            "        [1, 2, 3],\n"
            "        [4, 5, 6]\n"
            "    ]\n"
            "    for row in matrix:\n"
            "        for val in row:\n"
            "            if val > 3:\n"
            "                yield val\n"
        )
        client_msg_id = "msg-" + uuid.uuid4().hex

        try:
            # 1. Save Message
            msg = live_repo.save_message(
                session_id=session_id,
                sender_device_id=host_device,
                client_message_id=client_msg_id,
                message_type="code",
                content=raw_python,
                metadata={"file_name": "algo.py", "language": "python", "peer_name": "Host"},
                delivery_status="stored"
            )
            assert msg["content"] == raw_python

            # 2. Retrieve History & Check Exact Preservation
            hist = live_repo.get_history(code, host_device)
            assert hist["total"] >= 1
            matching = [m for m in hist["items"] if m["id"] == client_msg_id]
            assert len(matching) == 1
            assert matching[0]["content"] == raw_python
            assert matching[0]["direction"] == "sent"

            # 3. Idempotent Retry (Same client_message_id)
            msg_retry = live_repo.save_message(
                session_id=session_id,
                sender_device_id=host_device,
                client_message_id=client_msg_id,
                message_type="code",
                content=raw_python,
                metadata={"file_name": "algo.py"},
                delivery_status="delivered"
            )
            assert msg_retry["delivery_status"] == "delivered"
            # Ensure no duplicates inserted
            hist_after = live_repo.get_history(code, host_device)
            matching_after = [m for m in hist_after["items"] if m["id"] == client_msg_id]
            assert len(matching_after) == 1

        finally:
            with live_repo.pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM public.sessions WHERE id = %s", (session_id,))
                conn.commit()

    def test_live_storage_upload_download_and_integrity(self, live_storage, live_repo):
        """Verify live Supabase Storage upload, download, and SHA-256 integrity."""
        sess_id = str(uuid.uuid4())
        test_filename = "live_storage_test.py"
        test_payload = (
            "# Live storage verification with Telugu & emojis\n"
            "greeting = 'నమస్కారం ప్రపంచం 🚀'\n"
            "values = [x * 2 for x in range(100)]\n"
        ).encode("utf-8")
        expected_sha = hashlib.sha256(test_payload).hexdigest()

        # 1. Upload to Supabase Storage
        storage_path, bucket = live_storage.upload_file(
            session_id=sess_id,
            filename=test_filename,
            data=test_payload,
            content_type="text/x-python"
        )
        assert bucket == "chennalink-files"
        assert sess_id in storage_path

        try:
            # 2. Download from Supabase Storage
            downloaded = live_storage.download_file(storage_path)
            assert downloaded == test_payload
            actual_sha = hashlib.sha256(downloaded).hexdigest()
            assert actual_sha == expected_sha

            # 3. Create signed URL
            signed_url = live_storage.create_signed_url(storage_path, expires_in=3600)
            assert signed_url is not None
            assert "nagrpktxgwownfldpfip.supabase.co" in signed_url

        finally:
            # Clean up object from Supabase bucket
            if live_storage.client:
                live_storage.client.storage.from_(bucket).remove([storage_path])
