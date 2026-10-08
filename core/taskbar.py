from datetime import datetime
from textual.widget import Widget
from textual.widgets import Static
from textual.app import ComposeResult

class Taskbar(Widget):
    DEFAULT_CSS = """
    Taskbar {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $text;
        layout: horizontal;
    }
    #shortcuts {
        width: 1fr;
        padding-left: 1;
    }
    #clock {
        width: auto;
        padding-right: 1;
        color: $accent;
        text-style: bold;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(
            "ctrl+p Launcher │ ctrl+z Zoom │ ctrl+w Close │ ctrl+arrows Navigate │ ctrl+q Quit",
            id="shortcuts"
        )
        yield Static("", id="clock")

    def on_mount(self) -> None:
        self._update_clock()
        self.set_interval(1.0, self._update_clock)

    def _update_clock(self) -> None:
        self.query_one("#clock", Static).update(datetime.now().strftime("%H:%M:%S"))