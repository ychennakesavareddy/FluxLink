import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

from backend.database import init_db, get_db

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

def test_duplicate_device_connection():
    res = client.post("/api/sessions/create", json={
        "email": "a@x.com", "name": "A", "device_id": "A-1", "device_name": "A", "session_code": "DUPCOD", "device_type": "cli"
    })
    assert res.status_code == 200
    
    from contextlib import ExitStack
    from starlette.websockets import WebSocketDisconnect
    
    with ExitStack() as stack:
        ws1 = stack.enter_context(client.websocket_connect("/ws/DUPCOD/A-1"))
        data = ws1.receive_json()
        assert data["type"] == "status_update"
        
        # Connect again with the same device ID
        ws2 = stack.enter_context(client.websocket_connect("/ws/DUPCOD/A-1"))
        
        # The first socket should be disconnected
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws1.receive_json()
        assert exc_info.value.code == 1000
        
        data2 = ws2.receive_json()
        assert data2["type"] == "status_update"
