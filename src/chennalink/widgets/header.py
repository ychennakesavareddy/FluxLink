from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Label, Button
from textual.reactive import reactive

class AppHeader(Horizontal):
    DEFAULT_CSS = """
    AppHeader {
        height: 3;
        dock: top;
        background: $boost;
        color: $text;
        align: left middle;
        padding: 0 2;
        border-bottom: solid $primary;
    }
    
    .title {
        text-style: bold;
        width: 1fr;
    }
    
    .status {
        color: $success;
        text-align: right;
        width: auto;
    }
    """
    
    status = reactive("● CONNECTED")
    
    def compose(self) -> ComposeResult:
        yield Label("CHENNALINK", classes="title")
        yield Label(self.status, classes="status")

class Navigation(Horizontal):
    DEFAULT_CSS = """
    Navigation {
        height: 3;
        align: center middle;
        margin: 1 0;
    }
    Navigation Button {
        margin: 0 2;
        min-width: 16;
    }
    """
    
    def compose(self) -> ComposeResult:
        yield Button("CHAT (Ctrl+T)", id="nav_chat", variant="primary")
        yield Button("SEND (Ctrl+1)", id="nav_send")
        yield Button("RECEIVE (Ctrl+2)", id="nav_receive")
        yield Button("HISTORY (Ctrl+3)", id="nav_history")
        yield Button("SESSION (Ctrl+4)", id="nav_session")
        yield Button("QUIT (Ctrl+Q)", id="nav_quit", variant="error")
