from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Vertical, Horizontal
from textual.widgets import Label, Button
from textual.reactive import reactive

from chennalink.widgets.header import AppHeader

class WaitingScreen(Screen):
    
    def compose(self) -> ComposeResult:
        yield AppHeader()
        with Vertical(classes="session-container"):
            yield Label("SESSION CREATED", classes="session-title")
            
            yield Label("Connection Code:", classes="session-subtitle")
            yield Label("", id="lbl_code", classes="session-code-display")
            
            yield Label("", id="lbl_creator", classes="session-info-text")
            
            yield Label("● WAITING FOR SECOND DEVICE", id="lbl_status", classes="status-connecting")
            yield Label("Devices: 1 / 2", id="lbl_devices", classes="session-info-text")
            
            with Horizontal(classes="session-actions"):
                yield Button("CANCEL SESSION", id="btn_cancel", variant="error")

    def on_show(self) -> None:
        self.query_one("#lbl_code", Label).update(self.app.session_data.session_code)
        self.query_one("#lbl_creator", Label).update(f"Created by: {self.app.session_data.device_name}")
        self.update_status_display()
        
    def update_status_display(self):
        try:
            status = self.app.session_data.status
            # Extract device counts if possible
            if "DEVICES" in status:
                import re
                match = re.search(r'\((\d+)\s*/\s*(\d+)', status)
                if match:
                    active = match.group(1)
                    total = match.group(2)
                    self.query_one("#lbl_devices", Label).update(f"Devices: {active} / {total}")
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_cancel":
            if self.app.ws_task:
                self.app.ws_task.cancel()
            if self.app.ws:
                import asyncio
                asyncio.create_task(self.app.ws.close())
                
            self.app.session_data.session_code = ""
            self.app.session_data.session_id = None
            self.app.session_data.status = "OFFLINE"
            self.app.switch_screen("welcome")
