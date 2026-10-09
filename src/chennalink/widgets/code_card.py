from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Label, Button, Static
from textual.message import Message
from textual.reactive import reactive
from rich.syntax import Syntax

from chennalink.models.code_file import CodeFile

class CodeCard(Vertical):
    DEFAULT_CSS = """
    CodeCard {
        border: solid $accent;
        padding: 1;
        margin-bottom: 1;
        height: auto;
    }
    
    .card-header {
        height: auto;
        layout: horizontal;
        margin-bottom: 1;
    }
    
    .card-filename {
        width: 1fr;
        text-style: bold;
    }
    
    .card-meta {
        width: auto;
        color: $text-muted;
        text-align: right;
    }
    
    .card-sender {
        text-align: left;
        margin-bottom: 1;
    }
    
    .card-preview {
        height: 5;
        overflow: hidden;
        background: $surface;
        padding: 0 1;
        margin-bottom: 1;
    }
    
    .card-stats {
        color: $text-muted;
        text-align: right;
        margin-bottom: 1;
    }
    
    .card-actions {
        height: auto;
        align: right middle;
    }
    
    .card-actions Button {
        margin-left: 1;
    }
    """
    
    class CopyCode(Message):
        def __init__(self, content: str):
            super().__init__()
            self.content = content
            
    class SaveCode(Message):
        def __init__(self, file: CodeFile):
            super().__init__()
            self.file = file

    class ViewCode(Message):
        def __init__(self, file: CodeFile):
            super().__init__()
            self.file = file

    def __init__(self, file: CodeFile):
        super().__init__()
        self.file = file

    def compose(self) -> ComposeResult:
        with Horizontal(classes="card-header"):
            yield Label(f"📄 {self.file.filename}", classes="card-filename")
            time_str = self.file.timestamp.split("T")[1][:5] if "T" in self.file.timestamp else self.file.timestamp
            yield Label(time_str, classes="card-meta")
        
        yield Label(f"From: {self.file.sender}", classes="card-meta card-sender")
        
        # Preview first few lines
        lines = self.file.content.splitlines()
        preview_text = "\n".join(lines[:4])
        if len(lines) > 4:
            preview_text += "\n..."
            
        yield Static(Syntax(preview_text, self.file.language, theme="monokai", background_color="default"), classes="card-preview")
        
        file_size_kb = len(self.file.content.encode("utf-8")) / 1024
        yield Label(f"{len(lines)} lines · {file_size_kb:.1f} KB", classes="card-stats")
        
        with Horizontal(classes="card-actions"):
            yield Button("VIEW", id="btn_view")
            yield Button("COPY CODE", id="btn_copy", variant="primary")
            yield Button("SAVE", id="btn_save")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_copy":
            self.post_message(self.CopyCode(self.file.content))
        elif event.button.id == "btn_view":
            self.post_message(self.ViewCode(self.file))
        elif event.button.id == "btn_save":
            self.post_message(self.SaveCode(self.file))
