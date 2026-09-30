"""
Native Rust acceleration bindings for Rune.
Provides TerminalEngine and ImageEngine backed by rune_native.
"""

def _load_native():
    try:
        import rune_native
        return rune_native.TerminalEngine, rune_native.ImageEngine
    except ImportError:
        class _MissingTerminalEngine:
            def __init__(self, *args, **kwargs):
                raise RuntimeError(
                    "The native Rust module 'rune_native' is not compiled or installed.\n"
                    "To compile it, install Rust (e.g. `sudo dnf install cargo rust`) and run:\n"
                    "  cd crates/native && maturin develop --release"
                )

        class _MissingImageEngine:
            def __init__(self, *args, **kwargs):
                raise RuntimeError(
                    "The native Rust module 'rune_native' is not compiled or installed.\n"
                    "To compile it, install Rust (e.g. `sudo dnf install cargo rust`) and run:\n"
                    "  cd crates/native && maturin develop --release"
                )

        return _MissingTerminalEngine, _MissingImageEngine


TerminalEngine, ImageEngine = _load_native()

__all__ = ["TerminalEngine", "ImageEngine"]
