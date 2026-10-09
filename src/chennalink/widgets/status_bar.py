from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Label
from textual.reactive import reactive

class StatusBar(Horizontal):
    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        dock: bottom;
        background: $boost;
        color: $text;
        padding: 0 1;
        layout: horizontal;
    }
    
    StatusBar > Label {
        margin-right: 4;
    }
    
    .status-right {
        color: $success;
        width: 1fr;
        text-align: right;
    }
    """
    
    session = reactive("LOCAL")
    device = reactive("LAPTOP")
    status = reactive("● ONLINE")
    
    def compose(self) -> ComposeResult:
        yield Label(f"Session: {self.session}", id="status_session")
        yield Label(f"Device: {self.device}", id="status_device")
        yield Label(self.status, classes="status-right", id="status_status")
        
    def watch_session(self, session: str) -> None:
        try:
            self.query_one("#status_session", Label).update(f"Session: {session}")
        except Exception:
            pass
        
    def watch_device(self, device: str) -> None:
        try:
            self.query_one("#status_device", Label).update(f"Device: {device}")
        except Exception:
            pass
            
    def watch_status(self, status: str) -> None:
        try:
            self.query_one("#status_status", Label).update(status)
        except Exception:
            pass
