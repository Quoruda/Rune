"""
Power Menu – modal shown on Ctrl+Q.

Provides:
  • Quit Rune (with confirm_close on every open window)
  • Reboot the machine  (systemctl reboot)
  • Shutdown the machine (systemctl poweroff)
  • Cancel / Escape

A 2-second cooldown prevents accidental activation: action buttons
are disabled and display a countdown, while Cancel / Escape remain
active immediately.
"""

from textual.screen import ModalScreen
from textual.binding import Binding
from textual.containers import Vertical, Horizontal
from textual.widgets import Label, Button
from textual.app import ComposeResult
from textual.timer import Timer


COOLDOWN_SECONDS = 2


class PowerMenuModal(ModalScreen[str | None]):
    """Session power-menu with a safety cooldown."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False, priority=True),
        Binding("ctrl+q", "cancel", "Cancel", show=False, priority=True),
        Binding("right", "app.focus_next", "Next", show=False),
        Binding("down", "app.focus_next", "Next", show=False),
        Binding("left", "app.focus_previous", "Previous", show=False),
        Binding("up", "app.focus_previous", "Previous", show=False),
    ]

    DEFAULT_CSS = """
    PowerMenuModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.65);
    }

    #power-box {
        width: 58;
        height: auto;
        background: $surface;
        border: solid $warning;
        padding: 1 2;
        layout: vertical;
        align: center middle;
    }

    #power-title {
        width: 100%;
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    #power-status {
        width: 100%;
        text-align: center;
        margin-bottom: 1;
        color: $text-muted;
    }

    #power-cooldown {
        width: 100%;
        text-align: center;
        margin-bottom: 1;
        color: $warning;
    }

    #power-actions {
        width: auto;
        height: auto;
        align: center middle;
        margin-bottom: 1;
    }

    #power-actions Button {
        margin: 0 1;
    }

    #power-cancel-row {
        width: auto;
        height: auto;
        align: center middle;
    }
    """

    def __init__(self, app_count: int) -> None:
        super().__init__()
        self.app_count = app_count
        self._remaining = COOLDOWN_SECONDS
        self._cooldown_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="power-box"):
            yield Label("⏻  Power Menu", id="power-title")
            status = (
                f"{self.app_count} running application(s)"
                if self.app_count > 0
                else "No running applications"
            )
            yield Label(status, id="power-status")
            yield Label(
                f"Actions available in {self._remaining}s…",
                id="power-cooldown",
            )
            with Horizontal(id="power-actions"):
                yield Button(
                    "🚪 Quit",
                    variant="error",
                    id="btn-quit",
                    disabled=True,
                )
                yield Button(
                    "🔄 Reboot",
                    variant="warning",
                    id="btn-reboot",
                    disabled=True,
                )
                yield Button(
                    "⏻ Shutdown",
                    variant="warning",
                    id="btn-shutdown",
                    disabled=True,
                )
            with Horizontal(id="power-cancel-row"):
                yield Button(
                    "Cancel",
                    variant="primary",
                    id="btn-power-cancel",
                )

    def on_mount(self) -> None:
        # Focus on Cancel by default (always available and safe)
        self.query_one("#btn-power-cancel").focus()
        # Start the cooldown countdown
        self._cooldown_timer = self.set_interval(1, self._tick_cooldown)

    def on_unmount(self) -> None:
        if self._cooldown_timer is not None:
            self._cooldown_timer.stop()
            self._cooldown_timer = None

    def _tick_cooldown(self) -> None:
        if not self.is_mounted:
            return
        self._remaining -= 1
        try:
            cooldown_label = self.query_one("#power-cooldown", Label)
        except Exception:
            return

        if self._remaining > 0:
            cooldown_label.update(
                f"Actions available in {self._remaining}s…"
            )
        else:
            cooldown_label.update("")
            try:
                self.query_one("#btn-quit", Button).disabled = False
                self.query_one("#btn-reboot", Button).disabled = False
                self.query_one("#btn-shutdown", Button).disabled = False
            except Exception:
                pass
            if self._cooldown_timer is not None:
                self._cooldown_timer.stop()
                self._cooldown_timer = None

    # ── Button handlers ──────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-power-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-quit":
            self.dismiss("quit")
        elif event.button.id == "btn-reboot":
            self.dismiss("reboot")
        elif event.button.id == "btn-shutdown":
            self.dismiss("shutdown")

    def action_cancel(self) -> None:
        self.dismiss(None)
