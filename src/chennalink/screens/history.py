from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import VerticalScroll, Horizontal, Vertical
from textual.widgets import Button, Input, Label, Static
from textual.message import Message
import httpx
from datetime import datetime, timedelta
import asyncio
from rich.syntax import Syntax

from chennalink.widgets.header import AppHeader, Navigation
from chennalink.widgets.status_bar import StatusBar
from chennalink.models.code_file import CodeFile
from chennalink.widgets.code_card import CodeCard

class HistoryCard(Vertical):
    DEFAULT_CSS = """
    HistoryCard {
        border: solid $accent;
        padding: 1;
        margin-bottom: 1;
        height: auto;
    }
    .hc-header { height: auto; layout: horizontal; margin-bottom: 1; }
    .hc-filename { width: 1fr; text-style: bold; }
    .hc-meta { width: auto; color: $text-muted; text-align: right; }
    .hc-sender { text-align: left; margin-bottom: 1; }
    .hc-preview { height: 5; overflow: hidden; background: $surface; padding: 0 1; margin-bottom: 1; }
    .hc-actions { height: auto; align: right middle; }
    .hc-actions Button { margin-left: 1; }
    """
    
    def __init__(self, msg: dict, device_id: str):
        super().__init__()
        self.msg = msg
        self.direction = msg.get("direction") or ("sent" if msg.get("sender_device_id") == device_id else "received")
        if self.direction == "sent":
            self.sender_label = "To: REMOTE"
        else:
            self.sender_label = "From: REMOTE"

    def compose(self) -> ComposeResult:
        filename = self.msg.get("file_name", "unknown")
        timestamp = self.msg.get("created_at", "")
        time_str = timestamp.split("T")[1][:5] if "T" in timestamp else timestamp
        content_preview = self.msg.get("preview", "")
        lang = self.msg.get("language", "python")
        size_bytes = self.msg.get("size_bytes", 0)

        with Horizontal(classes="hc-header"):
            yield Label(f"📄 {filename}", classes="hc-filename")
            yield Label(f"{size_bytes} B • {time_str}", classes="hc-meta")
        
        yield Label(self.sender_label, classes="hc-meta hc-sender")
        
        lines = content_preview.splitlines()
        preview_text = "\n".join(lines[:4])
        if len(lines) > 4 or len(content_preview) == 200:
            preview_text += "\n..."
        
        yield Static(Syntax(preview_text, lang, theme="monokai", background_color="default"), classes="hc-preview")
        
        with Horizontal(classes="hc-actions"):
            yield Button("VIEW", id=f"view_{self.msg['id']}")
            yield Button("COPY", id=f"copy_{self.msg['id']}", variant="primary")
            yield Button("RESEND", id=f"resend_{self.msg['id']}")
            yield Button("DELETE", id=f"delete_{self.msg['id']}", variant="error")

