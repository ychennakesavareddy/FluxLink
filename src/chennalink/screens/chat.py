import asyncio
import inspect
import logging
import os
from pathlib import Path
from datetime import datetime

from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Vertical, Horizontal, VerticalScroll
from textual.widgets import Label, Button, Input, TextArea, Static
from textual.binding import Binding
from rich.syntax import Syntax

from chennalink.widgets.header import AppHeader, Navigation
from chennalink.widgets.status_bar import StatusBar
from chennalink.widgets.code_card import CodeCard
from chennalink.models.code_file import CodeFile
from chennalink.services.clipboard import copy_to_clipboard

logger = logging.getLogger("chennalink.chat")

LANGUAGES = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".json": "json",
    ".md": "markdown",
    ".html": "html",
    ".css": "css",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".go": "go",
    ".rs": "rust",
    ".sql": "sql",
    ".sh": "bash",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".toml": "toml",
}

def language_for(filename: str) -> str:
    return LANGUAGES.get(os.path.splitext(filename)[1].lower(), "python")


class ChatMessageCard(Vertical):
    DEFAULT_CSS = """
    ChatMessageCard {
        padding: 1 2;
        height: auto;
        border: solid $accent;
        width: 76%;
        max-width: 80%;
    }
    
    ChatMessageCard.incoming {
        border: solid $primary;
        background: $surface;
    }
    
    ChatMessageCard.outgoing {
        border: solid $success;
        background: $surface-darken-1;
    }
    
    .chat-card-header {
        height: auto;
        layout: horizontal;
        margin-bottom: 1;
    }
    
    .chat-card-sender {
        width: 1fr;
        text-style: bold;
    }
    
    .incoming .chat-card-sender {
        color: $primary;
    }
    
    .outgoing .chat-card-sender {
        color: $success;
    }
    
    .chat-card-meta {
        width: auto;
        color: $text-muted;
        text-align: right;
    }
    
    .chat-card-file {
        text-style: bold;
        color: $warning;
        margin-bottom: 1;
    }
    
    .chat-card-preview {
        height: auto;
        max-height: 10;
        background: $surface-darken-2;
        padding: 0 1;
        margin: 1 0;
        border: solid $surface-lighten-1;
    }
    
    .chat-card-stats {
        color: $text-muted;
        text-align: right;
        margin-bottom: 1;
    }
    
    .chat-card-actions {
        height: auto;
        align: right middle;
        margin-top: 1;
    }
    
    .chat-card-actions Button {
        margin-left: 1;
    }
    """

    def __init__(self, file: CodeFile):
        super().__init__()
        self.file = file
        is_outgoing = getattr(file, "direction", "received") == "sent"
        self.add_class("incoming" if not is_outgoing else "outgoing")

    def compose(self) -> ComposeResult:
        is_outgoing = getattr(self.file, "direction", "received") == "sent"
        time_str = ""
        if self.file.timestamp:
            time_str = self.file.timestamp.split("T")[1][:5] if "T" in self.file.timestamp else self.file.timestamp

        with Horizontal(classes="chat-card-header"):
            sender_label = "You" if is_outgoing else f"From: {self.file.sender}"
            yield Label(sender_label, classes="chat-card-sender")
            yield Label(time_str, classes="chat-card-meta")

        if self.file.filename and self.file.filename not in ["message.txt", "untitled.txt"]:
            yield Label(f"📄 {self.file.filename}", classes="chat-card-file")

        # Preview lines safely preserving exact whitespace
        lines = self.file.content.splitlines()
        preview_text = "\n".join(lines[:8])
        if len(lines) > 8:
            preview_text += "\n... [Click VIEW for full code]"

        yield Static(Syntax(preview_text, self.file.language or "plaintext", theme="monokai", background_color="default"), classes="chat-card-preview")

        file_size_kb = len(self.file.content.encode("utf-8")) / 1024
        yield Label(f"{len(lines)} lines · {file_size_kb:.1f} KB", classes="chat-card-stats")

        with Horizontal(classes="chat-card-actions"):
            yield Button("VIEW", id="btn_view")
            yield Button("COPY", id="btn_copy", variant="primary")
            yield Button("SAVE", id="btn_save")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_copy":
            self.post_message(CodeCard.CopyCode(self.file.content))
        elif event.button.id == "btn_view":
            self.post_message(CodeCard.ViewCode(self.file))
        elif event.button.id == "btn_save":
            self.post_message(CodeCard.SaveCode(self.file))


