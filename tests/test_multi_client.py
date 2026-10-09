import pytest
import time
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
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

def test_chennalink_connection_model():
    res = client.post("/api/sessions/create", json={
        "email": "a@x.com", "name": "A", "device_id": "A-1", "device_name": "A", "session_code": "TSCODE", "device_type": "cli"
    })
    assert res.status_code == 200
    
    for p in ["B", "C", "D", "E"]:
        res = client.post("/api/sessions/join", json={
            "email": f"{p.lower()}@x.com", "name": p, "device_id": f"{p}-1", "device_name": p, "session_code": "TSCODE", "device_type": "web"
        })
        assert res.status_code == 200

    with ExitStack() as stack:
        # Test 1: A connects (1/4 WAITING)
        ws_A = stack.enter_context(client.websocket_connect("/ws/TSCODE/A-1"))
        assert ws_A.receive_json()["active_devices"] == 1
        
        # Test 2: B connects (2/4 CONNECTED)
        ws_B = stack.enter_context(client.websocket_connect("/ws/TSCODE/B-1"))
        assert ws_A.receive_json()["active_devices"] == 2
        assert ws_B.receive_json()["active_devices"] == 2
        
        # Test 3: A + B only (Session works normally)
        ws_A.send_json({"type": "code_file", "file_name": "f.txt", "content": "x", "language": "txt"})
        ack = ws_A.receive_json()
        assert ack["type"] == "ack"
        
        msg_B = ws_B.receive_json()
        assert msg_B["type"] == "code_file"
        assert msg_B["content"] == "x"
        
        # Test 4: C connects (3/4 CONNECTED)
        ws_C = stack.enter_context(client.websocket_connect("/ws/TSCODE/C-1"))
        assert ws_A.receive_json()["active_devices"] == 3
        assert ws_B.receive_json()["active_devices"] == 3
        assert ws_C.receive_json()["active_devices"] == 3

        # Test 5: D connects (4/4 CONNECTED)
        ws_D = stack.enter_context(client.websocket_connect("/ws/TSCODE/D-1"))
        assert ws_A.receive_json()["active_devices"] == 4
        assert ws_B.receive_json()["active_devices"] == 4
        assert ws_C.receive_json()["active_devices"] == 4
        assert ws_D.receive_json()["active_devices"] == 4

        # Test 6: E attempts connection (SESSION FULL)
        try:
            ws_E = stack.enter_context(client.websocket_connect("/ws/TSCODE/E-1"))
            ws_E.receive_json()
            assert False, "Should have disconnected"
        except WebSocketDisconnect as e:
            assert e.code == 1008
        
        # Test 7: C disconnects (3/4)
        ws_C.close()
        time.sleep(0.05)
        assert ws_A.receive_json()["active_devices"] == 3
        assert ws_B.receive_json()["active_devices"] == 3
        assert ws_D.receive_json()["active_devices"] == 3

        # Test 8: E connects (4/4) -> now valid!
        ws_E = stack.enter_context(client.websocket_connect("/ws/TSCODE/E-1"))
        assert ws_A.receive_json()["active_devices"] == 4
        assert ws_B.receive_json()["active_devices"] == 4
        assert ws_D.receive_json()["active_devices"] == 4
        assert ws_E.receive_json()["active_devices"] == 4
        
        # Test 9: B disconnects (3/4)
        ws_B.close()
        time.sleep(0.05)
        assert ws_A.receive_json()["active_devices"] == 3
        assert ws_D.receive_json()["active_devices"] == 3
        assert ws_E.receive_json()["active_devices"] == 3
        
        # Test 10: B reconnects (4/4)
        ws_B_new = stack.enter_context(client.websocket_connect("/ws/TSCODE/B-1"))
        assert ws_A.receive_json()["active_devices"] == 4
        assert ws_D.receive_json()["active_devices"] == 4
        assert ws_E.receive_json()["active_devices"] == 4
        assert ws_B_new.receive_json()["active_devices"] == 4
        
        # Test 11: Only A remains (1/4 WAITING)
        ws_B_new.close()
        time.sleep(0.02)
        assert ws_A.receive_json()["active_devices"] == 3
        
        ws_D.close()
        time.sleep(0.02)
        assert ws_A.receive_json()["active_devices"] == 2
        
        ws_E.close()
        time.sleep(0.02)
        assert ws_A.receive_json()["active_devices"] == 1
        
        # Test 12: B reconnects (2/4 CONNECTED)
        ws_B_new2 = stack.enter_context(client.websocket_connect("/ws/TSCODE/B-1"))
        assert ws_A.receive_json()["active_devices"] == 2
        assert ws_B_new2.receive_json()["active_devices"] == 2
