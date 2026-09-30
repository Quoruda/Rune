import os
from PIL import Image, ImageSequence
from textual.strip import Strip
from rich.segment import Segment
from rich.text import Text
from textual.app import ComposeResult
from core.native import ImageEngine

from core.window import Window


class ImageViewer(Window):

    def __init__(self, *args, **kwargs):
        super().__init__("Image Viewer", "#")
        self.file_path = args[0] if args else None
        self.frames = []
        self.durations = []
        self.cached_renderables = []
        self.current_frame = 0
        self.is_animated = False
        self.timer = None
        self.last_width = 0
        self.last_height = 0

        if self.file_path:
            self.border_title = f"# Viewer - {os.path.basename(self.file_path)}"

    def compose(self) -> ComposeResult:
        return []

    def on_mount(self) -> None:
        if not self.file_path or not os.path.exists(self.file_path):
            return

        try:
            with Image.open(self.file_path) as img:
                self.is_animated = getattr(img, "is_animated", False)
                if self.is_animated:
                    self.frames = [f.copy() for f in ImageSequence.Iterator(img)]
                    self.durations = [f.info.get("duration", 100) / 1000.0 for f in self.frames]
                    self.render_next_frame()
                else:
                    self.frames = [img.copy()]
                    self.durations = [0.1]
                    self.update_render_cache()
        except Exception:
            pass

    def on_resize(self, event) -> None:
        self.update_render_cache()

    def update_render_cache(self) -> None:
        cols = self.content_size.width
        rows = self.content_size.height

        if cols <= 0 or rows <= 0:
            return

        if cols == self.last_width and rows == self.last_height:
            return

        self.last_width = cols
        self.last_height = rows
        self.cached_renderables = []

        target_width = cols
        target_height = rows * 2

        for img in self.frames:
            img_ratio = img.width / img.height
            win_ratio = target_width / target_height

            if img_ratio > win_ratio:
                w = target_width
                h = int(w / img_ratio)
            else:
                h = target_height
                w = int(h * img_ratio)

            w = max(1, w)
            h = max(1, h)

            resample_method = Image.Resampling.NEAREST if self.is_animated else Image.Resampling.BILINEAR
            resized_img = img.resize((w, h), resample_method)
            rgb_img = resized_img.convert("RGB")
            rgb_bytes = rgb_img.tobytes()

            engine = ImageEngine(w, h)
            ansi_str = engine.render_frame(rgb_bytes)

            text = Text.from_ansi(ansi_str)
            options = self.app.console.options.update(width=w, no_wrap=True)
            lines = self.app.console.render_lines(text, options)

            offset_x = (cols - w) // 2
            padding_segment = Segment(" " * offset_x) if offset_x > 0 else None

            frame_strips = []
            for line in lines:
                if padding_segment:
                    frame_strips.append(Strip([padding_segment] + list(line)))
                else:
                    frame_strips.append(Strip(line))

            self.cached_renderables.append(frame_strips)

        if self.current_frame >= len(self.cached_renderables):
            self.current_frame = 0

    def render_image(self) -> None:
        if not self.cached_renderables:
            self.update_render_cache()
        self.refresh()

    def render_next_frame(self) -> None:
        if not self.frames or not self.is_animated:
            return

        try:
            self.current_frame = (self.current_frame + 1) % len(self.frames)
            self.render_image()

            duration = self.durations[self.current_frame]
            if duration <= 0:
                duration = 0.1

            self.timer = self.set_timer(duration, self.render_next_frame)
        except Exception:
            pass

    def render_line(self, y: int) -> Strip:
        if not self.cached_renderables:
            self.update_render_cache()

        if not self.cached_renderables or self.current_frame >= len(self.cached_renderables):
            return Strip([])

        frame_strips = self.cached_renderables[self.current_frame]
        offset_y = (self.content_size.height - len(frame_strips)) // 2

        img_y = y - offset_y
        if 0 <= img_y < len(frame_strips):
            return frame_strips[img_y]

        return Strip([])

    def on_unmount(self) -> None:
        if self.timer:
            self.timer.stop()