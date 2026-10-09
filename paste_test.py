from textual.app import App
from textual.widgets import Label, TextArea

class PasteTest(App):
    def compose(self):
        yield Label("paste something", id="n")
        yield TextArea(id="t")

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        text = event.text_area.text
        self.query_one("#n", Label).update(
            f"{len(text)} chars, {len(text.encode('utf-8'))} bytes, {text.count(chr(10)) + 1} lines"
        )

PasteTest().run()
