import pytest
import os
import tempfile
import asyncio
from chennalink.app import ChennaLinkApp
from chennalink.services.local_storage import LocalStorage
from tests.fixtures.make_code import make_code

@pytest.mark.asyncio
@pytest.mark.parametrize("lines", [150, 300, 2000, 5000, 10000])
@pytest.mark.parametrize("kind", ["ascii", "unicode", "crlf", "mixed_endings"])
async def test_end_to_end_huge_files(lines, kind):
    # Simulate end-to-end send/receive bytes via the UI code
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "history.json")
        app = ChennaLinkApp()
        app.local_storage = LocalStorage(db_path=db_path)
        
        async with app.run_test() as pilot:
            app.session_data.session_code = "TESTING"
            app.push_screen("send")
            await pilot.pause()
            
            send_screen = app.screen
            
            # Generate the file content
            content = make_code(lines, kind)
            
            # We bypass UI input for speed in unit test, just queue it
            from chennalink.models.code_file import CodeFile
            file = CodeFile(filename=f"test_{lines}.py", content=content, language="python")
            send_screen.queue_files.append(file)
            
            sent_payloads = []
            # We mock the WS send to capture chunks
            async def mock_send(msg_text):
                import json
                msg = json.loads(msg_text)
                sent_payloads.append(msg)
                return True
                
            # Connect the mock
            class MockWS:
                async def send(self, data):
                    await mock_send(data)
            
            app.ws = MockWS()
            app.session_data.status = "CONNECTED"
            
            await pilot.click("#btn_send_all")
            await pilot.pause()
            
            assert len(send_screen.queue_files) == 0
            
            # The chunks should reconstruct to exact string
            file_start = next(p for p in sent_payloads if p["type"] == "file_start")
            chunks = sorted([p for p in sent_payloads if p["type"] == "file_chunk"], key=lambda x: x["index"])
            file_end = next(p for p in sent_payloads if p["type"] == "file_end")
            
            import base64
            assembled_bytes = b"".join(base64.b64decode(c["chunk"]) for c in chunks)
            
            # Verify file_start size
            assert file_start["file_size"] == len(content.encode("utf-8"))
            
            # Verify string equality
            assert assembled_bytes.decode("utf-8") == content
