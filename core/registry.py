from apps.terminal.terminal import PTYWidget
from apps.editor.editor import TextEditor
from apps.image_viewer.image_viewer import ImageViewer
from apps.music_player.music_player import MusicPlayer
from apps.video_player.video_player import VideoPlayer

APP_REGISTRY = [
    {
        "name": "Terminal",
        "icon": "$",
        "class": PTYWidget,
        "description": "Linux terminal emulator",
    },
    {
        "name": "Editor",
        "icon": "≡",
        "class": TextEditor,
        "description": "Powerful source code and text editor",
    },
    {
        "name": "Viewer",
        "icon": "#",
        "class": ImageViewer,
        "description": "High-performance image viewer",
    },
    {
        "name": "Player",
        "icon": ">",
        "class": MusicPlayer,
        "description": "Headless audio player via MPV",
    },
    {
        "name": "Watcher",
        "icon": "W",
        "class": VideoPlayer,
        "description": "High-performance ASCII video player",
    }
]