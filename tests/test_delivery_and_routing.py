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

def test_uuid_device_routing_and_delivery():
    code = "292005"
    
    # 1. User A creates session - server returns server-generated device UUID
    res_A = client.post("/api/sessions/create", json={
        "email": "userA@example.com",
        "name": "User-A",
        "device_id": "CLIENT-A-LOCAL",
        "device_name": "Device-A",
        "session_code": code,
        "device_type": "cli"
    })
    assert res_A.status_code == 200
    data_A = res_A.json()
    uuid_A = data_A["device_id"]
    session_id = data_A["session_id"]
    
    # Verify duplicate session create returns 400
    dup_res = client.post("/api/sessions/create", json={
        "email": "other@example.com",
        "name": "Other",
        "device_id": "OTHER",
        "device_name": "Other",
        "session_code": code,
        "device_type": "web"
    })
    assert dup_res.status_code == 400
    assert "Session code already in use" in dup_res.json()["detail"]

    # 2. User B joins session - server returns server-generated device UUID
    res_B = client.post("/api/sessions/join", json={
        "email": "userB@example.com",
        "name": "User-B",
        "device_id": "CLIENT-B-LOCAL",
        "device_name": "Device-B",
        "session_code": code,
        "device_type": "web"
    })
    assert res_B.status_code == 200
    data_B = res_B.json()
    uuid_B = data_B["device_id"]
    
    # Ensure returned device_ids are unique UUIDs
    assert uuid_A != uuid_B
    assert uuid_A != "CLIENT-A-LOCAL"
    assert uuid_B != "CLIENT-B-LOCAL"

    with ExitStack() as stack:
        # Connect both clients using the returned UUIDs (as observed in user logs)
        ws_A = stack.enter_context(client.websocket_connect(f"/ws/{code}/{uuid_A}"))
        st_A1 = ws_A.receive_json()
        assert st_A1["type"] == "status_update"
        assert st_A1["active_devices"] == 1
        
        ws_B = stack.enter_context(client.websocket_connect(f"/ws/{code}/{uuid_B}"))
        st_A2 = ws_A.receive_json()
        assert st_A2["type"] == "status_update"
        assert st_A2["active_devices"] == 2
        
        st_B1 = ws_B.receive_json()
        assert st_B1["type"] == "status_update"
        assert st_B1["active_devices"] == 2

        # 3. User A sends hello.py to User B
        content_A = "def hello():\n    print('Hello from User A: 🚀 తెలుగు')\n"
        msg_id_A = str(uuid.uuid4())
        ws_A.send_json({
            "type": "code_file",
            "message_id": msg_id_A,
            "sender_device_id": uuid_A,
            "file_name": "hello.py",
            "language": "python",
            "content": content_A
        })
        
        # User A receives ACK
        ack_A = ws_A.receive_json()
        assert ack_A["type"] == "ack"
        
        # User B receives the file in real-time
        recv_B = ws_B.receive_json()
        assert recv_B["type"] == "code_file"
        assert recv_B["file_name"] == "hello.py"
        assert recv_B["content"] == content_A
        assert recv_B["message_id"] == msg_id_A
        
        # A must NOT receive its own message (verify socket A queue is empty)
        # 4. User B sends solution.py to User A
        content_B = "def solve():\n    return 'Solution from User B: コンピュータ'\n"
        msg_id_B = str(uuid.uuid4())
        ws_B.send_json({
            "type": "code_file",
            "message_id": msg_id_B,
            "sender_device_id": uuid_B,
            "file_name": "solution.py",
            "language": "python",
            "content": content_B
        })
        
        # User B receives ACK
        ack_B = ws_B.receive_json()
        assert ack_B["type"] == "ack"
        
        # User A receives the file in real-time
        recv_A = ws_A.receive_json()
        assert recv_A["type"] == "code_file"
        assert recv_A["file_name"] == "solution.py"
        assert recv_A["content"] == content_B
        assert recv_A["message_id"] == msg_id_B

        # 5. Verify History API separation for both clients
        # A's history
        hist_A = client.get(f"/api/history/{session_id}?device_id={uuid_A}").json()["items"]
        assert len(hist_A) == 2
        # Most recent first
        assert hist_A[0]["file_name"] == "solution.py"
        assert hist_A[0]["direction"] == "received"
        assert hist_A[1]["file_name"] == "hello.py"
        assert hist_A[1]["direction"] == "sent"

        # B's history
        hist_B = client.get(f"/api/history/{session_id}?device_id={uuid_B}").json()["items"]
        assert len(hist_B) == 2
        assert hist_B[0]["file_name"] == "solution.py"
        assert hist_B[0]["direction"] == "sent"
        assert hist_B[1]["file_name"] == "hello.py"
        assert hist_B[1]["direction"] == "received"

        # Also verify history querying using session_code instead of session UUID
        hist_B_by_code = client.get(f"/api/history/{code}?device_id={uuid_B}").json()["items"]
        assert len(hist_B_by_code) == 2

        # 6. Disconnect B -> A receives status update with 1 active device
        ws_B.close()
        time.sleep(0.05)
        st_A3 = ws_A.receive_json()
        assert st_A3["type"] == "status_update"
        assert st_A3["active_devices"] == 1
