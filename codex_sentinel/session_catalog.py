"""Build the local conversation picker from Codex's index, not rollout mtimes.

The desktop source uses interactive, non-archived threads, display names,
recency timestamps and persisted project membership. All reads here are local.
"""

from __future__ import annotations

import json
import math
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath


def normalized_path(value):
    value = str(value or "")
    if "\\" in value or (len(value) > 1 and value[1] == ":"):
        value = value.replace("\\", "/")
        if value.startswith("//?/UNC/"):
            value = "//" + value[8:]
        elif value.startswith("//?/"):
            value = value[4:]
        value = value.casefold()
    return value.rstrip("/")


def folder_name(value):
    path = (
        PureWindowsPath(value)
        if "\\" in value or ":" in value
        else PurePosixPath(value)
    )
    return path.name or value


def is_visible_thread(row):
    # An omitted source in old metadata is unknown; a recorded noninteractive
    # source must never become a selectable/resumable user conversation.
    source = row.get("source")
    return (
        not row.get("archived")
        and not row.get("ephemeral")
        and (source is None or source in ("", "cli", "vscode"))
        and row.get("thread_source")
        not in (
            "guardian_review",
            "guardian_classifier",
            "subagent",
            "system",
            "chatgpt_hidden",
            "ambient_suggestions",
        )
    )


def _read_table(conn, table, wanted):
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    selected = [key for key in wanted if key in columns]
    if not selected:
        return []
    return [
        dict(row) for row in conn.execute(f"SELECT {','.join(selected)} FROM {table}")
    ]


def _read_index(codex_dir, warnings):
    db = codex_dir / "state_5.sqlite"
    if not db.exists():
        return [], [], []
    try:
        with closing(
            sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.2)
        ) as conn:
            conn.row_factory = sqlite3.Row
            threads = _read_table(
                conn,
                "threads",
                (
                    "id",
                    "name",
                    "title",
                    "preview",
                    "model",
                    "cwd",
                    "tokens_used",
                    "source",
                    "thread_source",
                    "archived",
                    "rollout_path",
                    "project_id",
                    "created_at",
                    "updated_at",
                    "recency_at",
                    "created_at_ms",
                    "updated_at_ms",
                    "recency_at_ms",
                ),
            )
            projects = _read_table(conn, "projects", ("id", "name", "position"))
            roots = _read_table(
                conn, "project_roots", ("project_id", "path", "position")
            )
            return threads, projects, roots
    except (sqlite3.Error, OSError) as exc:
        warnings.append(f"SQLite metadata unavailable: {exc}")
        return [], [], []


