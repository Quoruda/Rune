from textual.widget import Widget
from textual import events

class Window(Widget):
    can_focus = True
    DEFAULT_CSS = """
    Window {
        border: solid $accent;
        height: 1fr;
        width: 1fr;
    }
    Window:focus-within {
        border: solid $primary;
    }
    """

    def __init__(self, name: str, icon: str):
        super().__init__(name=name)
        icon = icon.replace("\ufe0f", "")
        assert len(icon) == 1, "Icon must be a single character"
        self.icon: str = icon
        self.border_title: str = f"{icon} {name}"

    def focus(self, scroll_visible: bool = True) -> "Window":
        for child in self.query("*"):
            if child.can_focus and child is not self:
                child.focus(scroll_visible)
                return self
        super().focus(scroll_visible)
        return self

    def on_focus(self, event: events.Focus) -> None:
        if event.control is self:
            for child in self.query("*"):
                if child.can_focus and child is not self:
                    child.focus()
                    break

    async def on_unmount(self) -> None:
        if self.has_class("zoomed"):
            self.app.remove_class("zoom-active")
    async def confirm_close(self) -> bool:
        return True
