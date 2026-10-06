"""Incremental read-only access to Codex rollouts, SQLite and model cache.
No account API calls are made here. Missing data stays unknown.
"""

from __future__ import annotations

import copy
import json
import os
import time
from datetime import datetime
from pathlib import Path

from codex_sentinel.session_catalog import normalized_path, read_session_catalog


def get_codex_dir() -> Path:
    return Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))


def timestamp(value, fallback=0.0):
    try:
        if isinstance(value, (float, int)):
            return float(value)
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError, AttributeError):
        return fallback


def is_usage_error(error) -> bool:
    text = str(error).lower()
    return "usage_limit_exceeded" in text or "usage limit" in text


def blocking_reset(limits: dict, now: float) -> float:
    """Wait for all exhausted windows, including a longer weekly limit."""
    return max(
        (
            float(w.get("resets_at") or 0)
            for w in (limits.get("primary"), limits.get("secondary"))
            if isinstance(w, dict)
            and (w.get("used_percent") or 0) >= 100
            and (w.get("resets_at") or 0) > now
        ),
        default=0.0,
    )


class SessionScanner:
    def __init__(self, sessions_dir: Path | None = None, codex_dir: Path | None = None):
        self.codex_dir = codex_dir or get_codex_dir()
        self.sessions_dir = sessions_dir or self.codex_dir / "sessions"
        self._cache = {}

    def _read(self, path: Path) -> dict:
        stat = path.stat()
        cached = self._cache.get(path)
        if cached and cached[0] == (stat.st_size, stat.st_mtime_ns):
            return copy.deepcopy(cached[2])
        if cached and stat.st_size > cached[0][0]:
            offset, session = cached[1], copy.deepcopy(cached[2])
        else:
            offset = 0
            session = {
                "session_id": "",
                "cwd": "",
                "model": "",
                "title": "",
                "started_at": stat.st_mtime,
                "total_turns": 0,
                "had_rate_limit": False,
                "task_status": "unknown",
                "error_msg": "",
                "limits": {},
                "limits_at": 0.0,
                "limited_at": 0.0,
                "status_at": 0.0,
                "tokens_used": None,
                "file_path": str(path),
            }
        with path.open("rb") as stream:
            stream.seek(offset)
            while True:
                start = stream.tell()
                line = stream.readline()
                if not line:
                    break
                if not line.endswith(b"\n"):
                    stream.seek(start)
                    break
                try:
                    data = json.loads(line)
                    if isinstance(data, dict):
                        self._event(session, data, stat.st_mtime)
                except (ValueError, TypeError, AttributeError):
                    continue
            offset = stream.tell()
        session["updated_at"] = stat.st_mtime
        self._cache[path] = ((stat.st_size, stat.st_mtime_ns), offset, session)
        return copy.deepcopy(session)

    @staticmethod
    def _event(s, data, fallback):
        payload = data.get("payload") or {}
        if not isinstance(payload, dict):
            return
        kind = data.get("type")
        at = timestamp(data.get("timestamp"), fallback)
        if kind == "session_meta":
            s.update(
                session_id=payload.get("id") or "",
                cwd=payload.get("cwd") or "",
                started_at=timestamp(payload.get("timestamp"), at),
                source=payload.get("source"),
                thread_source=payload.get("thread_source"),
            )
        elif kind == "turn_context":
            s["total_turns"] += 1
            s["model"] = payload.get("model") or s["model"]
        elif kind == "event_msg":
            event = payload.get("type")
            if event == "token_count":
                limits = payload.get("rate_limits")
                if isinstance(limits, dict) and (
                    limits.get("primary") or limits.get("secondary")
                ):
                    s["limits"] = limits
                    s["limits_at"] = at
                info = payload.get("info") or {}
                usage = info.get("total_token_usage") or {}
                if usage.get("total_tokens") is not None:
                    s["tokens_used"] = usage["total_tokens"]
            elif event in ("task_started", "user_message"):
                s.update(task_status="running", error_msg="", status_at=at)
            elif event in ("task_complete", "task_failed", "error", "turn_aborted"):
                if event == "task_complete" and not payload.get("error") and s["task_status"] == "rate_limited":
                    # Some CLI versions emit completion after the quota error.
                    # Keep the interruption until a new turn actually begins.
                    return
                s["status_at"] = at
                error = payload.get("error")
                if event == "error":
                    error = payload
                if is_usage_error(error):
                    s.update(
                        task_status="rate_limited", had_rate_limit=True, limited_at=at
                    )
                elif event == "turn_aborted":
                    s["task_status"] = "interrupted"
                else:
                    s["task_status"] = "error" if error else "completed"
                s["error_msg"] = (
                    error.get("message", str(error))
                    if isinstance(error, dict)
                    else str(error or "")
                )

    def scan(self, limit=100, watch_session_id="") -> dict:
        warnings = []
        paths = []
        if not self.sessions_dir.exists():
            warnings.append(f"Sessions directory unavailable: {self.sessions_dir}")
        else:
            for path in self.sessions_dir.rglob("*.jsonl"):
                try:
                    paths.append((path.stat().st_mtime, path))
                except OSError:
                    continue
        paths.sort(key=lambda pair: pair[0], reverse=True)
        catalog = read_session_catalog(self.codex_dir, [], warnings)
        visible = {normalized_path(s["file_path"]) for s in catalog if s.get("file_path")}
        watched = {normalized_path(s["file_path"]) for s in catalog
                   if s["session_id"] == watch_session_id and s.get("file_path")}
        # Internal review logs must not crowd out the latest user interruption.
        # Keep the active target under observation even after its log gets old.
        selected_paths = dict.fromkeys(
            [p for _, p in paths[:limit]]
            + [p for _, p in paths if normalized_path(p) in visible][:limit]
            + [p for _, p in paths if normalized_path(p) in watched]
        )
        sessions = []
        for path in selected_paths:
            try:
                s = self._read(path)
                if s["session_id"]:
                    sessions.append(s)
            except OSError as exc:
                warnings.append(str(exc))
        self._cache = {p: v for p, v in self._cache.items() if p in selected_paths}
        buckets = {}
        for session in sessions:
            limits = session["limits"]
            if limits:
                key = limits.get("limit_id") or "codex"
                if session["limits_at"] >= buckets.get(key, {}).get("observed_at", 0):
                    buckets[key] = {
                        **limits,
                        "observed_at": session["limits_at"],
                        "source": session["file_path"],
                    }
        return {
            "sessions": read_session_catalog(self.codex_dir, sessions, warnings),
            "buckets": buckets,
            "warnings": warnings,
            "scanned_at": time.time(),
            "sessions_dir": str(self.sessions_dir),
            "available": self.sessions_dir.is_dir(),
        }


def scan_all_sessions(limit=50):
    return SessionScanner().scan(limit)["sessions"]


def get_rate_limit_stats(days=7, sessions=None):
    sessions = sessions if sessions is not None else scan_all_sessions(500)
    recent = [
        s for s in sessions if s.get("updated_at", 0) >= time.time() - days * 86400
    ]
    return {
        "sessions_count": len(recent),
        "total_triggers": sum(bool(s["had_rate_limit"]) for s in recent),
    }


def get_available_models(codex_dir=None):
    try:
        data = json.loads(
            ((codex_dir or get_codex_dir()) / "models_cache.json").read_text(
                encoding="utf-8"
            )
        )
        items = data if isinstance(data, list) else data.get("models", [])
        return [
            {
                "slug": m["slug"],
                "display_name": m.get("display_name") or m["slug"],
                "description": m.get("description", ""),
            }
            for m in items
            if isinstance(m, dict) and m.get("slug") and m.get("visibility") != "hide"
        ]
    except (OSError, ValueError, TypeError, AttributeError):
        return []
