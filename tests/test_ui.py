import pytest
import os
import tempfile
from chennalink.app import ChennaLinkApp
from chennalink.services.local_storage import LocalStorage
from chennalink.screens.send import SendScreen

@pytest.mark.asyncio
async def test_add_to_queue():
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "history.json")
        app = ChennaLinkApp()
        app.local_storage = LocalStorage(db_path=db_path)
        
        async with app.run_test() as pilot:
            app.session_data.session_code = "TESTING"
            app.push_screen("send")
            await pilot.pause()
            
            send_screen = app.screen
            assert isinstance(send_screen, SendScreen)
            
            # Fill out form programmatically for test
            editor = send_screen.query_one("#editor")
            editor.query_one("#filename_input").value = "test.py"
            editor.query_one("#code_input").text = "print('hello')"
            
            # Click Add file
            await pilot.click("#btn_add")
            
            # Check queue
            assert len(send_screen.queue_files) == 1
            assert send_screen.queue_files[0].filename == "test.py"
            
            # Click send all
            # Wait, we need to mock send_message since it's an async operation using websockets.
            async def mock_send_chunked(filename, content, lang): return "mock_id_2"
            app.send_file_chunked = mock_send_chunked
            
            await send_screen.action_send_all()
            await pilot.pause()
            
            # Check queue is empty
            assert len(send_screen.queue_files) == 0
            
            # Check local storage
            saved = await app.local_storage.get_all()
            assert len(saved) == 1
            assert saved[0].filename == "test.py"
