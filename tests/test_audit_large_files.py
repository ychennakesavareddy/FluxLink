import pytest
import os
import hashlib
import json
import uuid
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

def make_test_content(size_bytes: int, special: bool = False) -> str:
    if special:
        prefix = "def special_func():\n\t# Tabs, spaces, and unicode: తెలుగు 🚀 コンピュータ\n\tval = \"quotes 'and' \\\"escapes\\\"\"\n\n"
        prefix_bytes = prefix.encode("utf-8")
        if size_bytes <= len(prefix_bytes):
            return prefix
        repeat_chunk = "    # Line filler with special chars: @#$%^&*()\n"
        repeat_bytes = repeat_chunk.encode("utf-8")
        needed = (size_bytes - len(prefix_bytes)) // len(repeat_bytes) + 1
        full_content = prefix + (repeat_chunk * needed)
        # Slice to exact utf-8 byte size safely
        encoded = full_content.encode("utf-8")[:size_bytes]
        # Ensure valid utf-8 decoding (drop partial byte at boundary if any)
        return encoded.decode("utf-8", errors="ignore")
    else:
        repeat_chunk = "def line_filler():\n    return '0123456789abcdef'\n"
        needed = size_bytes // len(repeat_chunk.encode("utf-8")) + 1
        full_content = repeat_chunk * needed
        encoded = full_content.encode("utf-8")[:size_bytes]
        return encoded.decode("utf-8", errors="ignore")

@pytest.mark.parametrize("size_name,size_bytes,is_special", [
    ("1KB", 1024, False),
    ("5KB", 5 * 1024, False),
    ("6KB", 6 * 1024, True),
    ("10KB", 10 * 1024, False),
    ("50KB", 50 * 1024, True),
    ("100KB", 100 * 1024, False),
    ("500KB", 500 * 1024, True),
    ("1MB", 1024 * 1024, False),
    ("5MB", 5 * 1024 * 1024, True),
    ("10MB", 10 * 1024 * 1024, False),
])
def test_file_transfer_exact_sizes(size_name, size_bytes, is_special):
    # Session code must be exactly 6 characters
    code = f"SZ{size_name.rjust(4, '0')}"[:6].upper()
    
    # 1. HTTP Session setup
    res = client.post("/api/sessions/create", json={
        "email": "sender@x.com", "name": "Sender", "device_id": "DEV-A", "device_name": "A", "session_code": code, "device_type": "cli"
    })
    assert res.status_code == 200
    
    res = client.post("/api/sessions/join", json={
        "email": "receiver@x.com", "name": "Receiver", "device_id": "DEV-B", "device_name": "B", "session_code": code, "device_type": "cli"
    })
    assert res.status_code == 200

    content = make_test_content(size_bytes, special=is_special)
    original_bytes = content.encode("utf-8")
    original_byte_size = len(original_bytes)
    original_sha256 = hashlib.sha256(original_bytes).hexdigest()
    
    with ExitStack() as stack:
        wa = stack.enter_context(client.websocket_connect(f"/ws/{code}/DEV-A"))
        # wa gets 1st status (active: 1)
        st_a1 = wa.receive_json()
        assert st_a1["type"] == "status_update"
        
        wb = stack.enter_context(client.websocket_connect(f"/ws/{code}/DEV-B"))
        # wa gets 2nd status (active: 2)
        st_a2 = wa.receive_json()
        assert st_a2["type"] == "status_update"
        # wb gets 1st status (active: 2)
        st_b1 = wb.receive_json()
        assert st_b1["type"] == "status_update"
        
        msg_id = str(uuid.uuid4())
        wa.send_json({
            "type": "code_file",
            "message_id": msg_id,
            "sender_device_id": "DEV-A",
            "file_name": f"test_{size_name}.py",
            "language": "python",
            "content": content
        })
        
        # Sender receives ACK
        ack = wa.receive_json()
        while ack.get("type") == "status_update":
            ack = wa.receive_json()
        assert ack["type"] == "ack"
        
        # Receiver receives code_file
        recv_msg = wb.receive_json()
        while recv_msg.get("type") == "status_update":
            recv_msg = wb.receive_json()
            
        assert recv_msg["type"] == "code_file"
        received_content = recv_msg["content"]
        received_bytes = received_content.encode("utf-8")
        received_byte_size = len(received_bytes)
        received_sha256 = hashlib.sha256(received_bytes).hexdigest()
        
        # Exact assertions
        assert content == received_content
        assert original_byte_size == received_byte_size
        assert original_sha256 == received_sha256

def test_file_larger_than_10mb_rejected():
    code = "REJECT"
    res = client.post("/api/sessions/create", json={
        "email": "s@x.com", "name": "S", "device_id": "S-1", "device_name": "S", "session_code": code, "device_type": "cli"
    })
    assert res.status_code == 200
    res = client.post("/api/sessions/join", json={
        "email": "r@x.com", "name": "R", "device_id": "R-1", "device_name": "R", "session_code": code, "device_type": "cli"
    })
    assert res.status_code == 200

    # Content larger than 10 MB (10 MB + 100 KB)
    oversized_content = "A" * (10 * 1024 * 1024 + 100 * 1024)
    
    with ExitStack() as stack:
        wa = stack.enter_context(client.websocket_connect(f"/ws/{code}/S-1"))
        wa.receive_json() # status 1
        wb = stack.enter_context(client.websocket_connect(f"/ws/{code}/R-1"))
        wa.receive_json() # status 2
        wb.receive_json() # status 2
        
        wa.send_json({
            "type": "code_file",
            "message_id": str(uuid.uuid4()),
            "sender_device_id": "S-1",
            "file_name": "too_big.py",
            "language": "python",
            "content": oversized_content
        })
        
        err = wa.receive_json()
        while err.get("type") == "status_update":
            err = wa.receive_json()
            
        assert err["type"] == "error"
        assert "FILE TOO LARGE" in err["message"]
