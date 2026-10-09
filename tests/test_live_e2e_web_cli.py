import os
import uuid
import json
import base64
import hashlib
import pytest
from contextlib import ExitStack
from fastapi.testclient import TestClient

from backend.config import settings
from backend.repository import get_repository, reset_repository, PostgresRepository
from backend.storage import get_storage_service, reset_storage_service
from backend.main import app

# Check if live Supabase is configured
from dotenv import dotenv_values
env_vals = dotenv_values(".env")
LIVE_DB = os.environ.get("DATABASE_URL") or env_vals.get("DATABASE_URL")
LIVE_URL = os.environ.get("SUPABASE_URL") or env_vals.get("SUPABASE_URL")
LIVE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or env_vals.get("SUPABASE_SERVICE_ROLE_KEY")

SKIP_LIVE = not (LIVE_DB and LIVE_URL and LIVE_KEY)

@pytest.mark.skipif(SKIP_LIVE, reason="Live Supabase credentials not provided")
def test_live_web_cli_end_to_end_with_real_supabase(monkeypatch):
    """
    Comprehensive live end-to-end test connecting Web and CLI to the FastAPI backend,
    persisting in Supabase PostgreSQL and private Supabase Storage, and validating
    exact formatting, history synchronization, and storage downloads.
    """
    # 1. Enforce Production Mode against live Supabase
    monkeypatch.setattr(settings, "chennalink_env", "production")
    monkeypatch.setattr(settings, "db_backend", "postgres")
    monkeypatch.setattr(settings, "storage_backend", "supabase")
    monkeypatch.setattr(settings, "allow_local_fallback", False)
    monkeypatch.setattr(settings, "database_url", LIVE_DB)
    monkeypatch.setattr(settings, "supabase_url", LIVE_URL)
    monkeypatch.setattr(settings, "supabase_service_role_key", LIVE_KEY)
    monkeypatch.setattr(settings, "supabase_storage_bucket", "chennalink-files")

    reset_repository()
    reset_storage_service()

    client = TestClient(app)

    # 2. Verify health check reports production state
    res_health = client.get("/api/health")
    assert res_health.status_code == 200
    h_data = res_health.json()
    assert h_data["status"] == "healthy"
    assert h_data["database"] == "PostgresRepository"
    assert h_data["database_backend"] == "postgres"
    assert h_data["storage_backend"] == "supabase"
    assert h_data["storage_bucket"] == "chennalink-files"

    repo = get_repository()
    assert isinstance(repo, PostgresRepository)

    # 3. Web client creates session
    code = "E2E" + uuid.uuid4().hex[:3].upper()
    web_device_id = "WEB-USER-" + uuid.uuid4().hex[:6]
    res_create = client.post("/api/sessions/create", json={
        "email": "webuser@example.com",
        "name": "WebUser",
        "device_id": web_device_id,
        "device_name": "Web Browser",
        "session_code": code,
        "device_type": "web"
    })
    assert res_create.status_code == 200
    sess_info = res_create.json()
    session_id = sess_info["session_id"]
    web_uuid = sess_info["device_id"]

    try:
        # 4. CLI client joins session
        cli_device_id = "CLI-USER-" + uuid.uuid4().hex[:6]
        res_join = client.post("/api/sessions/join", json={
            "email": "cliuser@example.com",
            "name": "CLIUser",
            "device_id": cli_device_id,
            "device_name": "CLI Terminal",
            "session_code": code,
            "device_type": "cli"
        })
        assert res_join.status_code == 200
        cli_uuid = res_join.json()["device_id"]

        # 5. Connect both Web and CLI via WebSockets
        with ExitStack() as stack:
            ws_web = stack.enter_context(client.websocket_connect(f"/ws/{code}/{web_uuid}"))
            web_st1 = ws_web.receive_json()
            assert web_st1["type"] == "status_update"

            ws_cli = stack.enter_context(client.websocket_connect(f"/ws/{code}/{cli_uuid}"))
            
            # Both receive active count = 2
            web_st2 = ws_web.receive_json()
            assert web_st2["type"] == "status_update"
            assert web_st2["active_devices"] == 2

            cli_st1 = ws_cli.receive_json()
            assert cli_st1["type"] == "status_update"
            assert cli_st1["active_devices"] == 2

            # 6. Web sends exact code payload to CLI (with indentation, blank lines, Telugu unicode)
            web_code = (
                "def calculate_tax(income: float) -> float:\n"
                "    \"\"\"Exact indentation docstring test\"\"\"\n"
                "    # Multi-lingual comment: నమస్కారం 🚀\n"
                "\n"
                "    if income <= 10000:\n"
                "        return 0.0\n"
                "    elif income <= 50000:\n"
                "        tax = income * 0.1\n"
                "        return tax\n"
                "\n"
                "    return income * 0.2\n"
            )
            web_bytes = web_code.encode("utf-8")
            web_sha = hashlib.sha256(web_bytes).hexdigest()
            msg_id_1 = str(uuid.uuid4())

            ws_web.send_json({
                "type": "code_file",
                "message_id": msg_id_1,
                "sender_device_id": web_device_id,
                "file_name": "tax_calc.py",
                "language": "python",
                "content": web_code
            })

            # Web receives ACK
            ack_web = ws_web.receive_json()
            assert ack_web["type"] == "ack"

            # CLI receives exact message in real-time
            rec_cli = ws_cli.receive_json()
            assert rec_cli["type"] == "code_file"
            assert rec_cli["file_name"] == "tax_calc.py"
            assert rec_cli["content"] == web_code
            assert hashlib.sha256(rec_cli["content"].encode("utf-8")).hexdigest() == web_sha

            # 7. CLI sends exact response to Web
            cli_code = (
                "const handleTax = (amount) => {\n"
                "  console.log(`Received: ${amount}`);\n"
                "  // UTF-8: こんにちは 世界 🌟\n"
                "  return amount > 0;\n"
                "};\n"
            )
            cli_sha = hashlib.sha256(cli_code.encode("utf-8")).hexdigest()
            msg_id_2 = str(uuid.uuid4())

            ws_cli.send_json({
                "type": "code_file",
                "message_id": msg_id_2,
                "sender_device_id": cli_device_id,
                "file_name": "client_tax.js",
                "language": "javascript",
                "content": cli_code
            })

            ack_cli = ws_cli.receive_json()
            assert ack_cli["type"] == "ack"

            rec_web = ws_web.receive_json()
            assert rec_web["type"] == "code_file"
            assert rec_web["file_name"] == "client_tax.js"
            assert rec_web["content"] == cli_code
            assert hashlib.sha256(rec_web["content"].encode("utf-8")).hexdigest() == cli_sha

            # 8. Web uploads a chunked file (>50 KB) to Supabase Storage
            large_binary_data = b"DEF_DATA_CHUNK_TEST_" * 3000 # ~60 KB
            large_sha = hashlib.sha256(large_binary_data).hexdigest()
            transfer_id = str(uuid.uuid4())
            chunk_size = 16384
            chunks = [large_binary_data[i:i+chunk_size] for i in range(0, len(large_binary_data), chunk_size)]

            ws_web.send_json({
                "type": "file_start",
                "transfer_id": transfer_id,
                "file_name": "large_binary.dat",
                "file_size": len(large_binary_data),
                "total_chunks": len(chunks),
                "sha256": large_sha
            })
            ack_start = ws_web.receive_json()
            assert ack_start["type"] == "ack"

            for idx, c_data in enumerate(chunks):
                ws_web.send_json({
                    "type": "file_chunk",
                    "transfer_id": transfer_id,
                    "index": idx,
                    "chunk": base64.b64encode(c_data).decode("ascii")
                })
                ack_chunk = ws_web.receive_json()
                assert ack_chunk["type"] == "ack"

            ws_web.send_json({
                "type": "file_end",
                "transfer_id": transfer_id
            })

            # CLI receives the assembled file announcement
            file_msg_cli = ws_cli.receive_json()
            assert file_msg_cli["type"] == "code_file"
            assert file_msg_cli["file_name"] == "large_binary.dat"
            assert file_msg_cli["size_bytes"] == len(large_binary_data)
            assert file_msg_cli["sha256"] == large_sha
            storage_path = file_msg_cli.get("storage_path")
            assert storage_path is not None
            assert "chennalink-files" in h_data["storage_bucket"]

            # 9. CLI downloads the file directly from Supabase Storage via authorized endpoint
            res_download = client.get(f"/api/files/download/{session_id}/{transfer_id}?device_id={cli_uuid}")
            assert res_download.status_code == 200
            assert res_download.content == large_binary_data
            assert hashlib.sha256(res_download.content).hexdigest() == large_sha

            # 10. Verify history retrieval from live Supabase PostgreSQL
            # CLI view
            hist_cli = client.get(f"/api/history/{session_id}?device_id={cli_uuid}&limit=10").json()
            assert hist_cli["total"] >= 2
            items_by_name = {it["file_name"]: it for it in hist_cli["items"]}
            assert "tax_calc.py" in items_by_name
            assert items_by_name["tax_calc.py"]["direction"] == "received"
            assert items_by_name["tax_calc.py"]["content"] == web_code

            assert "client_tax.js" in items_by_name
            assert items_by_name["client_tax.js"]["direction"] == "sent"

            # Web view
            hist_web = client.get(f"/api/history/{session_id}?device_id={web_uuid}&limit=10").json()
            assert hist_web["total"] >= 2
            items_web_by_name = {it["file_name"]: it for it in hist_web["items"]}
            assert items_web_by_name["tax_calc.py"]["direction"] == "sent"
            assert items_web_by_name["client_tax.js"]["direction"] == "received"

            # 11. Host ends session
            ws_web.send_json({"type": "end_session"})
            cli_end = ws_cli.receive_json()
            assert cli_end["type"] == "session_ended"

        # Verify session status is ended in Supabase PostgreSQL
        with repo.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status, ended_at FROM public.sessions WHERE id = %s", (session_id,))
                row = cur.fetchone()
                assert row[0] == "ended"
                assert row[1] is not None

    finally:
        # Clean up test session in Supabase PostgreSQL (cascade deletes participants & messages)
        with repo.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM public.sessions WHERE id = %s", (session_id,))
            conn.commit()

        # Clean up uploaded storage object from Supabase bucket
        try:
            storage_srv = get_storage_service()
            if storage_srv.client and storage_path:
                storage_srv.client.storage.from_("chennalink-files").remove([storage_path])
        except Exception:
            pass
