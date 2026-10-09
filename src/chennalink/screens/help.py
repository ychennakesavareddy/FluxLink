from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Vertical, VerticalScroll, Horizontal
from textual.widgets import Label, Button, Static
from textual.binding import Binding

from chennalink.widgets.header import AppHeader, Navigation
from chennalink.widgets.status_bar import StatusBar

HELP_TEXT = """
[bold cyan]FluxLink — High-Speed Real-Time Code & File Bridge[/bold cyan]

[bold yellow]Keyboard Navigation & Shortcuts[/bold yellow]
  [green]Ctrl + T[/green]  : WhatsApp-style Real-Time Chat Timeline
  [green]Ctrl + 1[/green]  : Send File / Source Code (Load path or paste code)
  [green]Ctrl + 2[/green]  : Receive Files (View incoming transfers & download)
  [green]Ctrl + 3[/green]  : History (Filter & inspect previous transfers)
  [green]Ctrl + 4[/green]  : Session Details (Participants, connection code & status)
  [green]Ctrl + H[/green]  : Help & Usage Screen
  [green]Ctrl + Q[/green]  : Quit FluxLink

[bold yellow]Command-Line Usage (Terminal / Kali Linux)[/bold yellow]
  [green]fluxlink[/green]                     : Launch interactive TUI
  [green]fluxlink send <path>[/green]         : Launch TUI with specified file queued
  [green]fluxlink receive[/green]             : Launch directly into Receive screen
  [green]fluxlink history[/green]             : Launch directly into History screen
  [green]fluxlink session[/green]             : Launch directly into Session screen
  [green]fluxlink --backend <url>[/green]     : Custom backend endpoint (Default: https://fluxlinkbackend.chennareddy.in)
  [green]fluxlink help[/green]                : Display this command line help

[bold yellow]Network & Production Endpoints[/bold yellow]
  • [bold]Frontend Web UI[/bold]   : https://fluxlink.chennareddy.in
  • [bold]Backend API[/bold]       : https://fluxlinkbackend.chennareddy.in
  • [bold]WebSocket Bridge[/bold]  : wss://fluxlinkbackend.chennareddy.in/ws
  • [bold]Local Fallback[/bold]    : Set FLUXLINK_BACKEND_URL=http://127.0.0.1:8000
"""

class HelpScreen(Screen):
    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("ctrl+h", "back", "Back"),
    ]

    DEFAULT_CSS = """
    HelpScreen {
        background: $surface;
    }
    .help-container {
        padding: 1 2;
        width: 80%;
        margin: 1 auto;
        border: solid $accent;
        height: 1fr;
    }
    .help-scroll {
        height: 1fr;
        padding-right: 1;
    }
    .help-actions {
        height: auto;
        align: center middle;
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield AppHeader()
        yield Navigation()

        with Vertical(classes="help-container"):
            with VerticalScroll(classes="help-scroll"):
                yield Static(HELP_TEXT)
            with Horizontal(classes="help-actions"):
                yield Button("BACK TO CHAT", id="btn_help_back", variant="primary")

        yield StatusBar()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_help_back":
            self.action_back()

    def action_back(self) -> None:
        if hasattr(self.app, "switch_screen"):
            self.app.switch_screen("chat")
        else:
            self.app.pop_screen()
