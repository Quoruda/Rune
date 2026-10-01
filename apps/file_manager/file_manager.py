from textual.widgets import DirectoryTree
from textual.app import ComposeResult
from core.window import Window
from pathlib import Path
from textual.widgets import Input
from textual.binding import Binding
from textual.widgets import Label
import time


class FileManager(Window):

    BINDINGS = [
        Binding("backspace", "parent_directory", "parent directory"),        
    ]

    def on_mount(self) -> None:
        self.set_interval(1, self.refresh_tree)

    def __init__(self, start_path: str | Path = "."):
        super().__init__("Files", "F")
        self.path = Path(start_path).resolve()
        self.path_label = Label(str(self.path), id="path-header")        
        self.directory_tree = DirectoryTree(self.path, id="file-tree")
        self.last_action_time = time.time()
        self.minimum_refresh_interval = 0.5

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        self.app.open_file(str(event.path.resolve()))


    def compose(self) -> ComposeResult:
        yield self.path_label
        yield self.directory_tree
    
    def action_parent_directory(self) -> None:
        self.directory_tree.path = self.directory_tree.path.parent
        self.path_label.update(str(self.directory_tree.path.resolve()))
        

    def on_directory_tree_directory_selected(self, event: DirectoryTree.DirectorySelected) -> None:
        self.directory_tree.path = event.path
        self.path_label.update(str(self.directory_tree.path.resolve()))
    
    def refresh_tree(self) -> None:
        now = time.time()
        if now - self.last_action_time > self.minimum_refresh_interval:
            self.directory_tree.reload()
            self.last_action_time = now


