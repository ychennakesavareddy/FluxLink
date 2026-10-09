from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import TextArea, Input, Label

class CodeEditor(Vertical):
    DEFAULT_CSS = """
    CodeEditor {
        height: 1fr;
        border: solid $accent;
        padding: 1;
        margin: 1 0;
    }
    
    CodeEditor > Input {
        margin-bottom: 1;
    }
    .editor-stats {
        width: 1fr;
        text-align: right;
        color: $text-muted;
    }
    """
    
    def compose(self) -> ComposeResult:
        from textual.containers import Horizontal
        with Horizontal(classes="editor-header"):
            yield Label("File name")
            yield Input(placeholder="e.g. main.py", id="filename_input")
            
        with Horizontal():
            yield Label("Code")
            yield Label("0 lines | 0 bytes", id="editor_stats", classes="editor-stats")
        
        # Using TextArea for multiline code editing, which supports 
        # scrolling, selection, pasting etc out of the box in Textual.
        text_area = TextArea(id="code_input", language="python", show_line_numbers=True)
        yield text_area

    def on_text_area_changed(self, event) -> None:
        self.update_stats()

    def update_stats(self):
        text = self.query_one("#code_input", TextArea).text
        lines = len(text.splitlines()) if text else 0
        bytes_len = len(text.encode("utf-8")) if text else 0
        try:
            self.query_one("#editor_stats", Label).update(f"{lines} lines | {bytes_len} bytes")
        except:
            pass

    def get_filename(self) -> str:
        return self.query_one("#filename_input", Input).value
        
    def get_code(self) -> str:
        return self.query_one("#code_input", TextArea).text
        
    def clear(self):
        self.query_one("#filename_input", Input).value = ""
        self.query_one("#code_input", TextArea).text = ""
        self.update_stats()

    def on_paste(self, event) -> None:
        # Handle large pastes efficiently
        event.stop()
        text_area = self.query_one("#code_input", TextArea)
        text_area.text = event.text
        self.update_stats()
