import os
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.repository import get_repository, reset_repository, SqliteRepository
from backend.storage import StorageService, reset_storage_service
from backend.main import app
from chennalink.app import ChennaLinkApp

# =====================================================================
# 1. PRODUCTION CONFIGURATION ENFORCEMENT TESTS
# =====================================================================

def test_production_config_rejects_missing_database_url(monkeypatch):
    """Verify production fails startup if DATABASE_URL is missing."""
    prod_settings = Settings(
        chennalink_env="production",
        db_backend="postgres",
        storage_backend="supabase",
        database_url=None,
        supabase_url="https://nagrpktxgwownfldpfip.supabase.co",
        supabase_anon_key="sb_publishable_dummy_key",
        allow_local_fallback=False
    )
    with pytest.raises(RuntimeError) as exc_info:
        prod_settings.validate_production()
    assert "DATABASE_URL" in str(exc_info.value)
    assert "SQLite persistence is strictly prohibited" in str(exc_info.value)

def test_production_config_rejects_allow_local_fallback():
    """Verify production prohibits allow_local_fallback=True."""
    prod_settings = Settings(
        chennalink_env="production",
        db_backend="postgres",
        storage_backend="supabase",
        database_url="postgresql://user:pass@localhost:5432/db",
        supabase_url="https://nagrpktxgwownfldpfip.supabase.co",
        supabase_anon_key="valid_key",
        allow_local_fallback=True
    )
    with pytest.raises(RuntimeError) as exc_info:
        prod_settings.validate_production()
    assert "allow_local_fallback" in str(exc_info.value)

def test_production_config_rejects_missing_storage_credentials():
    """Verify production fails startup if Supabase Storage credentials are missing."""
    prod_settings = Settings(
        chennalink_env="production",
        db_backend="postgres",
        storage_backend="supabase",
        database_url="postgresql://user:pass@localhost:5432/db",
        supabase_url=None,
        supabase_anon_key=None,
        supabase_service_role_key=None,
        allow_local_fallback=False
    )
    with pytest.raises(RuntimeError) as exc_info:
        prod_settings.validate_production()
    assert "Supabase Storage configuration" in str(exc_info.value)

def test_production_repository_rejects_sqlite_fallback(monkeypatch):
    """Verify get_repository raises RuntimeError instead of falling back to SQLite in production."""
    reset_repository()
    from backend.config import settings
    monkeypatch.setattr(settings, "chennalink_env", "production")
    monkeypatch.setattr(settings, "database_url", None)
    monkeypatch.setattr(settings, "allow_local_fallback", False)

    with pytest.raises(RuntimeError) as exc_info:
        get_repository()
    assert "DATABASE_URL" in str(exc_info.value)
    assert "Silent local SQLite fallback is strictly prohibited" in str(exc_info.value)

def test_production_repository_connection_failure_raises(monkeypatch):
    """Verify failed PostgreSQL connection raises RuntimeError without SQLite fallback."""
    reset_repository()
    from backend.config import settings
    monkeypatch.setattr(settings, "chennalink_env", "production")
    monkeypatch.setattr(settings, "database_url", "postgresql://user:pass@ep-fake.supabase.com/postgres")
    monkeypatch.setattr(settings, "allow_local_fallback", False)

    from backend import repository as repo_module
    def fail_pg_init(*args, **kwargs):
        raise Exception("Connection timeout: Supabase PostgreSQL unavailable")
    monkeypatch.setattr(repo_module, "PostgresRepository", fail_pg_init)

    with pytest.raises(RuntimeError) as exc_info:
        get_repository()
    assert "Production database connection failure" in str(exc_info.value)
    assert "Local SQLite fallback is strictly prohibited" in str(exc_info.value)

# =====================================================================
# 2. PRODUCTION STORAGE FAILURE & FALLBACK ENFORCEMENT TESTS
# =====================================================================

