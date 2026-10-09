from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Vertical
from textual.widgets import Label, Button
from chennalink.widgets.header import AppHeader

class WelcomeScreen(Screen):
    def compose(self) -> ComposeResult:
        yield AppHeader()
        with Vertical(classes="session-container"):
            yield Label("What would you like to do?", classes="session-title")
            yield Button("CREATE SESSION", id="btn_create", variant="primary")
            yield Button("CONNECT SESSION", id="btn_connect", variant="success")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_create":
            self.app.switch_screen("create_session")
        elif event.button.id == "btn_connect":
            self.app.switch_screen("connect_session")
