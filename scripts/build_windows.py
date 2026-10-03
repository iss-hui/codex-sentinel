"""Build the Windows desktop folder and ZIP with the current Python environment."""
import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    if os.name != "nt":
        raise SystemExit("Build the Windows package on Windows.")
    parser = argparse.ArgumentParser()
    parser.add_argument("--suffix", default="", help="Separate output for updating a running app")
    args = parser.parse_args()
    if args.suffix and not re.fullmatch(r"[a-z0-9-]+", args.suffix):
        parser.error("suffix must contain lowercase letters, digits or hyphens")
    suffix = f"-{args.suffix}" if args.suffix else ""
    root = Path(__file__).resolve().parents[1]
    destination = f"dist/desktop{suffix}"
    work = f"build/desktop{suffix}-isolated"
    archive_name = f"dist/CodexSentinel-windows-x64{suffix}"
    # PyInstaller may replace its existing generated output with --noconfirm.
    for relative in (f"{destination}/CodexSentinel", work, f"{archive_name}.zip"):
        (root / relative).resolve().relative_to(root)
    # Resolve native dependencies from this Python installation, not unrelated
    # tools on PATH (for example Poppler bundles incompatible Windows DLLs).
    python_root = Path(sys.base_prefix)
    windows = Path(os.environ.get("SystemRoot", "C:/Windows"))
    environment = os.environ.copy()
    environment["PATH"] = os.pathsep.join(str(p) for p in (
        Path(sys.executable).parent, python_root, python_root / "DLLs",
        python_root / "Library/bin", windows / "System32", windows,
    ) if p.is_dir())
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--onedir", "--windowed",
         "--name", "CodexSentinel", "--distpath", destination, "--workpath", work,
         "--specpath", "build", "run_desktop.py"], cwd=root, check=True, env=environment,
    )
    archive = shutil.make_archive(str(root / archive_name), "zip",
                                  root_dir=root / destination, base_dir="CodexSentinel")
    print(archive)


if __name__ == "__main__":
    main()
