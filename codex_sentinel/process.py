"""
Cross-platform process supervisor and Desktop client management.
Ensures session locks are cleanly released without triggering Electron auto-respawn loops.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from typing import List


def kill_codex_desktop_tree() -> None:
    """
    Terminate Codex Desktop App and its child worker backend.
    
    Why:
    Electron-based desktop clients (e.g. ChatGPT.exe) supervise child worker processes
    (codex.exe app-server). If only the child worker is terminated, the Electron parent
    immediately respawns a new worker within milliseconds, re-locking the session and causing
    'thread already has an active writer' errors.
    
    To ensure clean handover, the entire process hierarchy must be terminated.
    """
    if sys.platform == "win32":
        _kill_windows_desktop_tree()
    else:
        _kill_posix_desktop_tree()


def _kill_windows_desktop_tree() -> None:
    """Windows-specific process tree termination."""
    target_names = {
        "chatgpt.exe",
        "codex.exe",
        "codex-code-mode-host.exe",
        "codex-windows-sandbox-service.exe",
    }

    # 1. Best-effort graceful/force kill via psutil
    try:
        import psutil

        for proc in psutil.process_iter(["pid", "name"]):
            try:
                name = (proc.info["name"] or "").lower()
                if name in target_names:
                    proc.kill()
            except Exception:
                pass
    except Exception:
        pass

    # 2. taskkill with /T (terminate process tree) and /F (force)
    for img in ["ChatGPT.exe", "codex.exe"]:
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/IM", img],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except Exception:
            pass


def _kill_posix_desktop_tree() -> None:
    """Linux/macOS process tree termination."""
    target_keywords = ["chatgpt", "codex-app-server", "codex"]

    try:
        import psutil

        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                name = (proc.info["name"] or "").lower()
                cmdline = " ".join(proc.info["cmdline"] or []).lower()
                if any(kw in name or kw in cmdline for kw in target_keywords):
                    os.kill(proc.info["pid"], signal.SIGTERM)
            except Exception:
                pass
    except Exception:
        # Fallback to pkill if psutil is unavailable or fails
        for kw in ["ChatGPT", "codex"]:
            try:
                subprocess.run(
                    ["pkill", "-f", kw],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            except Exception:
                pass


def relaunch_desktop_app() -> bool:
    """
    Attempt to restart the official Codex / ChatGPT Desktop application.
    Returns True if launch command succeeded, False otherwise.
    """
    if sys.platform == "win32":
        try:
            # UWP / MSIX package ID for OpenAI Codex Desktop App
            app_id = "OpenAI.Codex_2p2nqsd0c76g0!App"
            subprocess.Popen(
                f"explorer.exe shell:AppsFolder\\{app_id}",
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            return False

    elif sys.platform == "darwin":
        # macOS
        for app_name in ["ChatGPT", "Codex"]:
            try:
                res = subprocess.run(
                    ["open", "-a", app_name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                if res.returncode == 0:
                    return True
            except Exception:
                pass
        return False

    else:
        # Linux
        for cmd in ["chatgpt", "codex-desktop"]:
            try:
                res = subprocess.run(
                    ["which", cmd],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                if res.returncode == 0:
                    subprocess.Popen([cmd])
                    return True
            except Exception:
                pass
        return False
