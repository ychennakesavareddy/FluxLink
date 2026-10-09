from textual.app import App
from textual.widgets import Button
from textual.binding import Binding
import os
import asyncio
import json
import websockets
import httpx
from uuid import uuid4

from chennalink.screens.chat import ChatScreen
from chennalink.screens.send import SendScreen
from chennalink.screens.receive import ReceiveScreen
from chennalink.screens.history import HistoryScreen
from chennalink.screens.session import SessionScreen
from chennalink.screens.welcome import WelcomeScreen
from chennalink.screens.create_session import CreateSessionScreen
from chennalink.screens.connect_session import ConnectSessionScreen
from chennalink.screens.waiting import WaitingScreen
from chennalink.screens.code_viewer import CodeViewerScreen
from chennalink.screens.help import HelpScreen
from chennalink.services.local_storage import LocalStorage
from chennalink.services.clipboard import copy_to_clipboard
from chennalink.widgets.code_card import CodeCard
from chennalink.models.session import Session
from chennalink.models.code_file import CodeFile

class ChennaLinkApp(App):
    CSS = """
    Screen { background: $surface; }
    .left-pane { width: 60%; height: 100%; padding: 1; }
    .right-pane { width: 40%; height: 100%; padding: 1; }
    .editor-actions { height: auto; align: left middle; }
    .editor-actions Button { margin-right: 1; }
    .queue-actions { height: auto; align: right middle; }
    .session-container { padding: 2; width: 60%; margin: 2 0; border: solid $accent; }
    .session-title { text-style: bold; margin-bottom: 2; text-align: center; }
    .session-subtitle { text-style: bold; margin-top: 1; }
    .session-code-display { text-style: bold; color: $success; margin: 1 0; text-align: center; }
    .session-info-text { margin-bottom: 1; }
    .status-connecting { color: $warning; margin-top: 2; margin-bottom: 1; }
    .session-info { height: 1; margin-bottom: 1; }
    .session-info Label { width: 1fr; }
    .session-value { text-align: right; }
    .session-actions { height: auto; margin-top: 2; align: center middle; }
    .session-actions Button { margin: 0 1; }
    .status-offline { color: $warning; }
    .status-connected { color: $success; }
    .status-reconnecting { color: $warning; }
    
    Notification {
        dock: top;
        layer: overlay;
        width: 100%;
        height: auto;
        background: $primary;
        color: $text;
        text-align: center;
        padding: 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+t", "switch_screen('chat')", "Chat", show=True),
        Binding("ctrl+1", "switch_screen('send')", "Send", show=True),
        Binding("ctrl+2", "switch_screen('receive')", "Receive", show=True),
        Binding("ctrl+3", "switch_screen('history')", "History", show=True),
        Binding("ctrl+4", "switch_screen('session')", "Session", show=True),
        Binding("ctrl+h", "switch_screen('help')", "Help", show=True),
        Binding("ctrl+q", "quit", "Quit", show=True),
    ]

    SCREENS = {
        "welcome": WelcomeScreen,
        "create_session": CreateSessionScreen,
        "connect_session": ConnectSessionScreen,
        "waiting": WaitingScreen,
        "chat": ChatScreen,
        "send": SendScreen,
        "receive": ReceiveScreen,
        "history": HistoryScreen,
        "session": SessionScreen,
        "code_viewer": CodeViewerScreen,
        "help": HelpScreen,
    }

    def __init__(self, send_file_on_startup=None, backend_url=None, initial_screen=None, **kwargs):
        super().__init__(**kwargs)
        self.send_file_on_startup = send_file_on_startup
        self.initial_screen = initial_screen
        self.local_storage = LocalStorage()
        import random
        device_id = self.local_storage.get_device_id()
        if not device_id:
            device_id = f"LAPTOP-{random.randint(1000, 9999)}"
            self.local_storage.save_device_id(device_id)
            
        self.session_data = Session(device_id=device_id, device_name=device_id)
        
        default_backend = "https://fluxlinkbackend.chennareddy.in"
        if os.environ.get("FLUXLINK_ENV") == "development" or os.environ.get("CHENNALINK_ENV") == "development" or "PYTEST_CURRENT_TEST" in os.environ:
            default_backend = "http://127.0.0.1:8000"

        resolved_backend = (
            backend_url
            or os.environ.get("FLUXLINK_BACKEND_URL")
            or os.environ.get("CHENNALINK_BACKEND_URL")
            or default_backend
        ).rstrip("/")
        
        self.backend_url = resolved_backend
        self.api_base = f"{resolved_backend}/api"
        ws_proto = "wss" if resolved_backend.startswith("https") else "ws"
        host_port = resolved_backend.split("://")[-1]
        self.ws_base = f"{ws_proto}://{host_port}/ws"
        self.ws = None
        self.ws_task = None
        self.ping_task = None

    def on_mount(self) -> None:
        if self.initial_screen and self.initial_screen in self.SCREENS:
            self.push_screen(self.initial_screen)
        else:
            self.push_screen("welcome")
        self.update_status_bars()
        
        if self.send_file_on_startup:
            # We queue it once the UI loads and connect happens
            pass # handled when SendScreen loads if we want, or we can push it to LocalStorage queue.
            # Easiest way is to have SendScreen pick it up.
            
    def get_startup_file(self):
        f = self.send_file_on_startup
        self.send_file_on_startup = None # only once
        return f

    def update_status_bars(self):
        for screen in self.SCREENS.values():
            if hasattr(screen, "status_bar"):
                # We will update status bar reactive variables
                pass
        # simpler: just update via a message or broadcast
        # Textual screens can query App's session_data.

    def action_switch_screen(self, screen_name: str) -> None:
        if not self.session_data.session_code and screen_name in ["chat", "send", "receive", "history", "session"]:
            self.notify("You must connect to a session first.", severity="warning")
            return
        self.switch_screen(screen_name)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "nav_chat":
            self.action_switch_screen("chat")
        elif event.button.id == "nav_send":
            self.action_switch_screen("send")
        elif event.button.id == "nav_receive":
            self.action_switch_screen("receive")
        elif event.button.id == "nav_history":
            self.action_switch_screen("history")
        elif event.button.id == "nav_session":
            self.action_switch_screen("session")
        elif event.button.id == "nav_quit":
            self.exit()

    def on_code_card_copy_code(self, message: CodeCard.CopyCode) -> None:
        if copy_to_clipboard(message.content):
            self.notify("✓ Code copied", timeout=2)
        else:
            self.notify("✗ Failed to copy code", severity="error")

    def on_code_card_view_code(self, message: CodeCard.ViewCode) -> None:
        self.push_screen(CodeViewerScreen(message.file))

    def on_code_card_save_code(self, message: CodeCard.SaveCode) -> None:
        import os
        try:
            with open(message.file.filename, "w", encoding="utf-8") as f:
                f.write(message.file.content)
            self.notify(f"✓ Saved to {os.path.abspath(message.file.filename)}", timeout=3)
        except Exception as e:
            self.notify(f"✗ Could not save file: {e}", severity="error")

    async def connect_ws(self):
        if not self.session_data.session_code or not self.session_data.device_id:
            return
            
        url = f"{self.ws_base}/{self.session_data.session_code}/{self.session_data.device_id}"
        
        import os
        max_mb = int(os.environ.get("CHENNALINK_MAX_FILE_SIZE_MB", "10"))
        # Account for Base64 (+33%) and JSON envelope overhead
        max_bytes = max(20 * 1024 * 1024, max_mb * 1024 * 1024 * 2)
        
        while True:
            try:
                self.session_data.status = "CONNECTING"
                self.update_status()
                
                async with websockets.connect(url, max_size=max_bytes) as ws:
                    self.ws = ws
                    self.session_data.status = "CONNECTED"
                    self.update_status()
                    
                    if hasattr(self.screen, "sync_from_server"):
                        self.run_worker(self.screen.sync_from_server())
                    
                    if self.ping_task:
                        self.ping_task.cancel()
                    self.ping_task = asyncio.create_task(self.ws_ping_loop())

                    while True:
                        msg = await ws.recv()
                        await self.handle_ws_message(msg)
                        
            except websockets.exceptions.InvalidStatusCode as e:
                self.ws = None
                if e.status_code == 403:
                    self.session_data.status = "SESSION FULL"
                    self.update_status()
                    self.notify("SESSION FULL: Maximum 4 active connections.", severity="error")
                    return # Stop retrying
                self.session_data.status = "CONNECTION LOST"
                self.update_status()
                await asyncio.sleep(5)
            except websockets.exceptions.ConnectionClosed as e:
                self.ws = None
                if e.code == 1008:
                    self.session_data.status = "SESSION FULL"
                    self.update_status()
                    self.notify("SESSION FULL: Maximum 4 active connections.", severity="error")
                    return # Stop retrying
                self.session_data.status = "⚠ Connection lost"
                self.update_status()
                self.notify("↻ Reconnecting...", severity="warning")
                await asyncio.sleep(2) # Backoff
            except Exception as e:
                self.ws = None
                self.session_data.status = "⚠ Connection lost"
                self.update_status()
                self.notify("↻ Reconnecting...", severity="warning")
                await asyncio.sleep(5)

    async def ws_ping_loop(self):
        while self.ws:
            try:
                await asyncio.sleep(30)
                if self.ws:
                    await self.ws.send(json.dumps({"type": "ping"}))
            except:
                break

    def update_status(self):
        status_text = self.session_data.status
        status_display = f"[red]● {status_text}[/red]"
        if status_text.startswith("CONNECTED"):
            status_display = f"[green]● {status_text}[/green]"
        elif status_text.startswith("RECONNECT"):
            status_display = f"[yellow]↻ {status_text}[/yellow]"
        elif status_text.startswith("CONNECTING") or status_text.startswith("WAITING"):
            status_display = f"[yellow]● {status_text}[/yellow]"
        elif status_text == "DISCONNECTED" or status_text == "OFFLINE" or status_text == "CONNECTION LOST":
            status_display = f"[red]⚠ {status_text}[/red]"
            
        if self.screen:
            try:
                for header in self.screen.query("AppHeader"):
                    header.status = status_display
            except:
                pass
                
            try:
                for bar in self.screen.query("StatusBar"):
                    bar.session = self.session_data.session_code
                    bar.device = self.session_data.device_name
                    bar.status = status_display
            except:
                pass
            
            # Update waiting screen if it is active
            if hasattr(self.screen, "update_status_display"):
                self.screen.update_status_display()

    async def handle_ws_message(self, data: str):
        msg = json.loads(data)
        msg_type = msg.get("type")
        
        if msg_type == "status_update":
            active = msg.get("active_devices", 1)
            total = msg.get("total_devices", 4)
            participants = msg.get("participants", [])
            self.session_data.participants = participants
            
            if active == total:
                self.session_data.status = f"SESSION FULL ({active} / {total} DEVICES)"
            else:
                self.session_data.status = f"CONNECTED ({active} / {total} DEVICES)"
                
            self.update_status()
            
            if active >= 2:
                if not isinstance(self.screen, (ChatScreen, SendScreen, ReceiveScreen, HistoryScreen, SessionScreen)):
                    self.notify("Connected to session! Entering chat...")
                    self.switch_screen("chat")
            
            # If we are on the session screen, notify it to re-render participants
            if isinstance(self.screen, SessionScreen) and hasattr(self.screen, "update_participants"):
                self.screen.update_participants()
            
        elif msg_type == "session_ended":
            self.notify("The host has ended the session.", title="Session Ended", severity="warning")
            if self.ws:
                asyncio.create_task(self.ws.close())
            self.session_data.status = "SESSION ENDED"
            self.switch_screen("welcome")
            
        elif msg_type == "code_file":
            await self.process_incoming_file(msg)
            
        elif msg_type == "file_bundle":
            files = msg.get("files", [])
            for f in files:
                m = msg.copy()
                m["file_name"] = f.get("file_name")
                m["content"] = f.get("content")
                m["language"] = f.get("language", "python")
                await self.process_incoming_file(m)
                
        elif msg_type == "device_joined":
            self.notify("A device joined the session.")
            
    async def process_incoming_file(self, msg):
        import uuid
        file = CodeFile(
            id=msg.get("message_id", str(uuid.uuid4())),
            filename=msg.get("file_name"),
            content=msg.get("content"),
            language=msg.get("language", "python"),
            timestamp=msg.get("created_at"),
            direction="received",
            status="delivered",
            sender=msg.get("sender_device_id", "REMOTE")
        )
        await self.local_storage.save_file(file)
        
        if self.ws:
            asyncio.create_task(self.ws.send(json.dumps({"type": "ack", "message_id": msg.get("message_id")})))
            
        self.notify(f"🔵 NEW CODE RECEIVED: {file.filename}", title="New Message", timeout=5)
        
        if hasattr(self.screen, "add_message"):
            self.screen.add_message(file)
        elif self.screen.name == "receive":
            if hasattr(self.screen, "load_messages"):
                self.screen.load_messages()

    async def send_message(self, msg_dict: dict):
        if self.ws and self.session_data.status.startswith("CONNECTED"):
            await self.ws.send(json.dumps(msg_dict))
            return True
        else:
            self.notify("Cannot send: not fully connected", severity="error")
            return False

    async def send_file_chunked(self, file_name: str, content: str, language: str = "python"):
        if not self.ws or not self.session_data.status.startswith("CONNECTED"):
            self.notify("Cannot send: not fully connected", severity="error")
            return False
            
        import uuid
        import base64
        import hashlib
        import math
        
        content_bytes = content.encode("utf-8")
        file_size = len(content_bytes)
        sha256 = hashlib.sha256(content_bytes).hexdigest()
        transfer_id = str(uuid.uuid4())
        
        chunk_size = 256 * 1024 # 256KB chunks
        total_chunks = math.ceil(file_size / chunk_size)
        
        # 1. Send file_start
        await self.ws.send(json.dumps({
            "type": "file_start",
            "transfer_id": transfer_id,
            "file_name": file_name,
            "file_size": file_size,
            "total_chunks": total_chunks,
            "sha256": sha256,
            "language": language
        }))
        
        # 2. Send chunks
        for i in range(total_chunks):
            start = i * chunk_size
            end = min(start + chunk_size, file_size)
            chunk_data = base64.b64encode(content_bytes[start:end]).decode("ascii")
            
            await self.ws.send(json.dumps({
                "type": "file_chunk",
                "transfer_id": transfer_id,
                "index": i,
                "chunk": chunk_data
            }))
            
        # 3. Send file_end
        await self.ws.send(json.dumps({
            "type": "file_end",
            "transfer_id": transfer_id
        }))
        
        return transfer_id

def main():
    app = ChennaLinkApp()
    app.run()

if __name__ == "__main__":
    main()
