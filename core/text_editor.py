import os
from textual.widgets import TextArea, Input
from textual.screen import ModalScreen
from textual.containers import Vertical
from textual.app import ComposeResult
from textual.binding import Binding
from core.window import Window
from tree_sitter import Language



from textual.widgets import Label, Button
from textual.containers import Horizontal

class ConfirmCloseModal(ModalScreen):
    BINDINGS = [
        ("left", "focus_left", "Left"),
        ("right", "focus_right", "Right"),
        ("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    ConfirmCloseModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.5);
    }
    #confirm-box {
        width: 60;
        height: auto;
        background: $surface;
        border: solid $warning;
        padding: 1 2;
        layout: vertical;
        align: center middle;
    }
    #confirm-label {
        width: 100%;
        text-align: center;
        margin-bottom: 2;
        text-style: bold;
    }
    #confirm-buttons {
        width: auto;
        height: auto;
        align: center middle;
    }
    #confirm-buttons Button {
        margin: 0 1;
    }
    """
    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box"):
            yield Label("⚠️ Modifications non enregistrées. Voulez-vous sauvegarder ?", id="confirm-label")
            with Horizontal(id="confirm-buttons"):
                yield Button("Enregistrer", variant="success", id="btn-save")
                yield Button("Ne pas sauver", variant="error", id="btn-discard")
                yield Button("Annuler", variant="primary", id="btn-cancel")

    def on_mount(self) -> None:
        self.query_one("#btn-save").focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_focus_left(self) -> None:
        focused = self.screen.focused
        if focused and focused.id == "btn-cancel":
            self.query_one("#btn-discard").focus()
        elif focused and focused.id == "btn-discard":
            self.query_one("#btn-save").focus()
        else:
            self.query_one("#btn-cancel").focus()

    def action_focus_right(self) -> None:
        focused = self.screen.focused
        if focused and focused.id == "btn-save":
            self.query_one("#btn-discard").focus()
        elif focused and focused.id == "btn-discard":
            self.query_one("#btn-cancel").focus()
        else:
            self.query_one("#btn-save").focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-save":
            self.dismiss(True)
        elif event.button.id == "btn-discard":
            self.dismiss(False)
        else:
            self.dismiss(None)

class SaveAsModal(ModalScreen):
    DEFAULT_CSS = """
    SaveAsModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.5);
    }

    #save-box {
        width: 50;
        height: auto;
        background: $surface;
        border: solid $primary;
        padding: 1;
    }

    #save-input {
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="save-box"):
            yield Input(placeholder="Enter file path to save...", id="save-input")

    def on_mount(self) -> None:
        self.query_one("#save-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        path = event.value.strip()
        if path:
            self.dismiss(path)
        else:
            self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)


