import pytest
import hashlib
import json
import uuid
import time
from fastapi.testclient import TestClient
from contextlib import ExitStack

from backend.main import app
from backend.database import init_db, get_db

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessions")
    cursor.execute("DELETE FROM devices")
    cursor.execute("DELETE FROM history")
    conn.commit()
    conn.close()

def test_cli_and_web_bidirectional_transfer():
    code = "CLIWEB"
    
    # 1. CLI Client creates session
    res_cli = client.post("/api/sessions/create", json={
        "email": "cli@example.com",
        "name": "CLI-User",
        "device_id": "CLI-DEV-01",
        "device_name": "CLI-User",
        "session_code": code,
        "device_type": "cli"
    })
    assert res_cli.status_code == 200
    cli_data = res_cli.json()
    
    # 2. Web Client joins session
    res_web = client.post("/api/sessions/join", json={
        "email": "web@example.com",
        "name": "Web-User",
        "device_id": "WEB-DEV-02",
        "device_name": "Web-User",
        "session_code": code,
        "device_type": "web"
    })
    assert res_web.status_code == 200
    web_data = res_web.json()

    with ExitStack() as stack:
        # CLI connects to WebSocket
        ws_cli = stack.enter_context(client.websocket_connect(f"/ws/{code}/CLI-DEV-01"))
        cli_st1 = ws_cli.receive_json()
        assert cli_st1["type"] == "status_update"
        assert cli_st1["active_devices"] == 1
        
        # Web connects to WebSocket
        ws_web = stack.enter_context(client.websocket_connect(f"/ws/{code}/WEB-DEV-02"))
        
        # Both receive active count = 2
        cli_st2 = ws_cli.receive_json()
        assert cli_st2["type"] == "status_update"
        assert cli_st2["active_devices"] == 2
        
        web_st1 = ws_web.receive_json()
        assert web_st1["type"] == "status_update"
        assert web_st1["active_devices"] == 2
        
        # Verify participants listed correctly
        types = {p["device_type"] for p in web_st1["participants"]}
        assert "cli" in types
        assert "web" in types

        # 3. CLI sends a file > 5 KB (8 KB) to Web
        large_code = "def cli_func():\n    return 'Hello from CLI: తెలుగు 🚀'\n" * 200
        large_bytes = large_code.encode("utf-8")
        assert len(large_bytes) > 5 * 1024 # Confirmed > 5 KB
        sha_cli = hashlib.sha256(large_bytes).hexdigest()
        
        msg_id_1 = str(uuid.uuid4())
        ws_cli.send_json({
            "type": "code_file",
            "message_id": msg_id_1,
            "sender_device_id": "CLI-DEV-01",
            "file_name": "cli_source.py",
            "language": "python",
            "content": large_code
        })
        
        # CLI receives ACK
        ack_cli = ws_cli.receive_json()
        assert ack_cli["type"] == "ack"
        
        # Web receives code file
        rec_web = ws_web.receive_json()
        assert rec_web["type"] == "code_file"
        assert rec_web["file_name"] == "cli_source.py"
        assert rec_web["content"] == large_code
        assert hashlib.sha256(rec_web["content"].encode("utf-8")).hexdigest() == sha_cli
        
        # Web sends ACK
        ws_web.send_json({"type": "ack", "message_id": msg_id_1})

        # 4. Web sends file to CLI (6 KB with special characters)
        web_code = "const webFunc = () => {\n  console.log('Web transfer: コンピュータ special: @#$%^&*');\n};\n" * 100
        web_bytes = web_code.encode("utf-8")
        assert len(web_bytes) > 5 * 1024
        sha_web = hashlib.sha256(web_bytes).hexdigest()
        
        msg_id_2 = str(uuid.uuid4())
        ws_web.send_json({
            "type": "code_file",
            "message_id": msg_id_2,
            "sender_device_id": "WEB-DEV-02",
            "file_name": "web_source.js",
            "language": "javascript",
            "content": web_code
        })
        
        # Web receives ACK
        ack_web = ws_web.receive_json()
        assert ack_web["type"] == "ack"
        
        # CLI receives code file
        rec_cli = ws_cli.receive_json()
        assert rec_cli["type"] == "code_file"
        assert rec_cli["file_name"] == "web_source.js"
        assert rec_cli["content"] == web_code
        assert hashlib.sha256(rec_cli["content"].encode("utf-8")).hexdigest() == sha_web

        # 5. Database direction checks:
        # CLI's view of history: sent 1, received 1
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT direction, file_name FROM history WHERE owner_device_id = 'CLI-DEV-01' ORDER BY created_at")
        cli_history = cursor.fetchall()
        assert len(cli_history) == 2
        assert cli_history[0]["direction"] == "sent"
        assert cli_history[0]["file_name"] == "cli_source.py"
        assert cli_history[1]["direction"] == "received"
        assert cli_history[1]["file_name"] == "web_source.js"

        # Web's view of history: received 1, sent 1
        cursor.execute("SELECT direction, file_name FROM history WHERE owner_device_id = 'WEB-DEV-02' ORDER BY created_at")
        web_history = cursor.fetchall()
        assert len(web_history) == 2
        assert web_history[0]["direction"] == "received"
        assert web_history[0]["file_name"] == "cli_source.py"
        assert web_history[1]["direction"] == "sent"
        assert web_history[1]["file_name"] == "web_source.js"
        conn.close()

        # 6. Disconnect Web client: Backend must not crash, CLI receives status update
        ws_web.close()
        time.sleep(0.05)
        cli_st3 = ws_cli.receive_json()
        assert cli_st3["type"] == "status_update"
        assert cli_st3["active_devices"] == 1
