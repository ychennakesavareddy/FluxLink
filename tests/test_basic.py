import pytest
from chennalink.models.code_file import CodeFile
from chennalink.services.local_storage import LocalStorage
from chennalink.services.clipboard import copy_to_clipboard
import tempfile
import os

def test_create_code_file():
    code = "def test():\n    pass"
    f = CodeFile(filename="test.py", content=code)
    assert f.filename == "test.py"
    assert f.content == code
    assert f.language == "python"
    assert f.status == "sent"
    assert f.direction == "sent"

@pytest.mark.asyncio
async def test_local_storage():
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "history.json")
        storage = LocalStorage(db_path=db_path)
        
        f1 = CodeFile(filename="test1.py", content="print(1)")
        f2 = CodeFile(filename="test2.py", content="print(2)")
        
        await storage.save_file(f1)
        await storage.save_file(f2)
        
        files = await storage.get_all()
        assert len(files) == 2
        assert files[0].filename == "test1.py"
        assert files[1].filename == "test2.py"
        
        await storage.delete_file(f1.id)
        files = await storage.get_all()
        assert len(files) == 1
        assert files[0].filename == "test2.py"

def test_copy_clipboard(monkeypatch):
    # Mock pyperclip
    import pyperclip
    copied_text = ""
    def mock_copy(text):
        nonlocal copied_text
        copied_text = text
        
    monkeypatch.setattr(pyperclip, "copy", mock_copy)
    
    code = "def hello():\n    print('Hello World')\n\n\n"
    assert copy_to_clipboard(code) is True
    assert copied_text == code
