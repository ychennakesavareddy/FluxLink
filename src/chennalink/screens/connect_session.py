from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Vertical, Horizontal
from textual.widgets import Label, Button, Input
import httpx
import asyncio

from chennalink.widgets.header import AppHeader

class ConnectSessionScreen(Screen):
    def compose(self) -> ComposeResult:
        yield AppHeader()
        with Vertical(classes="session-container"):
            yield Label("CONNECT SESSION", classes="session-title")
            
            yield Label("Email ID:")
            yield Input(placeholder="user@example.com", id="input_email")
            
            yield Label("Name:")
            yield Input(placeholder="Your Name", id="input_name")
            
            yield Label("Connection Code:")
            yield Input(placeholder="e.g. X7K9P2", id="input_code")
            
            with Horizontal(classes="session-actions"):
                yield Button("CONNECT", id="btn_submit", variant="success")
                yield Button("BACK", id="btn_back")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_back":
            self.app.switch_screen("welcome")
        elif event.button.id == "btn_submit":
            email = self.query_one("#input_email", Input).value.strip()
            name = self.query_one("#input_name", Input).value.strip()
            code = self.query_one("#input_code", Input).value.strip().upper()
            
            if not email or not name or not code:
                self.app.notify("Please fill all fields", severity="error")
                return
                
            self.app.session_data.email = email
            self.app.session_data.device_name = name
            
            try:
                async with httpx.AsyncClient() as client:
                    res = await client.post(
                        f"{self.app.api_base}/sessions/join",
                        json={
                            "email": email,
                            "name": name,
                            "device_id": self.app.session_data.device_id,
                            "device_name": name,
                            "session_code": code,
                            "device_type": "cli"
                        }
                    )
                    
                    if res.status_code == 200:
                        data = res.json()
                        self.app.session_data.session_id = data.get("session_id")
                        self.app.session_data.session_code = data["session_code"]
                        self.app.session_data.device_id = data["device_id"]
                        self.app.session_data.is_host = False
                        self.app.notify("Joined Session")
                        
                        if self.app.ws_task:
                            self.app.ws_task.cancel()
                        self.app.ws_task = asyncio.create_task(self.app.connect_ws())
                        
                        # Note: Transition to send screen is handled in app.py when status_update arrives and active_devices >= 2
                    else:
                        self.app.notify(f"Error: {res.json().get('detail', res.text)}", severity="error")
            except Exception as e:
                self.app.notify(f"Connection error: {e}", severity="error")
