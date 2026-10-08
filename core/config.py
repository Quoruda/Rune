"""
Rune configuration loader.

Reads ~/.config/rune/config.toml (XDG-compliant) and builds:
  - APP_REGISTRY:    list[dict]  used by the launcher and app spawner
  - ASSOCIATIONS:    dict[str, str]  extension -> app name
  - GENERAL:         dict  general settings (workspace, autostart, …)

On first launch the bundled config.toml template is copied to the
user's config directory so they can customise it freely.
"""

import importlib
import os
import shutil
import sys
import tomllib
from pathlib import Path
from functools import lru_cache


# ── Paths ────────────────────────────────────────────────────────

def _xdg_config_home() -> Path:
    """Return $XDG_CONFIG_HOME or default ~/.config."""
    raw = os.environ.get("XDG_CONFIG_HOME")
    return Path(raw) if raw else Path.home() / ".config"


def _user_config_path() -> Path:
    return _xdg_config_home() / "rune" / "config.toml"


def _bundled_config_path() -> Path:
    """config.toml shipped alongside the source tree (project root)."""
    return Path(__file__).resolve().parent.parent / "config.toml"


# ── Bootstrap ────────────────────────────────────────────────────

def _ensure_user_config() -> Path:
    """
    If the user config does not exist yet, copy the bundled template.
    Returns the path to the user config file.
    """
    user_cfg = _user_config_path()
    if not user_cfg.exists():
        bundled = _bundled_config_path()
        if not bundled.exists():
            print(
                f" [Rune] Warning: no bundled config.toml found at {bundled}",
                file=sys.stderr,
            )
            return user_cfg  # will fail gracefully later
        user_cfg.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bundled, user_cfg)
        print(f" [Rune] Created default configuration at {user_cfg}")
    return user_cfg


# ── Loader ───────────────────────────────────────────────────────

def _load_toml(path: Path) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def _resolve_app_class(app_entry: dict):
    """
    Return a callable that creates a Window for *app_entry*.

    • Native apps  → import module.class
    • CLI commands  → lambda wrapping PTYWidget
    """
    if "command" in app_entry:
        # Lazy import to avoid circular deps at module level
        from apps.terminal.terminal import PTYWidget

        command = app_entry["command"]

        def _make_cli_app(*args):
            return PTYWidget(command, *args)

        return _make_cli_app

    module_path = app_entry.get("module")
    class_name = app_entry.get("class")
    if not module_path or not class_name:
        return None

    try:
        mod = importlib.import_module(module_path)
        return getattr(mod, class_name)
    except Exception as exc:
        print(
            f" [Rune] Warning: could not load {module_path}.{class_name}: {exc}",
            file=sys.stderr,
        )
        return None


def _build_registry(raw_apps: list[dict]) -> list[dict]:
    """
    Transform raw [[apps]] entries into the runtime registry format
    expected by ApplicationLauncher / Rune._open_app_by_name.
    """
    registry: list[dict] = []
    for entry in raw_apps:
        if not entry.get("enabled", True):
            continue

        cls = _resolve_app_class(entry)
        if cls is None:
            continue

        registry.append({
            "name": entry["name"],
            "icon": entry.get("icon", "📦"),
            "class": cls,
            "description": entry.get("description", ""),
        })
    return registry


# ── Public API ───────────────────────────────────────────────────

class RuneConfig:
    """Singleton-like holder for the loaded configuration."""

    def __init__(self):
        self.general: dict = {}
        self.associations: dict[str, str] = {}
        self.app_registry: list[dict] = []
        self._loaded = False

    def load(self) -> None:
        """Load config from disk (only once at startup)."""
        if self._loaded:
            return
        self._do_load()
        self._loaded = True

    def reload(self) -> None:
        """Force re-read of config.toml (e.g. when opening the launcher)."""
        self._do_load()

    def _do_load(self) -> None:
        cfg_path = _ensure_user_config()

        if cfg_path.exists():
            data = _load_toml(cfg_path)
        else:
            # Fallback: try the bundled config directly
            bundled = _bundled_config_path()
            if bundled.exists():
                data = _load_toml(bundled)
            else:
                data = {}

        self.general = data.get("general", {})
        self.associations = data.get("associations", {})
        self.app_registry = _build_registry(data.get("apps", []))

    def resolve_file_app(self, file_path: str | Path) -> str | None:
        """
        Given a file path, return the application name to open it with,
        using the [associations] table.  Falls back to mimetype guessing
        if no explicit mapping is found.
        """
        import mimetypes

        ext = os.path.splitext(str(file_path))[1].lower()

        # 1. Explicit association
        app_name = self.associations.get(ext)
        if app_name:
            return app_name

        # 2. Mimetype fallback — map to well-known categories
        mimetypes.init()
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if mime_type:
            if mime_type.startswith("image/"):
                return self._first_app_for_category("image")
            elif mime_type.startswith("audio/"):
                return self._first_app_for_category("audio")
            elif mime_type.startswith("video/"):
                return self._first_app_for_category("video")

        # 3. Default to editor
        return self._first_app_for_category("text")

    def _first_app_for_category(self, category: str) -> str | None:
        """
        Find the first app name in associations whose extensions belong
        to *category*, or return a sensible default.
        """
        # Map common extensions to categories for reverse lookup
        category_exts = {
            "image": {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"},
            "audio": {".mp3", ".wav", ".ogg", ".flac", ".m4a"},
            "video": {".mp4", ".mkv", ".avi", ".mov", ".webm"},
            "text":  {".txt", ".py", ".rs", ".md", ".json", ".toml"},
        }

        target_exts = category_exts.get(category, set())
        for ext, app_name in self.associations.items():
            if ext in target_exts:
                return app_name

        # Absolute fallback: first registered app name, or "Editor"
        if self.app_registry:
            return self.app_registry[0]["name"]
        return "Editor"


# Module-level singleton
config = RuneConfig()
