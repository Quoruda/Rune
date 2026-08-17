import os
import cv2
import json
import asyncio
import time
import shutil
from textual.widgets import Static
from textual.app import ComposeResult
from textual import events
from textual.strip import Strip
from rich.segment import Segment
from rich.text import Text
import native

from core.window import Window


def format_time(seconds: float) -> str:
    if seconds is None or seconds < 0:
        return "00:00"
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class VideoPlayer(Window):

    def __init__(self, *args, **kwargs):
        super().__init__("Watcher", "W")
        self.file_path = args[0] if args else None
        
        # MPV Audio control
        self.mpv_process = None
        self.reader = None
        self.writer = None
        self.ipc_path = f"/tmp/rune_video_mpv_{os.getpid()}.sock"
        self.duration = 0.0
        self.volume = 100.0
        self.is_muted = False
        
        # OpenCV Video engine
        self.cap = None
        self.fps = 30.0
        self.is_paused = True
        self.current_time_pos = 0.0
        self._last_sync_wall_time = time.monotonic()
        
        # Error messages & states
        self.error_message = None
        
        # Rendering cache
        self.cached_strips = []
        self.needs_immediate_seek = False
        self.cap_lock = asyncio.Lock()
        
        if self.file_path:
            self.border_title = f"W Watcher - {os.path.basename(self.file_path)}"

    def compose(self) -> ComposeResult:
        return []

    async def on_mount(self) -> None:
        if not self.file_path or not os.path.exists(self.file_path):
            self.error_message = f"Error: File not found\n'{self.file_path}'"
            self.refresh()
            return
            
        if not shutil.which("mpv"):
            self.error_message = "Error: 'mpv' is not installed.\nPlease install mpv to use Watcher."
            self.refresh()
            return
            
        self.cap = cv2.VideoCapture(self.file_path)
        if not self.cap.isOpened():
            self.error_message = f"Error: Failed to open video file\n'{self.file_path}'"
            self.refresh()
            return
            
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        
        try:
            self.mpv_process = await asyncio.create_subprocess_exec(
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
            await self._send_command(["observe_property", 2, "pause"])
            await self._send_command(["observe_property", 3, "duration"])
            await self._send_command(["observe_property", 4, "volume"])
            await self._send_command(["observe_property", 5, "mute"])
            
            self.run_worker(self._mpv_reader_loop())
            self.run_worker(self._video_render_loop())
        except Exception as e:
            self.error_message = f"Error starting MPV: {e}"
            self.refresh()

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

    def get_current_playback_time(self) -> float:
        if self.is_paused:
            return self.current_time_pos
        elapsed = time.monotonic() - self._last_sync_wall_time
        return self.current_time_pos + min(elapsed, 1.0)

    async def _mpv_reader_loop(self) -> None:
        while self.reader and not self.reader.at_eof():
            try:
                line = await self.reader.readline()
                if not line:
                    break
                msg = json.loads(line.decode())
                if msg.get("event") == "property-change":
                    prop_name = msg.get("name")
                    prop_data = msg.get("data")
                    if prop_name == "time-pos" and prop_data is not None:
                        estimated_time = self.get_current_playback_time()
                        if abs(prop_data - estimated_time) > 0.5:
                            self.needs_immediate_seek = True
                        self.current_time_pos = prop_data
                        self._last_sync_wall_time = time.monotonic()
                    elif prop_name == "pause" and prop_data is not None:
                        self.is_paused = prop_data
                        self._last_sync_wall_time = time.monotonic()
                    elif prop_name == "duration" and prop_data is not None:
                        self.duration = prop_data
                    elif prop_name == "volume" and prop_data is not None:
                        self.volume = prop_data
                    elif prop_name == "mute" and prop_data is not None:
                        self.is_muted = prop_data
            except Exception:
                break

    async def _video_render_loop(self) -> None:
        frame_duration = 1.0 / self.fps
        last_displayed_frame = -1
        
        while self.cap and self.cap.isOpened():
            current_time = self.get_current_playback_time()
            target_frame = int(current_time * self.fps)
            
            if self.is_paused:
                if target_frame != last_displayed_frame:
                    async with self.cap_lock:
                        await asyncio.to_thread(self.cap.set, cv2.CAP_PROP_POS_FRAMES, target_frame)
                        ret, frame = await asyncio.to_thread(self.cap.read)
                    if ret:
                        strips = self._process_frame_to_strips(frame)
                        if strips:
                            self.cached_strips = strips
                            self.refresh()
                        last_displayed_frame = target_frame
                await asyncio.sleep(0.05)
                continue
                
            start_time = time.time()
            
            async with self.cap_lock:
                if self.needs_immediate_seek:
                    await asyncio.to_thread(self.cap.set, cv2.CAP_PROP_POS_FRAMES, target_frame)
                    self.needs_immediate_seek = False
                
                # Check video sync relative to continuous audio clock
                current_frame = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
                delta = target_frame - current_frame
                
                if delta > 15 or delta < -15:
                    # Significant desynchronization or seek: jump directly
                    await asyncio.to_thread(self.cap.set, cv2.CAP_PROP_POS_FRAMES, target_frame)
                elif delta > 2:
                    # Moderate lag: batch grab intermediate frames without decoding
                    def _skip_frames(cap, count):
                        for _ in range(count):
                            if not cap.grab():
                                break
                    await asyncio.to_thread(_skip_frames, self.cap, delta - 1)
                elif delta < -2:
                    # Video slightly ahead of audio clock: pause briefly to align
                    await asyncio.sleep(0.01)
                    continue
                
                ret, frame = await asyncio.to_thread(self.cap.read)
            
            if ret:
                strips = self._process_frame_to_strips(frame)
                if strips:
                    self.cached_strips = strips
                    self.refresh()
                last_displayed_frame = target_frame
                
            elapsed = time.time() - start_time
            sleep_time = max(0.001, frame_duration - elapsed)
            await asyncio.sleep(sleep_time)

    def _process_frame_to_strips(self, frame) -> list[Strip] | None:
        cols = self.content_size.width
        # Reserve bottom row for status bar
        rows = self.content_size.height - 1
        if cols <= 0 or rows <= 0:
            return None
            
        target_width = cols
        target_height = rows * 2
        
        h, w = frame.shape[:2]
        img_ratio = w / h
        win_ratio = target_width / target_height
        
        if img_ratio > win_ratio:
            rw = target_width
            rh = int(rw / img_ratio)
        else:
            rh = target_height
            rw = int(rh * img_ratio)
            
        rw = max(1, rw)
        rh = max(1, rh)
        
        resized = cv2.resize(frame, (rw, rh), interpolation=cv2.INTER_NEAREST)
        rgb_frame = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        rgb_bytes = rgb_frame.tobytes()
        
        engine = native.ImageEngine(rw, rh)
        ansi_frame = engine.render_frame(rgb_bytes)
        
        text = Text.from_ansi(ansi_frame)
        options = self.app.console.options.update(width=rw, no_wrap=True)
        rendered_lines = self.app.console.render_lines(text, options)
        
        offset_x = (cols - rw) // 2
        if offset_x > 0:
            padding_segment = Segment(" " * offset_x)
            return [Strip([padding_segment] + list(line)) for line in rendered_lines]
        return [Strip(line) for line in rendered_lines]

    def _render_status_bar(self, width: int) -> Strip:
        status_icon = "⏸" if self.is_paused else "▶"
        current_time = self.get_current_playback_time()
        time_str = format_time(current_time)
        duration_str = format_time(self.duration)
        time_info = f" {status_icon} {time_str} / {duration_str} "
        
        if self.is_muted:
            volume_info = " Vol: MUTE 🔇 "
        else:
            volume_info = f" Vol: {int(self.volume)}% 🔊 "
            
        # Calculate remaining width for progress bar
        reserved_width = len(time_info) + len(volume_info) + 2
        bar_width = width - reserved_width
        
        t = Text()
        t.append(f" {status_icon} ", style="bold yellow" if self.is_paused else "bold green")
        t.append(f"{time_str}", style="bold white")
        t.append(f" / {duration_str} ", style="cyan")
        
        if bar_width > 5:
            if self.duration > 0:
                progress = min(1.0, max(0.0, current_time / self.duration))
            else:
                progress = 0.0
            
            filled_width = int(progress * bar_width)
            empty_width = bar_width - filled_width
            
            t.append("[", style="bold white")
            t.append("━" * max(0, filled_width - 1), style="bold green")
            if filled_width > 0:
                t.append("●", style="bold yellow")
            t.append("─" * empty_width, style="white")
            t.append("]", style="bold white")
            
        if self.is_muted:
            t.append(volume_info, style="bold red")
        else:
            t.append(volume_info, style="bold magenta")
            
        # Pad line with spaces to fill full width
        t_len = len(t.plain)
        if t_len < width:
            t.append(" " * (width - t_len))
            
        t.stylize("on #121214")
        
        options = self.app.console.options.update(width=width, no_wrap=True)
        rendered_lines = self.app.console.render_lines(t, options)
        if rendered_lines:
            return Strip(rendered_lines[0])
        return Strip([])

    def render_line(self, y: int) -> Strip:
        H = self.content_size.height
        W = self.content_size.width
        if H <= 0 or W <= 0:
            return Strip([])
            
        # Error overlay rendering
        if self.error_message:
            lines = self.error_message.splitlines()
            offset_y = (H - len(lines)) // 2
            img_y = y - offset_y
            if 0 <= img_y < len(lines):
                line_text = lines[img_y]
                padding = max(0, (W - len(line_text)) // 2)
                t = Text(" " * padding + line_text + " " * (W - len(line_text) - padding), style="bold red on #121214")
                options = self.app.console.options.update(width=W, no_wrap=True)
                rendered = self.app.console.render_lines(t, options)
                if rendered:
                    return Strip(rendered[0])
            return Strip([])
            
        # Render status bar on bottom row
        if y == H - 1:
            return self._render_status_bar(W)
            
        # Render video frame
        if not self.cached_strips:
            return Strip([])
            
        # Centered frame rendering (height minus status bar)
        offset_y = (H - 1 - len(self.cached_strips)) // 2
        img_y = y - offset_y
        
        if 0 <= img_y < len(self.cached_strips):
            return self.cached_strips[img_y]
                
        return Strip([])

    async def on_key(self, event: events.Key) -> None:
        if self.error_message:
            return
            
        if event.key == "space":
            event.stop()
            await self._send_command(["cycle", "pause"])
        elif event.key == "left":
            event.stop()
            await self._send_command(["seek", -5, "relative"])
        elif event.key == "right":
            event.stop()
            await self._send_command(["seek", 5, "relative"])
        elif event.key in ("up", "plus"):
            event.stop()
            await self._send_command(["add", "volume", 5])
        elif event.key in ("down", "minus"):
            event.stop()
            await self._send_command(["add", "volume", -5])
        elif event.key == "m":
            event.stop()
            await self._send_command(["cycle", "mute"])

    async def on_unmount(self) -> None:
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass
        if self.mpv_process:
            try:
                self.mpv_process.terminate()
                await self.mpv_process.wait()
            except Exception:
                pass
        async with self.cap_lock:
            if self.cap:
                self.cap.release()
        if os.path.exists(self.ipc_path):
            try:
                os.remove(self.ipc_path)
            except Exception:
                pass