class ChatRow(Horizontal):
    DEFAULT_CSS = """
    ChatRow {
        height: auto;
        width: 100%;
        margin-bottom: 1;
    }
    ChatRow.incoming {
        align-horizontal: left;
    }
    ChatRow.outgoing {
        align-horizontal: right;
    }
    """

    def __init__(self, file: CodeFile):
        super().__init__()
        self.file = file
        is_outgoing = getattr(file, "direction", "received") == "sent"
        self.add_class("outgoing" if is_outgoing else "incoming")

    def compose(self) -> ComposeResult:
        yield ChatMessageCard(self.file)


class ChatScreen(Screen):
    BINDINGS = [
        Binding("ctrl+s", "send_message", "Send", show=False),
        Binding("ctrl+l", "load_file", "Load File", show=False),
        Binding("ctrl+q", "quit", "Quit", show=False),
    ]

    DEFAULT_CSS = """
    ChatScreen {
        background: $surface;
        layout: vertical;
    }
    
    #chat_timeline {
        height: 1fr;
        padding: 1;
        overflow-y: scroll;
    }
    
    .composer-container {
        height: auto;
        border-top: solid $primary;
        background: $surface-darken-1;
        padding: 0 1;
    }
    
    .composer-row {
        height: 8;
    }
    
    .composer-left {
        width: 20%;
        height: 8;
        padding-right: 1;
    }
    
    .composer-left Input {
        margin-bottom: 0;
    }
    
    .composer-left Button {
        width: 100%;
    }
    
    .composer-right {
        width: 80%;
        height: 8;
    }
    
    .composer-right TextArea {
        height: 8;
    }
    
    .composer-actions {
        height: auto;
        margin-top: 1;
        align: left middle;
    }
    
    .composer-actions Button {
        margin-right: 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.known_message_ids = set()

    def compose(self) -> ComposeResult:
        yield AppHeader()
        yield Navigation()

        with VerticalScroll(id="chat_timeline"):
            pass

        # Fixed Bottom Composer: EXACT 20% / 80% Layout
        with Vertical(classes="composer-container"):
            with Horizontal(classes="composer-row"):
                with Vertical(classes="composer-left"):
                    yield Input(placeholder="File name...", id="composer_filename")
                    yield Input(placeholder="Path to file...", id="composer_path")
                    yield Button("LOAD FILE", id="btn_load_file")
                with Vertical(classes="composer-right"):
                    yield TextArea(id="composer_text")
            
            with Horizontal(classes="composer-actions"):
                yield Button("SEND", id="btn_send_chat", variant="primary")
                yield Button("CLEAR", id="btn_clear_chat")
                yield Button("HISTORY", id="btn_history_chat")
                yield Button("SESSION", id="btn_session_chat")
                yield Button("DISCONNECT", id="btn_disconnect_chat", variant="warning")
                yield Button("END SESSION", id="btn_end_session_chat", variant="error")
                yield Button("QUIT", id="btn_quit_chat")

        yield StatusBar()

    def on_mount(self) -> None:
        self.run_worker(self.load_history(), exclusive=True)

    async def load_history(self) -> None:
        timeline = self.query_one("#chat_timeline")
        await timeline.query(ChatRow).remove()
        self.known_message_ids.clear()

        # 1. First load any cached local files
        files = self.app.local_storage.get_all()
        if inspect.isawaitable(files):
            files = await files

        for f in sorted(files, key=lambda x: x.timestamp or ""):
            self.known_message_ids.add(f.id)
            timeline.mount(ChatRow(f))

        timeline.scroll_end(animate=False)

        # 2. Sync from server as source of truth
        await self.sync_from_server()

    async def sync_from_server(self) -> None:
        session_id = self.app.session_data.session_id or self.app.session_data.session_code
        device_id = self.app.session_data.device_id
        if not session_id or not device_id:
            return

        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(
                    f"{self.app.api_base}/history/{session_id}",
                    params={"device_id": device_id, "limit": 100}
                )
                if res.status_code == 200:
                    data = res.json()
                    items = data.get("items", [])
                    # Sort ascending by created_at for chronological chat order
                    items.sort(key=lambda x: x.get("created_at") or "")

                    timeline = self.query_one("#chat_timeline")
                    new_count = 0
                    for item in items:
                        msg_id = item["id"]
                        if msg_id in self.known_message_ids:
                            continue

                        code_file = CodeFile(
                            id=msg_id,
                            filename=item.get("file_name") or "message.txt",
                            language=item.get("language", "python"),
                            content=item.get("content", ""),
                            timestamp=item.get("created_at"),
                            direction=item.get("direction", "received"),
                            status=item.get("status", "delivered"),
                            sender=item.get("peer_name") or item.get("sender_device_id") or "Remote"
                        )

                        await self.app.local_storage.save_file(code_file)
                        self.known_message_ids.add(msg_id)
                        timeline.mount(ChatRow(code_file))
                        new_count += 1

                    if new_count > 0:
                        timeline.scroll_end(animate=False)
        except Exception as e:
            logger.warning(f"Server history sync failed: {e}")

    def add_message(self, file: CodeFile) -> None:
        if file.id in self.known_message_ids:
            return
        self.known_message_ids.add(file.id)
        timeline = self.query_one("#chat_timeline")
        timeline.mount(ChatRow(file))
        timeline.scroll_end(animate=False)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_send_chat":
            await self.action_send_message()
        elif event.button.id == "btn_load_file":
            self.action_load_file()
        elif event.button.id == "btn_clear_chat":
            self.query_one("#composer_text", TextArea).text = ""
            self.query_one("#composer_filename", Input).value = ""
        elif event.button.id == "btn_history_chat":
            self.app.switch_screen("history")
        elif event.button.id == "btn_session_chat":
            self.app.switch_screen("session")
        elif event.button.id == "btn_disconnect_chat":
            self.action_disconnect()
        elif event.button.id == "btn_end_session_chat":
            await self.action_end_session()
        elif event.button.id == "btn_quit_chat":
            self.app.exit()

    def action_load_file(self) -> None:
        path_input = self.query_one("#composer_path", Input)
        path = path_input.value.strip()
        if not path:
            self.app.notify("Enter a file path to load", severity="warning")
            return

        if not os.path.isfile(path):
            self.app.notify(f"File not found: {path}", severity="error")
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            filename_input = self.query_one("#composer_filename", Input)
            if not filename_input.value.strip():
                filename_input.value = os.path.basename(path)

            self.query_one("#composer_text", TextArea).text = content
            self.app.notify(f"✓ Loaded {os.path.basename(path)} ({len(content)} chars)")
        except Exception as e:
            self.app.notify(f"Could not read file: {e}", severity="error")

    async def action_send_message(self) -> None:
        text_area = self.query_one("#composer_text", TextArea)
        filename_input = self.query_one("#composer_filename", Input)
        
        # Exact content without strip()
        content = text_area.text
        filename = filename_input.value.strip() or "message.txt"

        if not content:
            self.app.notify("Cannot send: message is empty", severity="warning")
            return

        lang = language_for(filename)
        byte_size = len(content.encode("utf-8"))

        max_mb = int(os.environ.get("CHENNALINK_MAX_FILE_SIZE_MB", "10"))
        if byte_size > max_mb * 1024 * 1024:
            self.app.notify(f"✗ FILE TOO LARGE: Maximum allowed size is {max_mb} MB", severity="error")
            return

        import uuid
        msg_id = str(uuid.uuid4())
        
        # Send via chunked if > 5KB, else code_file
        if byte_size > 5 * 1024:
            transfer_id = await self.app.send_file_chunked(filename, content, lang)
            if not transfer_id:
                return
            msg_id = transfer_id
        else:
            payload = {
                "type": "code_file",
                "message_id": msg_id,
                "session_id": self.app.session_data.session_id or "",
                "sender_device_id": self.app.session_data.device_name,
                "file_name": filename,
                "content": content,
                "language": lang,
            }
            success = await self.app.send_message(payload)
            if not success:
                return

        code_file = CodeFile(
            id=msg_id,
            filename=filename,
            language=lang,
            content=content,
            timestamp=datetime.now().isoformat(),
            direction="sent",
            status="sent",
            sender="You"
        )

        await self.app.local_storage.save_file(code_file)
        self.add_message(code_file)

        # Clear inputs
        text_area.text = ""
        filename_input.value = ""
        self.app.notify(f"✓ Sent {filename}")

    def action_disconnect(self) -> None:
        if self.app.ws_task:
            self.app.ws_task.cancel()
        if self.app.ws:
            asyncio.create_task(self.app.ws.close())
        self.app.session_data.status = "DISCONNECTED"
        self.app.notify("Disconnected from session.")
        self.app.switch_screen("welcome")

    async def action_end_session(self) -> None:
        if not getattr(self.app.session_data, "is_host", False):
            self.app.notify("Only the host can end the session.", severity="error")
            return

        try:
            if self.app.ws:
                import json
                await self.app.ws.send(json.dumps({"type": "end_session"}))
            else:
                import httpx
                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"{self.app.api_base}/sessions/end",
                        json={
                            "session_code": self.app.session_data.session_code,
                            "device_id": self.app.session_data.device_id
                        }
                    )
            self.app.notify("Session ended for all participants.")
            self.action_disconnect()
        except Exception as e:
            self.app.notify(f"Error ending session: {e}", severity="error")
