"""
Application registry — now driven by config.toml.

This module exposes APP_REGISTRY for backward-compatibility with
existing imports (ApplicationLauncher, Rune, etc.).  The actual data
is loaded lazily from core.config on first access.
"""

from core.config import config


def get_registry() -> list[dict]:
    """Return the application registry, loading config if needed."""
    config.load()
    return config.app_registry


def get_associations() -> dict[str, str]:
    """Return the file-extension associations."""
    config.load()
    return config.associations


# Eager load so that `from core.registry import APP_REGISTRY` keeps working.
config.load()
APP_REGISTRY = config.app_registry