class TextEditor(Window):
    BINDINGS = [
        Binding("ctrl+s", "save_file", "Save"),
        Binding("shift+tab", "dedent", "Dedent", show=False),
    ]

    DEFAULT_CSS = """
    TextEditor TextArea, TextEditor TextArea:focus {
        border: none;
        height: 100%;
        width: 100%;
    }
    """

    def __init__(self, *args, **kwargs):
        super().__init__("Editor", "📝")
        self.file_path = args[0] if args else None
        self.text_area = TextArea(show_line_numbers=True)
        self.text_area.theme = "vscode_dark"
        self.text_area.tab_behavior = "indent"

        self._language_mapping = {
            ".py": "python", ".rs": "rust", ".json": "json",
            ".md": "markdown", ".toml": "toml", ".yaml": "yaml",
            ".sh": "bash", ".c": "c", ".h": "c", ".cpp": "cpp",
            ".hpp": "cpp", ".js": "javascript", ".ts": "javascript",
            ".html": "html", ".css": "css", ".xml": "xml",
            ".go": "go", ".java": "java", ".sql": "sql",
        }

        self._load_user_languages()

        try:
            import tree_sitter_c
            _root = os.path.dirname(os.path.abspath(__file__))
            with open(os.path.join(_root, "c_highlights.scm"), "r") as f:
                self.text_area.register_language("c", Language(tree_sitter_c.language()), f.read())
        except Exception:
            pass

        self._language_mapping = {
            ".py": "python", ".rs": "rust", ".json": "json",
            ".md": "markdown", ".toml": "toml", ".yaml": "yaml",
            ".sh": "bash", ".c": "c", ".h": "c", ".cpp": "cpp",
            ".hpp": "cpp", ".js": "javascript", ".ts": "javascript",
            ".html": "html", ".css": "css", ".xml": "xml",
            ".go": "go", ".java": "java", ".sql": "sql",
        }

        self._load_user_languages()

        try:
            import tree_sitter_cpp
            _root = os.path.dirname(os.path.abspath(__file__))
            with open(os.path.join(_root, "cpp_highlights.scm"), "r") as f:
                self.text_area.register_language("cpp", Language(tree_sitter_cpp.language()), f.read())
        except Exception:
            pass

        self._original_text = ""
        self._is_dirty = False
        self._update_title()

    def compose(self) -> ComposeResult:
        yield self.text_area

    def on_mount(self) -> None:
        if self.file_path and os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    self._original_text = content
                    self.text_area.load_text(content)
                self._detect_language()
            except Exception:
                pass
        self.text_area.focus()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        new_is_dirty = (self.text_area.text != self._original_text)
        if new_is_dirty != self._is_dirty:
            self._is_dirty = new_is_dirty
            self._update_title()

    def _update_title(self) -> None:
        base = os.path.basename(self.file_path) if self.file_path else "Untitled"
        indicator = " * " if self._is_dirty else ""
        self.border_title = f"📝 Editor - {base}{indicator}"


    def _load_user_languages(self) -> None:
        import json
        import importlib
        config_dir = os.path.expanduser("~/.config/rune/languages")
        if not os.path.exists(config_dir):
            try:
                os.makedirs(config_dir, exist_ok=True)
            except Exception:
                return

        for plugin_folder in os.listdir(config_dir):
            folder_path = os.path.join(config_dir, plugin_folder)
            if not os.path.isdir(folder_path):
                continue
            
            config_path = os.path.join(folder_path, "config.json")
            highlights_path = os.path.join(folder_path, "highlights.scm")
            
            if os.path.exists(config_path) and os.path.exists(highlights_path):
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                    
                    exts = config.get("extensions", [])
                    if "extension" in config and config["extension"] not in exts:
                        exts.append(config["extension"])
                    
                    module_name = config.get("module")
                    lang_name = config.get("name", plugin_folder)
                    
                    if not exts or not module_name:
                        continue
                        
                    lang_module = importlib.import_module(module_name)
                    
                    with open(highlights_path, "r", encoding="utf-8") as f:
                        query = f.read()
                    
                    language_obj = Language(lang_module.language())
                    self.text_area.register_language(language_obj.name, language_obj, query)
                    
                    # Register extensions
                    for ext in exts:
                        self._language_mapping[ext] = language_obj.name
                except Exception as e:
                    pass

    def _detect_language(self) -> None:
        if not self.file_path:
            return
        _, ext = os.path.splitext(self.file_path)
        lang = self._language_mapping.get(ext.lower())
        if lang:
            self.text_area.language = lang

    def action_save_file(self) -> None:
        if self.file_path:
            self._execute_save(self.file_path)
        else:
            def handle_path(path: str | None) -> None:
                if path:
                    self.file_path = path
                    self._detect_language()
                    self._execute_save(path)

            self.app.push_screen(SaveAsModal(), handle_path)

    def _execute_save(self, path: str) -> None:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.text_area.text)
            self._original_text = self.text_area.text
            self._is_dirty = False
            self._update_title()
        except OSError:
            pass
    async def confirm_close(self) -> bool:
        if not self._is_dirty:
            return True
        
        result = await self.app.push_screen_wait(ConfirmCloseModal())
        if result is True:  # Save
            if self.file_path:
                self._execute_save(self.file_path)
                return True
            else:
                path = await self.app.push_screen_wait(SaveAsModal())
                if path:
                    self.file_path = path
                    self._detect_language()
                    self._execute_save(path)
                    return True
                return False
        elif result is False:  # Discard
            return True
        return False  # Cancel

    def action_dedent(self) -> None:
        start, end = self.text_area.selection
        line_obj = self.text_area.get_line(start[0])
        line_str = getattr(line_obj, "plain", str(line_obj))
        if line_str.startswith("    "):
            self.text_area.replace("", (start[0], 0), (start[0], 4))
        elif line_str.startswith("\t"):
            self.text_area.replace("", (start[0], 0), (start[0], 1))