def _read_state(codex_dir, warnings):
    path = codex_dir / ".codex-global-state.json"
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        return state if isinstance(state, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        warnings.append(f"Sidebar metadata unavailable: {exc}")
        return {}


def _timestamp(row, key, fallback=0):
    for value, scale in ((row.get(key + "_ms"), 1000), (row.get(key), 1), (fallback, 1)):
        if value is None:
            continue
        try:
            try:
                result = float(value) / scale
            except (ValueError, TypeError):
                if scale != 1 or not isinstance(value, str):
                    continue
                result = datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
            if math.isfinite(result):
                # The GUI must be able to render this timestamp on this OS.
                datetime.fromtimestamp(result)
                return result
        except (ValueError, TypeError, OverflowError, OSError):
            continue
    return 0.0


def _projects(state, db_projects, db_roots, codex_dir):
    projects = {
        key: {"name": value.get("name") or key, "roots": value.get("rootPaths") or []}
        for key, value in (state.get("local-projects") or {}).items()
        if isinstance(value, dict)
    }
    aliases = {}
    for host, mapping in (
        state.get("app-server-project-id-by-legacy-project-id-by-host") or {}
    ).items():
        if host.startswith("local:") and normalized_path(host[6:]) == normalized_path(
            codex_dir
        ):
            aliases.update({new: old for old, new in mapping.items()})
    order = list(state.get("project-order") or [])
    for row in sorted(db_projects, key=lambda p: p.get("position", 0)):
        key = aliases.get(row["id"], row["id"])
        project = projects.setdefault(key, {"roots": []})
        project["name"] = row.get("name") or project.get("name") or key
        if key not in order:
            order.append(key)
    for row in db_roots:
        key = aliases.get(row["project_id"], row["project_id"])
        if key in projects and row.get("path"):
            projects[key]["roots"].append(row["path"])
    return projects, aliases, order


def _group_and_sort(sessions, state, projects, aliases, order):
    assignments = state.get("thread-project-assignments") or {}
    projectless = set(state.get("projectless-thread-ids") or [])
    hints = state.get("thread-workspace-root-hints") or {}
    roots = sorted(
        (
            (normalized_path(root), key)
            for key, p in projects.items()
            for root in p["roots"]
            if root
        ),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    for s in sessions:
        sid, cwd = s["session_id"], s["cwd"]
        key = aliases.get(s.get("project_id"), s.get("project_id"))
        assignment = assignments.get(sid) or {}
        if key not in projects and assignment.get("projectKind") == "local":
            key = assignment.get("projectId")
        is_projectless = sid in projectless and key not in projects
        if key not in projects and not is_projectless and not assignment:
            path = normalized_path(hints.get(sid) or cwd)
            key = next(
                (
                    pid
                    for root, pid in roots
                    if path == root or path.startswith(root + "/")
                ),
                None,
            )
        if key in projects:
            s.update(project_key=key, project_name=projects[key]["name"])
        elif is_projectless or not cwd:
            s.update(project_key="projectless", project_name="")
        else:
            s.update(
                project_key="cwd:" + normalized_path(cwd), project_name=folder_name(cwd)
            )

    # Codex's project order is persisted separately. "Updated" conversation
    # sorting uses recencyAt (user activity), not the file or background updates.
    ranks = {key: i for i, key in enumerate(order)}
    groups = {}
    for s in sessions:
        groups.setdefault(s["project_key"], []).append(s)
    prefs = (state.get("electron-persisted-atom-state") or {}).get(
        "flat-project-sidebar-preferences-v1"
    ) or {}
    manual = (
        prefs.get("projectSortMode") == "manual" and prefs.get("manualSortVersion") == 1
    )
    manual_orders = state.get("sidebar-project-thread-orders") or {}
    result = []
    for key, items in sorted(
        groups.items(),
        key=lambda pair: (
            ranks.get(pair[0], len(ranks)),
            -max(s["recency_at"] for s in pair[1]),
            pair[0],
        ),
    ):
        items.sort(key=lambda s: (s["recency_at"], s["session_id"]), reverse=True)
        if manual:
            ids = (manual_orders.get(key) or {}).get("threadIds") or []
            positions = {sid: i for i, sid in enumerate(ids)}
            items.sort(key=lambda s: positions.get(s["session_id"], len(positions)))
        result.extend(items)
    return result


def read_session_catalog(codex_dir: Path, rollouts: list[dict], warnings: list[str]):
    rows, db_projects, db_roots = _read_index(codex_dir, warnings)
    by_id = {s["session_id"]: s for s in rollouts}
    hidden = set()
    for row in rows:
        sid = row.get("id")
        if not sid:
            continue
        if not is_visible_thread(row):
            hidden.add(sid)
            continue
        s = by_id.setdefault(
            sid,
            {
                "session_id": sid,
                "title": "",
                "cwd": "",
                "model": "",
                "started_at": 0,
                "total_turns": None,
                "had_rate_limit": False,
                "task_status": "unknown",
                "error_msg": "",
                "limits": {},
                "limits_at": 0.0,
                "limited_at": 0.0,
                "tokens_used": None,
                "file_path": row.get("rollout_path") or "",
            },
        )
        for key in ("model", "cwd", "tokens_used"):
            if row.get(key) is not None and not s.get(key):
                s[key] = row[key]
        name = (row.get("name") or "").strip()
        fallback = " ".join((row.get("preview") or row.get("title") or "").split())
        s["title"] = (
            name
            or (fallback if len(fallback) <= 60 else fallback[:59] + "…")
            or s["title"]
        )
        s["project_id"] = row.get("project_id")
        s["started_at"] = _timestamp(row, "created_at", s["started_at"])
        s["updated_at"] = _timestamp(
            row, "updated_at", s.get("updated_at", s["started_at"])
        )
        s["recency_at"] = _timestamp(row, "recency_at", s["updated_at"])
    sessions = [
        s for sid, s in by_id.items() if sid not in hidden and is_visible_thread(s)
    ]
    for s in sessions:
        s.setdefault("recency_at", s.get("updated_at", 0))
    state = _read_state(codex_dir, warnings)
    projects, aliases, order = _projects(state, db_projects, db_roots, codex_dir)
    return _group_and_sort(sessions, state, projects, aliases, order)
