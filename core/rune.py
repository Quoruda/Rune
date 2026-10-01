import mimetypes
from pathlib import Path
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.binding import Binding
from textual import events
from core.application_manager import ApplicationManager
from core.taskbar import Taskbar
from core.window import Window
from core.workspace import Workspace
from core.application_launcher import ApplicationLauncher
from core.registry import APP_REGISTRY
import asyncio
import json
import os
import sys
import fcntl



def resolve_file_app(file_path: str | Path) -> str:
    path_str = str(file_path)
    ext = os.path.splitext(path_str)[1].lower()

    if ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp']:
        return "viewer"
    elif ext in ['.mp3', '.wav', '.ogg', '.flac', '.m4a']:
        return "player"
    elif ext in ['.mp4', '.mkv', '.avi', '.mov', '.webm']:
        return "watcher"
    elif ext in ['.txt', '.py', '.rs', '.md', '.json', '.toml', '.yaml', '.yml', '.sh', '.js', '.ts', '.css', '.html']:
        return "editor"
    else:
        mimetypes.init()
        mime_type, _ = mimetypes.guess_type(path_str)
        if mime_type:
            if mime_type.startswith("image/"):
                return "viewer"
            elif mime_type.startswith("audio/"):
                return "player"
            elif mime_type.startswith("video/"):
                return "watcher"
        return "editor"

class Rune(App):
    ENABLE_COMMAND_PALETTE = False
    SOCKET_PATH = "/tmp/rune.sock"
    LOCK_PATH = "/tmp/rune.lock"
    DEFAULT_CSS = """
    Rune.zoom-active Window {
        display: none;
    }

    Rune.zoom-active Window.zoomed {
        display: block;
    }
    """

    BINDINGS = [
        Binding("ctrl+up", "navigate('up')", show=False, priority=True),
        Binding("ctrl+down", "navigate('down')", show=False, priority=True),
        Binding("ctrl+left", "navigate('left')", show=False, priority=True),
        Binding("ctrl+right", "navigate('right')", show=False, priority=True),
        Binding("ctrl+p", "show_launcher()", show=False, priority=True),
        Binding("ctrl+z", "toggle_zoom()", show=False, priority=True),
        Binding("ctrl+w", "close_active_window()", show=False, priority=True),
    ]

    def __init__(self):
        super().__init__()
        self._lock_file = None
        self._ensure_single_instance()
        self.workspace = Workspace()
        self.manager = ApplicationManager(self.workspace)

    def _ensure_single_instance(self) -> None:
        try:
            self._lock_file = open(self.LOCK_PATH, "w")
            fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Error: Another instance of Rune is already running.", file=sys.stderr)
            sys.exit(1)

    def compose(self) -> ComposeResult:
        yield self.workspace
        yield Taskbar()

    def on_mount(self) -> None:
        if self.screen.focusable:
            self.screen.focusable[0].focus()
        self.run_worker(self._start_ipc_server())

    def action_navigate(self, direction: str) -> None:
        focused = self.focused
        if not focused:
            return

        current_window = None
        if isinstance(focused, Window):
            current_window = focused
        else:
            for ancestor in focused.ancestors:
                if isinstance(ancestor, Window):
                    current_window = ancestor
                    break

        if not current_window:
            return

        current_reg = current_window.region
        windows = [w for w in self.screen.query(Window)]
        candidates = [w for w in windows if w is not current_window]
        best_candidate = None

        if direction == "right":
            right_side = [w for w in candidates if w.region.x >= current_reg.right]
            if right_side:
                best_candidate = min(right_side, key=lambda w: w.region.x)
        elif direction == "left":
            left_side = [w for w in candidates if w.region.right <= current_reg.x]
            if left_side:
                best_candidate = max(left_side, key=lambda w: w.region.right)
        elif direction == "up":
            above = [w for w in candidates if w.region.bottom <= current_reg.y]
            if above:
                best_candidate = max(above, key=lambda w: w.region.bottom)
        elif direction == "down":
            below = [w for w in candidates if w.region.y >= current_reg.bottom]
            if below:
                best_candidate = min(below, key=lambda w: w.region.y)

        if best_candidate:
            best_candidate.focus()

    def action_show_launcher(self) -> None:
        if isinstance(self.screen, ApplicationLauncher):
            return

        def handle_selection(app_entry: dict | None) -> None:
            if app_entry:
                new_app = app_entry["class"]()
                self.manager.add_application(new_app)
                new_app.focus()

        self.push_screen(ApplicationLauncher(APP_REGISTRY), handle_selection)

    def action_toggle_zoom(self) -> None:
        focused = self.focused
        if not focused:
            return

        current_window = None
        if isinstance(focused, Window):
            current_window = focused
        else:
            for ancestor in focused.ancestors:
                if isinstance(ancestor, Window):
                    current_window = ancestor
                    break

        if not current_window:
            return

        if self.has_class("zoom-active"):
            self.remove_class("zoom-active")
            current_window.remove_class("zoomed")
        else:
            self.add_class("zoom-active")
            current_window.add_class("zoomed")

    async def _start_ipc_server(self) -> None:
        if os.path.exists(self.SOCKET_PATH):
            os.remove(self.SOCKET_PATH)

        self.ipc_server = await asyncio.start_unix_server(
            self._handle_ipc_client,
            path=self.SOCKET_PATH
        )
        async with self.ipc_server:
            await self.ipc_server.serve_forever()

    async def _handle_ipc_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            data = await reader.read(4096)
            if data:
                payload = json.loads(data.decode())
                action = payload.get("action")
                if action == "run":
                    self.call_later(
                        self._open_app_by_name,
                        payload.get("app"),
                        payload.get("args", [])
                    )
                elif action == "open":
                    self.call_later(
                        self.open_file,
                        payload.get("path")
                    )
        except Exception:
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    def open_file(self, file_path: str | Path) -> None:
        abs_path = str(Path(file_path).resolve())
        app_name = resolve_file_app(abs_path)
        self._open_app_by_name(app_name, [abs_path])

    def _open_app_by_name(self, name: str, args: list = None) -> None:
        args = args or []
        for app in APP_REGISTRY:
            if app["name"].lower() == name.lower():
                new_app = app["class"](*args)
                self.manager.add_application(new_app)
                new_app.focus()
                break

    async def on_unmount(self) -> None:
        if os.path.exists(self.SOCKET_PATH):
            os.remove(self.SOCKET_PATH)

    @work
    async def action_close_active_window(self) -> None:
        focused = self.focused
        if not focused:
            return

        current_window = None
        if isinstance(focused, Window):
            current_window = focused
        else:
            for ancestor in focused.ancestors:
                if isinstance(ancestor, Window):
                    current_window = ancestor
                    break

        if current_window:
            if not await current_window.confirm_close():
                return
            if current_window in self.manager.applications:
                self.manager.applications.remove(current_window)
            current_window.remove()
    @work
    async def action_quit(self) -> None:
        for window in list(self.manager.applications):
            if not await window.confirm_close():
                window.focus()
                return
        self.exit()
