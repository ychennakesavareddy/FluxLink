from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Vertical, Horizontal
from textual.widgets import Label, Button
from chennalink.widgets.header import AppHeader, Navigation
from chennalink.widgets.status_bar import StatusBar
from chennalink.services.clipboard import copy_to_clipboard

class SessionScreen(Screen):
    def compose(self) -> ComposeResult:
        yield AppHeader()
        yield Navigation()
        
        with Vertical(classes="session-container"):
            yield Label("SESSION", classes="session-title")
            
            yield Label("Connection Code:", classes="session-subtitle")
            yield Label(self.app.session_data.session_code or "NONE", classes="session-code-display", id="lbl_session_code")
            
            yield Label("Your Device:", classes="session-subtitle")
            yield Label(self.app.session_data.device_name or "NONE", id="lbl_device_name")
            
            yield Label("Status:", classes="session-subtitle")
            yield Label(self.app.session_data.status, id="lbl_status")
            
            yield Label("Participants:", classes="session-subtitle")
            yield Label("", id="lbl_participants")
            
            with Horizontal(classes="session-actions"):
                yield Button("COPY CODE", id="btn_copy_code", variant="primary")
                yield Button("DISCONNECT", id="btn_disconnect_session", variant="warning")
                if getattr(self.app.session_data, "is_host", False):
                    yield Button("END SESSION", id="btn_end_session", variant="error")
                yield Button("QUIT", id="btn_leave", variant="error")
            
        yield StatusBar()
        
    def on_mount(self) -> None:
        self.update_status_display()
        self.update_participants()
        
    def update_status_display(self):
        try:
            self.query_one("#lbl_session_code", Label).update(self.app.session_data.session_code or "NONE")
            self.query_one("#lbl_device_name", Label).update(self.app.session_data.device_name or "NONE")
            self.query_one("#lbl_status", Label).update(self.app.session_data.status)
        except Exception:
            pass

    def update_participants(self):
        try:
            participants = getattr(self.app.session_data, "participants", [])
            lines = []
            for p in participants:
                marker = "●" if p.get("status") == "CONNECTED" else "○"
                name = p.get("device_name", "Unknown")
                ctype = p.get("device_type", "cli").upper()
                status = p.get("status", "DISCONNECTED").capitalize()
                lines.append(f"{marker} {name}\n  {ctype}\n  {status}")
            self.query_one("#lbl_participants", Label).update("\n\n".join(lines))
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_copy_code":
            if self.app.session_data.session_code:
                if copy_to_clipboard(self.app.session_data.session_code):
                    self.app.notify("✓ Code copied")
        elif event.button.id == "btn_disconnect_session":
            if self.app.ws_task:
                self.app.ws_task.cancel()
            if self.app.ws:
                import asyncio
                asyncio.create_task(self.app.ws.close())
            self.app.session_data.status = "DISCONNECTED"
            self.app.notify("Disconnected from session.")
            self.app.switch_screen("welcome")
        elif event.button.id == "btn_end_session":
            if self.app.ws:
                import json, asyncio
                asyncio.create_task(self.app.ws.send(json.dumps({"type": "end_session"})))
            self.app.notify("Session ended.")
            self.app.switch_screen("welcome")
        elif event.button.id == "btn_leave":
            self.app.exit()