class HistoryScreen(Screen):
    DEFAULT_CSS = """
    .filter-bar {
        height: auto;
        layout: horizontal;
        margin: 1;
        align: left middle;
    }
    .filter-bar Button {
        margin-right: 1;
    }
    .active-filter {
        background: $accent;
        color: $text;
    }
    .search-bar {
        margin: 1;
    }
    .date-group {
        text-style: bold;
        color: $accent;
        margin-top: 1;
        margin-bottom: 1;
        margin-left: 1;
    }
    """
    
    def compose(self) -> ComposeResult:
        yield AppHeader()
        yield Navigation()
        
        yield Input(placeholder="Search history...", id="search_input", classes="search-bar")
        
        with Horizontal(classes="filter-bar"):
            yield Button("ALL", id="filter_all", classes="active-filter")
            yield Button("SENT", id="filter_sent")
            yield Button("RECEIVED", id="filter_received")
            
        with VerticalScroll(id="history_list"):
            yield Button("LOAD MORE", id="btn_load_more", variant="primary")
            
        yield StatusBar()

    def on_mount(self) -> None:
        self.history_offset = 0
        self.history_limit = 50
        self.all_items = []
        self.current_filter = "ALL"
        self.search_query = ""
        self._search_timer = None

    def on_show(self) -> None:
        self.history_offset = 0
        self.all_items = []
        self.query(HistoryCard).remove()
        self.query(Label).filter(".date-group").remove()
        self.run_worker(self.load_history())

    async def load_history(self):
        if not self.app.session_data.session_id:
            return
            
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(
                    f"{self.app.api_base}/history/{self.app.session_data.session_id}?device_id={self.app.session_data.device_id}&limit={self.history_limit}&offset={self.history_offset}"
                )
                if res.status_code == 200:
                    data = res.json()
                    new_items = data.get("items", [])
                    self.all_items.extend(new_items)
                    self.history_offset += len(new_items)
                    
                    await self.render_items()
                    
                    btn = self.query_one("#btn_load_more", Button)
                    if len(new_items) < self.history_limit:
                        btn.display = False
                    else:
                        btn.display = True
                        
        except Exception as e:
            self.app.notify(f"Failed to load history: {e}", severity="error")

    async def render_items(self):
        container = self.query_one("#history_list")
        btn = self.query_one("#btn_load_more")
        
        with self.app.batch_update():
            # Remove existing items
            for child in list(container.children):
                if child != btn:
                    child.remove()
            
            filtered = []
            for item in self.all_items:
                direction = item.get("direction") or ("sent" if item.get("sender_device_id") == self.app.session_data.device_id else "received")
                
                if self.current_filter == "SENT" and direction != "sent":
                    continue
                if self.current_filter == "RECEIVED" and direction != "received":
                    continue
                    
                if self.search_query:
                    sq = self.search_query.lower()
                    if sq not in item.get("file_name", "").lower() and sq not in item.get("content", "").lower():
                        continue
                        
                filtered.append(item)
                
            current_group = None
            for item in filtered:
                date_str = item.get("created_at", "")
                group = self.get_date_group(date_str)
                
                if group != current_group:
                    container.mount(Label(f"--- {group} ---", classes="date-group"), before=btn)
                    current_group = group
                    
                container.mount(HistoryCard(item, self.app.session_data.device_id), before=btn)

    def get_date_group(self, timestamp_str: str) -> str:
        if not timestamp_str:
            return "Unknown Date"
        try:
            if "T" in timestamp_str:
                dt_str = timestamp_str.split(".")[0]
                dt = datetime.fromisoformat(dt_str)
            else:
                dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            
            now = datetime.now()
            date_only = dt.date()
            today = now.date()
            yesterday = today - timedelta(days=1)
            
            if date_only == today:
                return "Today"
            elif date_only == yesterday:
                return "Yesterday"
            else:
                return date_only.strftime("%B %d, %Y")
        except Exception:
            return "Older"

    async def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search_input":
            self.search_query = event.value
            if self._search_timer is not None:
                self._search_timer.stop()
            self._search_timer = self.set_timer(0.3, self._do_search)
            
    async def _do_search(self):
        await self.render_items()

    async def fetch_full_content(self, msg_id: str) -> str:
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(f"{self.app.api_base}/history/{self.app.session_data.session_id}/{msg_id}?device_id={self.app.session_data.device_id}")
                if res.status_code == 200:
                    return res.json().get("content", "")
        except Exception as e:
            self.app.notify(f"Failed to fetch content: {e}", severity="error")
        return ""

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_load_more":
            await self.load_history()
        elif event.button.id in ("filter_all", "filter_sent", "filter_received"):
            for b in self.query(".filter-bar Button"):
                b.remove_class("active-filter")
            event.button.add_class("active-filter")
            
            self.current_filter = event.button.label.plain.upper()
            await self.render_items()
            
        elif event.button.id and event.button.id.startswith("view_"):
            msg_id = event.button.id.split("view_")[1]
            msg = next((m for m in self.all_items if str(m["id"]) == msg_id), None)
            if msg:
                content = await self.fetch_full_content(msg_id)
                direction = "sent" if msg.get("sender_device_id") == self.app.session_data.device_id else "received"
                sender = "LOCAL" if direction == "sent" else "REMOTE"
                cf = CodeFile(
                    id=msg["id"],
                    filename=msg.get("file_name", "unknown"),
                    content=content,
                    language=msg.get("language", "python"),
                    timestamp=msg.get("created_at", ""),
                    direction=direction,
                    status=msg.get("status", "delivered"),
                    sender=sender
                )
                self.post_message(CodeCard.ViewCode(cf))
                
        elif event.button.id and event.button.id.startswith("copy_"):
            msg_id = event.button.id.split("copy_")[1]
            content = await self.fetch_full_content(msg_id)
            if content:
                self.post_message(CodeCard.CopyCode(content))
                self.app.notify("Code copied to clipboard")
                
        elif event.button.id and event.button.id.startswith("resend_"):
            msg_id = event.button.id.split("resend_")[1]
            msg = next((m for m in self.all_items if str(m["id"]) == msg_id), None)
            content = await self.fetch_full_content(msg_id)
            if msg and content:
                self.app.notify(f"↑ Resending {msg.get('file_name')}...", timeout=1)
                try:
                    await self.app.send_file_chunked(msg.get("file_name", "unknown"), content, msg.get("language", "python"))
                    self.app.notify(f"✓ Resent {msg.get('file_name')}", timeout=2)
                except Exception as e:
                    self.app.notify(f"✗ Failed to resend: {e}", severity="error")
            
        elif event.button.id and event.button.id.startswith("delete_"):
            msg_id = event.button.id.split("delete_")[1]
            try:
                async with httpx.AsyncClient() as client:
                    res = await client.delete(f"{self.app.api_base}/history/{self.app.session_data.session_id}/{msg_id}?device_id={self.app.session_data.device_id}")
                    if res.status_code == 200:
                        self.app.notify("Deleted message")
                        self.all_items = [m for m in self.all_items if str(m["id"]) != msg_id]
                        await self.render_items()
            except Exception as e:
                self.app.notify(f"Failed to delete: {e}", severity="error")
