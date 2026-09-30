import os
import sys
import shutil
import subprocess
import importlib


def ensure_native_compiled() -> None:
    try:
        import rune_native  # type: ignore
        return
    except ImportError:
        pass

    root_dir = os.path.dirname(os.path.abspath(__file__))
    crate_dir = os.path.join(root_dir, "crates", "native")
    if not os.path.exists(os.path.join(crate_dir, "Cargo.toml")):
        return

    # Check for maturin command or Python module
    maturin_bin = shutil.which("maturin")
    maturin_cmd = [maturin_bin] if maturin_bin else [sys.executable, "-m", "maturin"]

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(" [Rune] First launch: compiling native Rust acceleration engine...")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    env = os.environ.copy()
    env["PYO3_USE_ABI3_FORWARD_COMPATIBILITY"] = "1"

    try:
        cmd = maturin_cmd + ["develop", "--release"]
        res = subprocess.run(cmd, cwd=crate_dir, env=env)
        if res.returncode == 0:
            print(" [Rune] Native module compiled and installed successfully!\n")
            importlib.invalidate_caches()
        else:
            print(" [Rune] Warning: Compilation failed. Run 'cd crates/native && maturin develop --release' manually.\n")
    except Exception as e:
        print(f" [Rune] Could not trigger automatic compilation: {e}\n")


if __name__ == "__main__":
    ensure_native_compiled()
    from core.rune import Rune
    Rune().run()
