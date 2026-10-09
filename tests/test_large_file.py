import pytest
import os
import tempfile
import asyncio
from chennalink.app import ChennaLinkApp
from chennalink.services.local_storage import LocalStorage
from chennalink.screens.send import SendScreen
import json

@pytest.mark.asyncio
async def test_large_file_ui_queue():
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "history.json")
        app = ChennaLinkApp()
        app.local_storage = LocalStorage(db_path=db_path)
        
        async with app.run_test() as pilot:
            app.session_data.session_code = "TESTING"
            app.push_screen("send")
            await pilot.pause()
            
            send_screen = app.screen
            
            # Generate 1 MB content
            content_1mb = "x" * (1024 * 1024)
            
            # Fill form
            editor = send_screen.query_one("#editor")
            editor.query_one("#filename_input").value = "large.py"
            editor.query_one("#code_input").text = content_1mb
            
            # Click Add
            await pilot.click("#btn_add")
            await pilot.pause()
            
            # Check queue
            assert len(send_screen.queue_files) == 1
            assert len(send_screen.queue_files[0].content) == 1024 * 1024
            
            # Simulate sending via mock
            sent_payloads = []
            async def mock_send_chunked(filename, content, lang):
                sent_payloads.append(content)
                return "mock_id"
                
            app.send_file_chunked = mock_send_chunked
            
            await pilot.click("#btn_send_all")
            await pilot.pause()
            
            # Queue should be empty
            assert len(send_screen.queue_files) == 0
            
            # Message should have full content
            assert len(sent_payloads) == 1
            assert len(sent_payloads[0]) == 1024 * 1024

@pytest.mark.asyncio
async def test_exact_content_preservation():
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "history.json")
        storage = LocalStorage(db_path=db_path)
        
        content = "def test():\n    print('తెలుగు 🚀')\n\n\n"
        from chennalink.models.code_file import CodeFile
        import uuid
        f = CodeFile(id=str(uuid.uuid4()), filename="unicode.py", content=content, status="sent")
        
        await storage.save_file(f)
        saved = await storage.get_all()
        assert len(saved) == 1
        assert saved[0].content == content