def test_production_storage_upload_failure_prohibits_local_disk_write(tmp_path, monkeypatch):
    """Verify that a Supabase upload failure in production raises and NEVER writes to local disk."""
    local_dir = tmp_path / "storage_local"
    
    from backend.config import settings
    monkeypatch.setattr(settings, "chennalink_env", "production")
    monkeypatch.setattr(settings, "allow_local_fallback", False)

    # Storage service with a mock client that fails on upload
    storage = StorageService(
        supabase_url="https://nagrpktxgwownfldpfip.supabase.co",
        supabase_key="valid_token",
        bucket_name="chennalink-files"
    )
    storage.local_storage_dir = str(local_dir)
    storage.client = MagicMock()
    storage.client.storage.from_().upload.side_effect = Exception("Supabase 503 Service Unavailable")

    test_bytes = b"def secure_code(): pass"
    with pytest.raises(RuntimeError) as exc_info:
        storage.upload_file("session-123", "code.py", test_bytes)
    
    assert "Supabase Storage upload failed" in str(exc_info.value)
    assert "Local disk fallback is strictly prohibited" in str(exc_info.value)
    # Assert nothing was saved locally
    assert not local_dir.exists() or len(list(local_dir.iterdir())) == 0

def test_production_storage_download_failure_prohibits_local_fallback(tmp_path, monkeypatch):
    """Verify that a Supabase download failure in production raises and NEVER checks local disk."""
    local_dir = tmp_path / "storage_local"
    local_sess = local_dir / "session-123"
    local_sess.mkdir(parents=True, exist_ok=True)
    fake_local_file = local_sess / "dummy.txt"
    fake_local_file.write_bytes(b"local unpersisted bytes")

    from backend.config import settings
    monkeypatch.setattr(settings, "chennalink_env", "production")
    monkeypatch.setattr(settings, "allow_local_fallback", False)

    storage = StorageService(
        supabase_url="https://nagrpktxgwownfldpfip.supabase.co",
        supabase_key="valid_token",
        bucket_name="chennalink-files"
    )
    storage.local_storage_dir = str(local_dir)
    storage.client = MagicMock()
    storage.client.storage.from_().download.side_effect = Exception("Object not found in Supabase")

    with pytest.raises(RuntimeError) as exc_info:
        storage.download_file("session-123/dummy.txt")
    assert "Failed to download file from Supabase Storage" in str(exc_info.value)

# =====================================================================
# 3. WEBSOCKET PERSISTENCE ERROR REPORTING (NO FALSE SUCCESS)
# =====================================================================

def test_websocket_message_persistence_failure_reports_error(monkeypatch):
    """Verify that if database save fails, client receives error and NOT ack/delivery."""
    reset_repository()
    from backend import main as main_module
    
    mock_repo = MagicMock()
    mock_repo.get_session.return_value = {"id": "s-123", "status": "active"}
    mock_repo.get_participant.return_value = {"id": "p-1", "device_id": "CLI-1", "display_name": "CLI-1"}
    mock_repo.save_message.side_effect = Exception("PostgreSQL disk full / connection timeout")
    
    monkeypatch.setattr(main_module, "get_repository", lambda: mock_repo)

    client = TestClient(app)
    with client.websocket_connect("/ws/TEST01/CLI-1") as ws:
        status_msg = ws.receive_json()
        assert status_msg["type"] == "status_update"

        ws.send_json({
            "type": "code_file",
            "message_id": "msg-err-test",
            "sender_device_id": "CLI-1",
            "file_name": "test.py",
            "content": "print('hello')"
        })

        resp = ws.receive_json()
        assert resp["type"] == "error"
        assert "Message persistence failed" in resp["message"]

# =====================================================================
# 4. CLI CONNECTION CONFIGURATION FOR PRODUCTION BACKEND
# =====================================================================

def test_cli_app_derives_backend_urls_from_environment(monkeypatch):
    """Verify Chennalink CLI derives HTTP and WSS URLs from CHENNALINK_BACKEND_URL."""
    monkeypatch.setenv("CHENNALINK_BACKEND_URL", "https://chennalink.onrender.com")
    cli_app = ChennaLinkApp()
    assert cli_app.api_base == "https://chennalink.onrender.com/api"
    assert cli_app.ws_base == "wss://chennalink.onrender.com/ws"

def test_cli_app_defaults_to_localhost(monkeypatch):
    """Verify Chennalink CLI defaults to 127.0.0.1:8000 when CHENNALINK_BACKEND_URL is unset."""
    monkeypatch.delenv("CHENNALINK_BACKEND_URL", raising=False)
    cli_app = ChennaLinkApp()
    assert cli_app.api_base == "http://127.0.0.1:8000/api"
    assert cli_app.ws_base == "ws://127.0.0.1:8000/ws"
