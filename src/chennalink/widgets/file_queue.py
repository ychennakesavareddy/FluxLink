from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Label, Button, Static
from textual.message import Message

class FileQueueItem(Horizontal):
    DEFAULT_CSS = """
    FileQueueItem {
        height: 3;
        align: left middle;
        padding: 0 1;
        margin: 1 0;
        border: solid $boost;
    }
    .filename {
        width: 1fr;
    }
    .filesize {
        width: 12;
        text-align: right;
        color: $text-muted;
    }
    Button {
        margin-left: 1;
        min-width: 10;
    }
    """
    
    class RemoveItem(Message):
        def __init__(self, item_id: str):
            super().__init__()
            self.item_id = item_id

    def __init__(self, file_id: str, filename: str, size_bytes: int = 0):
        super().__init__()
        self.file_id = file_id
        self.filename = filename
        self.size_bytes = size_bytes

    def compose(self) -> ComposeResult:
        size_str = f"{self.size_bytes / 1024:.1f} KB" if self.size_bytes else ""
        yield Label(f"✓ {self.filename}", classes="filename")
        yield Label(size_str, classes="filesize")
        yield Button("VIEW", id=f"view_{self.file_id}", classes="view-btn")
        yield Button("REMOVE", id=f"remove_{self.file_id}", variant="error", classes="remove-btn")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.has_class("remove-btn"):
            self.post_message(self.RemoveItem(self.file_id))
        elif event.button.has_class("view-btn"):
            # Implement view if needed, or emit message
            pass

class FileQueueList(Vertical):
    DEFAULT_CSS = """
    FileQueueList {
        height: auto;
        max-height: 10;
        overflow-y: auto;
        margin-bottom: 1;
    }
    """
    pass

class FileQueue(Vertical):
    DEFAULT_CSS = """
    FileQueue {
        height: auto;
        padding: 1;
        border: solid $accent;
    }
    .queue-title {
        text-style: bold;
        margin-bottom: 1;
    }
    """
    
    def compose(self) -> ComposeResult:
        yield Label("FILES READY", classes="queue-title")
        yield FileQueueList(id="queue_list")
