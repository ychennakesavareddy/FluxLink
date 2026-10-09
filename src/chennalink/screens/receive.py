import inspect

from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import VerticalScroll

from chennalink.widgets.header import AppHeader, Navigation
from chennalink.widgets.status_bar import StatusBar
from chennalink.widgets.code_card import CodeCard


class ReceiveScreen(Screen):
    def compose(self) -> ComposeResult:
        yield AppHeader()
        yield Navigation()

        with VerticalScroll(id="receive_list"):
            pass

        yield StatusBar()

    def on_mount(self) -> None:
        self.run_worker(self.load_messages(), exclusive=True)

    async def load_messages(self) -> None:
        container = self.query_one("#receive_list")
        await container.query(CodeCard).remove()

        files = self.app.local_storage.get_all()
        if inspect.isawaitable(files):
            files = await files

        received = [f for f in files if getattr(f, "direction", "received") == "received"]
        cards = [CodeCard(f) for f in sorted(received, key=lambda x: x.timestamp, reverse=True)]
        if cards:
            await container.mount_all(cards)
