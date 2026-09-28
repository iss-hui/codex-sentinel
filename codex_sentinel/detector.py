"""
Session scanner and rate-limit detector for OpenAI Codex session rollout logs.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def get_sessions_dir() -> Path:
    """Return the platform-agnostic sessions directory: ~/.codex/sessions"""
    return Path.home() / ".codex" / "sessions"


def get_recent_session_files(limit: int = 15) -> List[Path]:
    """
    Search and return recent session jsonl files, sorted by modification time (newest first).
    """
    sessions_dir = get_sessions_dir()
    if not sessions_dir.exists():
        return []

    files = list(sessions_dir.glob("**/*.jsonl"))
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:limit]


def parse_session_file(filepath: Path) -> Optional[Dict[str, Any]]:
    """
    Parse a single session rollout file to check if it was interrupted by rate limits.
    Scans turns in reverse chronological order to capture the most recent state.
    """
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except Exception:
        return None

    if not lines:
        return None

    session_id: Optional[str] = None
    cwd: Optional[str] = None

    # Parse session_meta from first line
    try:
        first = json.loads(lines[0])
        if first.get("type") == "session_meta":
            payload = first.get("payload", {})
            session_id = payload.get("id")
            cwd = payload.get("cwd")
    except Exception:
        pass

    latest_task_complete: Optional[Dict[str, Any]] = None
    latest_rate_limit: Optional[Dict[str, Any]] = None
    latest_model: Optional[str] = None

    # Scan events bottom-up (newest events first)
    for line in reversed(lines):
        try:
            data = json.loads(line)
        except Exception:
            continue

        msg_type = data.get("type")
        payload = data.get("payload", {})

        if msg_type == "turn_context" and not latest_model:
            model = payload.get("model")
            if model:
                latest_model = model

        if msg_type == "event_msg":
            p_type = payload.get("type")
            if p_type == "task_complete" and latest_task_complete is None:
                latest_task_complete = payload

            if p_type == "token_count" and latest_rate_limit is None:
                rate_limits = payload.get("rate_limits", {})
                primary = rate_limits.get("primary")
                if primary and primary.get("resets_at"):
                    latest_rate_limit = primary

        # Short-circuit once all latest status entries are discovered
        if latest_task_complete is not None and latest_rate_limit is not None and latest_model is not None:
            break

    # Verify if the latest task turn was actually stopped due to quota limits
    if latest_task_complete and latest_task_complete.get("error") and latest_rate_limit:
        err = latest_task_complete["error"]
        err_str = str(err).lower()
        if err.get("codex_error_info") == "usage_limit_exceeded" or "usage limit" in err_str:
            resets_at = latest_rate_limit["resets_at"]
            now = time.time()
            if resets_at > now:
                return {
                    "session_id": session_id,
                    "file": str(filepath),
                    "cwd": cwd or str(Path.cwd()),
                    "resets_at": resets_at,
                    "error_msg": err.get("message", "Usage limit reached"),
                    "model": latest_model or "Desktop App Default",
                    "used_percent": latest_rate_limit.get("used_percent", 100),
                    "remaining_seconds": resets_at - now,
                }

    return None


def find_active_rate_limit(max_files: int = 15) -> Optional[Dict[str, Any]]:
    """
    Search recent session files and return rate limit status for the latest active session.
    """
    session_files = get_recent_session_files(limit=max_files)
    for filepath in session_files:
        limit_info = parse_session_file(filepath)
        if limit_info:
            return limit_info
    return None
