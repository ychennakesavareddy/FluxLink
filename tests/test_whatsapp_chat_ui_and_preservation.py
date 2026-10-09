import pytest
import os
import json
import uuid
import tempfile
from contextlib import ExitStack
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import init_db, get_db
from chennalink.app import ChennaLinkApp
from chennalink.screens.chat import ChatScreen, ChatMessageCard
from chennalink.models.code_file import CodeFile
from chennalink.services.local_storage import LocalStorage

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

def test_exact_code_and_indentation_preservation():
    """Verify that Python code, tabs, spaces, newlines, HTML, and Unicode are preserved 100% byte-for-byte."""
    code = "PR" + uuid.uuid4().hex[:4].upper()
    
    # 1. Create session (Host)
    res_a = client.post("/api/sessions/create", json={
        "email": "host@example.com",
        "name": "Host-Dev",
        "device_id": "HOST-DEV-ID",
        "device_name": "Host-Dev",
        "session_code": code,
        "device_type": "cli"
    })
    assert res_a.status_code == 200
    uuid_a = res_a.json()["device_id"]
    session_id = res_a.json()["session_id"]
    
    # 2. Join session (Peer)
    res_b = client.post("/api/sessions/join", json={
        "email": "peer@example.com",
        "name": "Peer-Dev",
        "device_id": "PEER-DEV-ID",
        "device_name": "Peer-Dev",
        "session_code": code,
        "device_type": "web"
    })
    assert res_b.status_code == 200
    uuid_b = res_b.json()["device_id"]

    test_payloads = [
        # Prompt's exact Python indentation example
        (
            "python_indent.py",
            "python",
            'def example():\n    if True:\n        print("Hello")\n        if 2 > 1:\n            print("Indentation must remain exact")\n\n    print("This line is outside the if block")\n'
        ),
        # Mixed tabs and spaces + consecutive blank lines
        (
            "tabs_spaces.py",
            "python",
            "\tdef calculate():\n\t    x = 10\n        y = 20\n\n\n\t    return x + y\n"
        ),
        # Unicode, emojis, non-English text
        (
            "unicode_test.txt",
            "plaintext",
            "🚀 Chennalink Telugu: తెలుగు, Japanese: コンピュータ, Arabic: مرحبا, Math: ∑(x^2) = ∞\n"
        ),
        # HTML-like content with entities
        (
            "template.html",
            "html",
            '<div class="box">\n  <script>alert("exact & intact");</script>\n  <span>&amp; &lt; &gt;</span>\n</div>\n'
        ),
        # Leading / trailing spaces and whitespace on lines
        (
            "whitespace.py",
            "python",
            "   # 3 leading spaces\nx = 1    # 4 trailing spaces\n\n   \n# empty line with 3 spaces above\n"
        ),
    ]

    with ExitStack() as stack:
        ws_a = stack.enter_context(client.websocket_connect(f"/ws/{code}/{uuid_a}"))
        ws_a.receive_json() # status_update (1)

        ws_b = stack.enter_context(client.websocket_connect(f"/ws/{code}/{uuid_b}"))
        ws_a.receive_json() # status_update (2)
        ws_b.receive_json() # status_update (2)

        for filename, lang, payload in test_payloads:
            msg_id = str(uuid.uuid4())
            
            # Host sends to Peer
            ws_a.send_json({
                "type": "code_file",
                "message_id": msg_id,
                "sender_device_id": uuid_a,
                "file_name": filename,
                "language": lang,
                "content": payload
            })

            ack = ws_a.receive_json()
            assert ack["type"] == "ack"

            received = ws_b.receive_json()
            assert received["type"] == "code_file"
            assert received["file_name"] == filename
            # CRITICAL: Exact character-by-character equality
            assert received["content"] == payload, f"Failed exact preservation on {filename}"

        # Verify history preservation from API
        hist = client.get(f"/api/history/{session_id}?device_id={uuid_b}").json()
        assert len(hist["items"]) == len(test_payloads)


