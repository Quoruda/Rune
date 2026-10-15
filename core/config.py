"""
Rune configuration loader.

Reads bundled config.toml (defaults) and ~/.config/rune/config.toml (user overrides):
  - Bundled config defines default apps, associations, and general settings.
  - User config (~/.config/rune/config.toml) overrides or extends these defaults.
    For instance, an app can be disabled with:
      [[apps]]
      name = "PdfViewer"
      enabled = false  (or enable = false)

On first launch a minimal user config template is created at ~/.config/rune/config.toml.
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

USER_CONFIG_TEMPLATE = """# ==============================================================
#  Rune Desktop Environment — User Configuration
#  Stored at: ~/.config/rune/config.toml
#
#  This file overrides and extends Rune's bundled configuration.
#  You only need to define what you want to customize or add.
# ==============================================================

[general]
# Override general settings:
# workspace = "~"
# autostart = ["Terminal"]

[associations]
# Override or add custom file associations:
# ".pdf" = "PdfViewer"

# ==============================================================
#  Application Overrides & Custom Applications
# ==============================================================
#
# Example: Disable a built-in application
# [[apps]]
# name    = "PdfViewer"
# enabled = false
#
# Example: Add a custom CLI command
# [[apps]]
# name    = "Neovim"
# icon    = "📝"
# command = "nvim"
"""


def _ensure_user_config() -> Path:
    """
    If the user config does not exist yet, create a starter template.
    Returns the path to the user config file.
    """
    user_cfg = _user_config_path()
    if not user_cfg.exists():
        user_cfg.parent.mkdir(parents=True, exist_ok=True)
        try:
            user_cfg.write_text(USER_CONFIG_TEMPLATE, encoding="utf-8")
            print(f" [Rune] Created default configuration at {user_cfg}")
        except Exception as exc:
            print(f" [Rune] Warning: could not write user config to {user_cfg}: {exc}", file=sys.stderr)
    return user_cfg


# ── Loader & Merger ───────────────────────────────────────────────

def _load_toml(path: Path) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def _merge_configs(bundled: dict, user: dict) -> dict:
    """
    Merge bundled (default) and user configuration dictionaries.

    - general: user values override bundled values.
    - associations: user mappings override/augment bundled mappings.
    - apps: bundled apps provide default attributes. User entries with matching
      'name' override attributes (e.g. enabled = false / enable = false).
      New user apps are appended.
    """
    general = dict(bundled.get("general", {}))
    general.update(user.get("general", {}))

    associations = dict(bundled.get("associations", {}))
    for k, v in user.get("associations", {}).items():
        if v:
            associations[k] = v
        elif k in associations:
            del associations[k]

    merged_apps: list[dict] = []
    bundled_apps = [dict(a) for a in bundled.get("apps", [])]
    user_apps = [dict(a) for a in user.get("apps", [])]

    # Pre-process bundled apps and register their order
    for entry in bundled_apps:
        if "enable" in entry:
            entry["enabled"] = entry.pop("enable")
        merged_apps.append(entry)

    name_to_index = {entry["name"]: idx for idx, entry in enumerate(merged_apps) if "name" in entry}

    for u_entry in user_apps:
        u_dict = dict(u_entry)
        if "enable" in u_dict:
            u_dict["enabled"] = u_dict.pop("enable")

        name = u_dict.get("name")
        if name and name in name_to_index:
            # Override existing bundled app attributes
            idx = name_to_index[name]
            merged_apps[idx].update(u_dict)
        else:
            # Brand new custom application
            if name:
                name_to_index[name] = len(merged_apps)
            merged_apps.append(u_dict)

    return {
        "general": general,
        "associations": associations,
        "apps": merged_apps,
    }


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
        is_enabled = entry.get("enabled", entry.get("enable", True))
        if not is_enabled:
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
        bundled_path = _bundled_config_path()
        bundled_data = _load_toml(bundled_path) if bundled_path.exists() else {}

        user_path = _ensure_user_config()
        user_data = _load_toml(user_path) if user_path.exists() else {}

        merged = _merge_configs(bundled_data, user_data)

        self.general = merged.get("general", {})
        self.associations = merged.get("associations", {})
        self.app_registry = _build_registry(merged.get("apps", []))

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
