import asyncio
import inspect
import os
from pathlib import Path

from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Vertical, Horizontal
from textual.widgets import Button, Input
from textual.binding import Binding

from chennalink.widgets.header import AppHeader, Navigation
from chennalink.widgets.status_bar import StatusBar
from chennalink.widgets.code_editor import CodeEditor
from chennalink.widgets.file_queue import FileQueue, FileQueueItem, FileQueueList
from chennalink.models.code_file import CodeFile

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


def max_file_mb() -> int:
    try:
        return int(os.environ.get("CHENNALINK_MAX_FILE_SIZE_MB", "10"))
    except ValueError:
        return 10


async def maybe_await(value):
    """Works whether a storage method is sync or async."""
    if inspect.isawaitable(value):
        return await value
    return value


class SendScreen(Screen):
    BINDINGS = [
        Binding("ctrl+n", "new_file", "New File"),
        Binding("ctrl+s", "send", "Send", show=False),
        Binding("ctrl+a", "send_all", "Send All", show=False),
    ]

    DEFAULT_CSS = """
    SendScreen .open-row { height: auto; }
    SendScreen .open-row Input { width: 1fr; }
    SendScreen .open-row Button { width: auto; }
    """

    def compose(self) -> ComposeResult:
        yield AppHeader()
        yield Navigation()

        with Horizontal():
            with Vertical(classes="left-pane"):
                with Horizontal(classes="open-row"):
                    yield Input(
                        placeholder="Open file by path, e.g. C:\\code\\main.py (Enter to load)",
                        id="path_input",
                    )
                    yield Button("OPEN FILE", id="btn_open")
                yield CodeEditor(id="editor")
                with Horizontal(classes="editor-actions"):
                    yield Button("SEND", id="btn_send", variant="primary")
                    yield Button("+ ADD FILE", id="btn_add")

            with Vertical(classes="right-pane"):
                yield FileQueue(id="queue")
                with Horizontal(classes="queue-actions"):
                    yield Button("SEND ALL", id="btn_send_all", variant="primary")

        yield StatusBar()

    def on_mount(self) -> None:
        self.queue_files = []

        # Load startup file if any (chennalink <path>)
        if hasattr(self.app, "get_startup_file"):
            startup_file = self.app.get_startup_file()
            if startup_file and os.path.isfile(startup_file):
                self.run_worker(self._load_path(Path(startup_file)), exclusive=False)

    # ------------------------------------------------------------------
    # Loading a file from disk (no terminal paste involved)
    # ------------------------------------------------------------------
    @staticmethod
    def _read_text(path: Path) -> str:
        # newline="" keeps LF / CRLF exactly as they are on disk
        with open(path, "r", encoding="utf-8", newline="") as f:
            return f.read()

    async def _load_path(self, path: Path) -> None:
        max_mb = max_file_mb()
        try:
            size = path.stat().st_size
        except OSError as e:
            self.app.notify(f"✗ Cannot open file: {e}", severity="error")
            return
        if size > max_mb * 1024 * 1024:
            self.app.notify(f"✗ FILE TOO LARGE (max {max_mb} MB)", severity="error")
            return
        try:
            content = await asyncio.to_thread(self._read_text, path)
        except UnicodeDecodeError:
            self.app.notify("✗ Not a UTF-8 text file", severity="error")
            return
        except OSError as e:
            self.app.notify(f"✗ Cannot read file: {e}", severity="error")
            return

        editor = self.query_one("#editor", CodeEditor)
        editor.query_one("#filename_input").value = path.name
        editor.query_one("#code_input").text = content
        lines = content.count("\n") + (0 if content.endswith("\n") or not content else 1)
        self.app.notify(f"Loaded {path.name}: {lines} lines, {size / 1024:.1f} KB")

    async def _open_from_input(self) -> None:
        raw = self.query_one("#path_input", Input).value.strip().strip('"').strip("'")
        if not raw:
            self.app.notify("Enter a file path first", severity="warning")
            return
        path = Path(os.path.expandvars(os.path.expanduser(raw)))
        if not path.is_file():
            self.app.notify(f"✗ File not found: {path}", severity="error")
            return
        await self._load_path(path)

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------
    async def _send_one(self, filename: str, code: str, language: str) -> bool:
        try:
            msg_id = await self.app.send_file_chunked(filename, code, language)
            if not msg_id:
                return False
            record = CodeFile(
                id=msg_id,
                filename=filename,
                content=code,
                language=language,
                direction="sent",
                status="sent",
            )
            await maybe_await(self.app.local_storage.save_file(record))
            return True
        except Exception as e:  # keep the UI alive, report cleanly
            self.app.notify(f"✗ Transfer failed: {e}", severity="error")
            return False

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "path_input":
            await self._open_from_input()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        editor = self.query_one("#editor", CodeEditor)

        if event.button.id == "btn_open":
            await self._open_from_input()

        elif event.button.id == "btn_add":
            queue_list = self.query_one("#queue_list", FileQueueList)
            filename = editor.get_filename()
            code = editor.get_code()
            if not filename:
                self.app.notify("Enter a file name", severity="warning")
                return
            if not code:
                self.app.notify("Nothing to add", severity="warning")
                return
            max_mb = max_file_mb()
            if len(code.encode("utf-8")) > max_mb * 1024 * 1024:
                self.app.notify(f"✗ FILE TOO LARGE (max {max_mb} MB)", severity="error")
                return
            file = CodeFile(filename=filename, content=code, language=language_for(filename))
            self.queue_files.append(file)
            queue_list.mount(FileQueueItem(file.id, file.filename, len(code.encode("utf-8"))))
            editor.clear()
            self.app.notify(f"Added {filename} to queue", timeout=2)

        elif event.button.id == "btn_send":
            filename = editor.get_filename()
            code = editor.get_code()
            if not filename:
                self.app.notify("Enter a file name", severity="warning")
                return
            if not code:
                self.app.notify("Nothing to send", severity="warning")
                return
            max_mb = max_file_mb()
            if len(code.encode("utf-8")) > max_mb * 1024 * 1024:
                self.app.notify(f"✗ FILE TOO LARGE (max {max_mb} MB)", severity="error")
                return

            btn = self.query_one("#btn_send", Button)
            btn.disabled = True
            try:
                self.app.notify(f"↑ Sending {filename}...", timeout=1)
                ok = await self._send_one(filename, code, language_for(filename))
            finally:
                btn.disabled = False

            if ok:
                self.app.notify(f"✓ Sent {filename}", timeout=2)
                editor.clear()
            else:
                self.app.notify("✗ Transfer failed. Your code was kept in the editor.", severity="error")

        elif event.button.id == "btn_send_all":
            if not self.queue_files:
                return
            queue_list = self.query_one("#queue_list", FileQueueList)
            self.app.notify(f"↑ Sending {len(self.queue_files)} files...", timeout=1)

            sent_ids = set()
            for file in list(self.queue_files):
                if await self._send_one(file.filename, file.content, file.language):
                    sent_ids.add(file.id)

            self.queue_files = [f for f in self.queue_files if f.id not in sent_ids]
            for item in list(queue_list.query(FileQueueItem)):
                if item.file_id in sent_ids:
                    item.remove()

            failed = len(self.queue_files)
            if failed:
                self.app.notify(
                    f"✓ Sent {len(sent_ids)} files, ✗ {failed} failed (kept in queue)",
                    severity="warning",
                )
            else:
                self.app.notify(f"✓ Sent {len(sent_ids)} files", timeout=2)

    def on_file_queue_item_remove_item(self, message: FileQueueItem.RemoveItem) -> None:
        self.queue_files = [f for f in self.queue_files if f.id != message.item_id]
        for item in self.query(FileQueueItem):
            if item.file_id == message.item_id:
                item.remove()

    def action_new_file(self):
        editor = self.query_one("#editor", CodeEditor)
        editor.clear()
        editor.query_one("#filename_input").focus()

    async def action_send(self):
        btn = self.query_one("#btn_send", Button)
        await self.on_button_pressed(Button.Pressed(btn))

    async def action_send_all(self):
        btn = self.query_one("#btn_send_all", Button)
        await self.on_button_pressed(Button.Pressed(btn))