def test_session_lifecycle_host_end_and_disconnect():
    """Verify max 4 participants, host termination, participant disconnect, and history persistence."""
    code = "LF" + uuid.uuid4().hex[:4].upper()
    
    # 1. Host creates
    r_host = client.post("/api/sessions/create", json={
        "email": "host@test.com", "name": "Host", "device_id": "HOST-01",
        "device_name": "Host", "session_code": code, "device_type": "cli"
    })
    assert r_host.status_code == 200
    host_uuid = r_host.json()["device_id"]
    session_id = r_host.json()["session_id"]

    # 2. Join 4 peers
    peer_uuids = []
    for i in range(2, 6):
        r_p = client.post("/api/sessions/join", json={
            "email": f"peer{i}@test.com", "name": f"Peer-{i}", "device_id": f"PEER-0{i}",
            "device_name": f"Peer-{i}", "session_code": code, "device_type": "web"
        })
        assert r_p.status_code == 200
        peer_uuids.append(r_p.json()["device_id"])

    with ExitStack() as stack:
        ws_host = stack.enter_context(client.websocket_connect(f"/ws/{code}/{host_uuid}"))
        ws_host.receive_json() # status 1

        ws_p2 = stack.enter_context(client.websocket_connect(f"/ws/{code}/{peer_uuids[0]}"))
        ws_host.receive_json() # status 2
        ws_p2.receive_json() # status 2

        ws_p3 = stack.enter_context(client.websocket_connect(f"/ws/{code}/{peer_uuids[1]}"))
        ws_host.receive_json() # status 3
        ws_p2.receive_json()
        ws_p3.receive_json()

        ws_p4 = stack.enter_context(client.websocket_connect(f"/ws/{code}/{peer_uuids[2]}"))
        st_final = ws_host.receive_json() # status 4
        assert st_final["active_devices"] == 4
        ws_p2.receive_json() # status 4
        ws_p3.receive_json() # status 4
        ws_p4.receive_json() # status 4

        # 3. 5th active connection rejected (SESSION FULL: 1008)
        from starlette.websockets import WebSocketDisconnect
        try:
            with client.websocket_connect(f"/ws/{code}/{peer_uuids[3]}") as ws_p5:
                ws_p5.receive_json()
                assert False, "5th connection should have been rejected"
        except WebSocketDisconnect as exc_info:
            assert exc_info.code == 1008

        # Peer 2 sends a message to session
        ws_p2.send_json({
            "type": "code_file",
            "message_id": "msg-p2-test",
            "sender_device_id": peer_uuids[0],
            "file_name": "p2.txt",
            "content": "Message from peer 2 before session end"
        })
        ws_p2.receive_json() # ack
        # All connected peers and host receive message
        recv_host = ws_host.receive_json()
        assert recv_host["content"] == "Message from peer 2 before session end"
        recv_p3 = ws_p3.receive_json()
        assert recv_p3["content"] == "Message from peer 2 before session end"
        recv_p4 = ws_p4.receive_json()
        assert recv_p4["content"] == "Message from peer 2 before session end"

        # 4. Host ends session via WebSocket
        ws_host.send_json({"type": "end_session"})

        # All connected devices receive session_ended notification
        end_host = ws_host.receive_json()
        assert end_host["type"] == "session_ended"
        end_p2 = ws_p2.receive_json()
        assert end_p2["type"] == "session_ended"
        end_p3 = ws_p3.receive_json()
        assert end_p3["type"] == "session_ended"
        end_p4 = ws_p4.receive_json()
        assert end_p4["type"] == "session_ended"

    # 5. Subsequent join requests to ended session return 400
    res_rejoin = client.post("/api/sessions/join", json={
        "email": "peer2@test.com", "name": "Peer-2", "device_id": "PEER-02",
        "device_name": "Peer-2", "session_code": code, "device_type": "web"
    })
    assert res_rejoin.status_code == 400
    assert "This session has ended" in res_rejoin.json()["detail"]

    # 6. History remains fully accessible after session termination
    hist = client.get(f"/api/history/{session_id}?device_id={host_uuid}").json()
    assert len(hist["items"]) == 1
    assert hist["items"][0]["file_name"] == "p2.txt"


@pytest.mark.asyncio
async def test_chat_screen_tui_layout_and_load_file():
    """Verify that Textual ChatScreen renders WhatsApp-style cards, supports loading files by path, and preserves content."""
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = os.path.join(temp_dir, "history.json")
        sample_code_file = os.path.join(temp_dir, "sample.py")
        
        # Write exact multiline Python content with indentation
        sample_code = "def sample():\n    x = 42\n    if x > 0:\n        return 'Exact Indentation'\n"
        with open(sample_code_file, "w", encoding="utf-8") as f:
            f.write(sample_code)

        app = ChennaLinkApp()
        app.local_storage = LocalStorage(db_path=db_path)

        async with app.run_test(size=(100, 35)) as pilot:
            app.session_data.session_code = "CHATTUI"
            app.push_screen("chat")
            await pilot.pause()

            chat_screen = app.screen
            assert isinstance(chat_screen, ChatScreen)

            # Check composer components
            composer_filename = chat_screen.query_one("#composer_filename")
            composer_path = chat_screen.query_one("#composer_path")
            composer_text = chat_screen.query_one("#composer_text")
            
            # Load file by path
            composer_path.value = sample_code_file
            await pilot.click("#btn_load_file")
            await pilot.pause()

            # Content in composer must match exact source code
            assert composer_text.text == sample_code
            assert composer_filename.value == "sample.py"

            # Mock sending
            sent_messages = []
            async def mock_send(msg):
                sent_messages.append(msg)
                return True
            app.send_message = mock_send

            # Click send
            await pilot.click("#btn_send_chat")
            await pilot.pause()

            # Composer is cleared
            assert composer_text.text == ""

            # Check that ChatMessageCard was mounted
            cards = chat_screen.query(ChatMessageCard)
            assert len(cards) == 1
            card = cards.first()
            assert card.file.content == sample_code
            assert card.file.filename == "sample.py"

            # Check that local storage preserved exact content
            saved_files = await app.local_storage.get_all()
            assert len(saved_files) == 1
            assert saved_files[0].content == sample_code
