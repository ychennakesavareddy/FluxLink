from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Vertical, Horizontal, VerticalScroll
from textual.widgets import Label, Button, Static
from textual.binding import Binding
from rich.syntax import Syntax
from chennalink.models.code_file import CodeFile

class CodeViewerScreen(Screen):
    BINDINGS = [
        Binding("escape", "close_viewer", "Close", show=True),
    ]

    CSS = """
    CodeViewerScreen {
        background: $surface;
        padding: 1;
    }
    .viewer-header {
        height: 3;
        border-bottom: solid $primary;
        margin-bottom: 1;
    }
    .viewer-title {
        width: 1fr;
        text-style: bold;
    }
    .viewer-stats {
        width: auto;
        color: $text-muted;
    }
    .viewer-content {
        height: 1fr;
        border: solid $accent;
        overflow-x: auto;
        overflow-y: auto;
    }
    .viewer-actions {
        height: 3;
        align: left middle;
        margin-top: 1;
    }
    """

    def __init__(self, file: CodeFile):
        super().__init__()
        self.file = file

    def compose(self) -> ComposeResult:
        file_size_kb = len(self.file.content.encode("utf-8")) / 1024
        
        with Horizontal(classes="viewer-header"):
            yield Label(self.file.filename, classes="viewer-title")
            yield Label(f"{file_size_kb:.1f} KB · {self.file.language}", classes="viewer-stats")
            
        from textual.widgets import TextArea
        lang = self.file.language or "python"
        if file_size_kb > 100:
            lang = None # Disable syntax highlighting for massive files
            
        text_area = TextArea(text=self.file.content, language=lang, read_only=True, show_line_numbers=True)
        yield text_area
            
        with Horizontal(classes="viewer-actions"):
            yield Button("COPY CODE", id="btn_copy", variant="primary")
            yield Button("CLOSE", id="btn_close")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_copy":
            from chennalink.services.clipboard import copy_to_clipboard
            import asyncio
            success = await asyncio.to_thread(copy_to_clipboard, self.file.content)
            if success:
                self.app.notify("✓ Code copied")
            else:
                self.app.notify("✗ Failed to copy code", severity="error")
        elif event.button.id == "btn_close":
            self.action_close_viewer()
            
    def action_close_viewer(self):
        self.app.pop_screen()
