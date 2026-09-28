"""
Cross-platform file locking manager for OpenAI Codex thread writer locks.
Supports Windows (msvcrt) and POSIX/Linux/macOS (fcntl).
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Optional


def get_locks_dir() -> Path:
    """Return the platform-agnostic lock directory: ~/.codex/thread-writer-locks"""
    return Path.home() / ".codex" / "thread-writer-locks"


def get_lock_file(session_id: str) -> Path:
    """Return the path to the session lock file."""
    return get_locks_dir() / f"{session_id}.lock"


def is_lock_free(lock_path: Path | str) -> bool:
    """
    Check if the specified lock file is free (not exclusively held by another process).
    Returns True if free or does not exist, False if locked.
    """
    path = Path(lock_path)
    if not path.exists():
        return True

    try:
        with open(path, "r+", encoding="utf-8", errors="ignore") as f:
            if sys.platform == "win32":
                import msvcrt
                try:
                    # Non-blocking lock test on Windows
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                    return True
                except OSError:
                    return False
            else:
                import fcntl
                try:
                    # Non-blocking lock test on Unix/Linux/macOS
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                    return True
                except (BlockingIOError, OSError):
                    return False
    except OSError:
        # File is locked at the OS level (e.g., Windows sharing violation)
        return False
    except Exception:
        return False


def is_thread_locked(session_id: str) -> bool:
    """Check whether a given session thread has an active writer lock."""
    if not session_id:
        return False
    return not is_lock_free(get_lock_file(session_id))


def wait_for_lock_release(session_id: str, timeout: float = 10.0, poll_interval: float = 0.5) -> bool:
    """
    Poll until the thread lock is verified to be completely released.
    Returns True if lock was released within timeout, False otherwise.
    """
    if not session_id:
        return True

    lock_file = get_lock_file(session_id)
    start_time = time.time()

    while time.time() - start_time < timeout:
        if is_lock_free(lock_file):
            return True
        time.sleep(poll_interval)

    return False
