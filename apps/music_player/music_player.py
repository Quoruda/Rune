import os
import json
import asyncio
import math
import time
import random
from textual.widgets import Static, ProgressBar
from textual.app import ComposeResult
from textual.containers import Vertical
from textual import events

from core.window import Window


class MusicPlayer(Window):
    DEFAULT_CSS = """
    MusicPlayer {
        align: center middle;
        background: transparent;
    }
    MusicPlayer .player-card {
        width: 50;
        height: auto;
        border: none;
        padding: 1 2;
        background: transparent;
        align: center middle;
    }
    MusicPlayer Static {
        text-align: center;
        width: 100%;
    }
    MusicPlayer .title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    MusicPlayer .status {
        color: $text-muted;
    }
    MusicPlayer .wave {
        color: $accent;
        height: 4;
        margin: 1 0;
    }
    MusicPlayer ProgressBar {
        width: 100%;
        margin: 1 0;
        padding: 0;
    }
    MusicPlayer ProgressBar Bar {
        width: 100%;
        background: #3a3a3a;
        color: $accent;
    }
    MusicPlayer .help {
        color: $text-muted;
        margin-top: 1;
    }
    """

    def __init__(self, *args, **kwargs):
        super().__init__("Music Player", ">")
        self.file_path = args[0] if args else None
        self.process = None
        self.reader = None
        self.writer = None
        self.ipc_path = f"/tmp/rune_mpv_{os.getpid()}.sock"

        self.lbl_title = Static("No track loaded", classes="title")
        self.lbl_status = Static("Stopped", classes="status")
        self.lbl_wave = Static("", classes="wave")
        self.lbl_time = Static("--:-- / --:--")
        self.progress = ProgressBar(total=100, show_eta=False, show_percentage=False)

        self._current_pos = 0.0
        self._duration = 0.0
        self._is_paused = True

        if self.file_path:
            self.border_title = f"> Player - {os.path.basename(self.file_path)}"

        self.system_mode_overrides = ["left", "right"]

    def compose(self) -> ComposeResult:
        with Vertical(classes="player-card"):
            yield self.lbl_title
            yield self.lbl_status
            yield self.lbl_wave
            yield self.progress
            yield self.lbl_time
            yield Static("[Space] Play/Pause", classes="help")
            yield Static("[<-/->] Seek 5s", classes="help")

    async def on_mount(self) -> None:
        if not self.file_path or not os.path.exists(self.file_path):
            self.lbl_title.update("Error: File not found")
            return

        self.lbl_title.update(os.path.basename(self.file_path))
        self.lbl_status.update("Loading...")

        self.set_interval(0.08, self._update_wave)

        try:
            self.process = await asyncio.create_subprocess_exec(
                "mpv", "--no-video", "--keep-open=yes", f"--input-ipc-server={self.ipc_path}", self.file_path,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )

            for _ in range(20):
                if os.path.exists(self.ipc_path):
                    break
                await asyncio.sleep(0.1)

            self.reader, self.writer = await asyncio.open_unix_connection(self.ipc_path)

            await self._send_command(["observe_property", 1, "time-pos"])
            await self._send_command(["observe_property", 2, "duration"])
            await self._send_command(["observe_property", 3, "pause"])

            self.run_worker(self._reader_loop())
        except Exception as e:
            self.lbl_status.update(f"Error: {e}")

    async def _send_command(self, command_args: list) -> None:
        if not self.writer:
            return
        payload = {"command": command_args}
        try:
            self.writer.write((json.dumps(payload) + "\n").encode())
            await self.writer.drain()
        except (OSError, ConnectionError):
            self.writer = None
            self.reader = None

    async def _reader_loop(self) -> None:
        while self.reader and not self.reader.at_eof():
            try:
                line = await self.reader.readline()
                if not line:
                    break

                msg = json.loads(line.decode())
                if msg.get("event") == "property-change":
                    prop_name = msg.get("name")
                    prop_data = msg.get("data")

                    if prop_data is None:
                        continue

                    if prop_name == "time-pos":
                        self._current_pos = prop_data
                        self.progress.progress = prop_data
                        self._update_time_label()
                    elif prop_name == "duration":
                        self._duration = prop_data
                        self.progress.total = prop_data
                        self._update_time_label()
                    elif prop_name == "pause":
                        self._is_paused = prop_data
                        self.lbl_status.update("Paused" if prop_data else "Playing")
            except Exception:
                break
        self.lbl_status.update("Finished")
        self._is_paused = True

    def _update_wave(self) -> None:
        if self._is_paused:
            self.lbl_wave.update("\n\n\n" + "." * 44)
            return

        t = time.time()
        rows = 4
        cols = 44
        grid = [[" " for _ in range(cols)] for _ in range(rows)]

        for i in range(cols):
            val = 0.5 + 0.4 * math.sin(t * 12 + i * 0.4) * math.cos(t * 5 - i * 0.2)
            val += random.uniform(-0.1, 0.1)
            val = max(0.0, min(1.0, val))

            row_idx = int((1.0 - val) * (rows - 1))
            grid[row_idx][i] = "."

        lines = ["".join(row) for row in grid]
        self.lbl_wave.update("\n".join(lines))

    def _update_time_label(self) -> None:
        self.lbl_time.update(f"{self._format_time(self._current_pos)} / {self._format_time(self._duration)}")

    def _format_time(self, seconds: float) -> str:
        m, s = divmod(int(seconds), 60)
        return f"{m:02d}:{s:02d}"

    async def on_key(self, event: events.Key) -> None:
        if event.key == "space":
            event.stop()
            await self._send_command(["cycle", "pause"])
        elif event.key == "left":
            event.stop()
            await self._send_command(["seek", -5, "relative"])
        elif event.key == "right":
            event.stop()
            await self._send_command(["seek", 5, "relative"])

    async def on_unmount(self) -> None:
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass
        if self.process:
            try:
                self.process.terminate()
                await self.process.wait()
            except Exception:
                pass
        if os.path.exists(self.ipc_path):
            try:
                os.remove(self.ipc_path)
            except Exception:
                pass