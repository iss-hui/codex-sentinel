import json
import sqlite3

from codex_sentinel.session_scanner import (
    SessionScanner,
    blocking_reset,
    get_available_models,
)


def append(path, *events):
    with path.open("a", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")


def event(kind, **payload):
    return {
        "timestamp": "2026-10-02T01:00:00Z",
        "type": "event_msg",
        "payload": {"type": kind, **payload},
    }


def test_incremental_null_partial_and_latest_percent(tmp_path):
    path = tmp_path / "rollout.jsonl"
    append(
        path,
        {"type": "session_meta", "payload": {"id": "s1", "cwd": str(tmp_path)}},
        event(
            "token_count",
            rate_limits={"primary": {"used_percent": 90, "resets_at": 900}},
        ),
        event("token_count", rate_limits=None),
    )
    scanner = SessionScanner(tmp_path, tmp_path)
    first = scanner.scan()
    assert first["buckets"]["codex"]["primary"]["used_percent"] == 90
    with path.open("a", encoding="utf-8") as f:
        f.write('{"type": "turn_context", "payload":')
    assert scanner.scan()["sessions"][0]["total_turns"] == 0
    with path.open("a", encoding="utf-8") as f:
        f.write('{"model":"local-model"}}\n')
    append(
        path,
        event(
            "token_count",
            rate_limits={"primary": {"used_percent": 10, "resets_at": 1900}},
        ),
    )
    snapshot = scanner.scan()
    assert snapshot["sessions"][0]["total_turns"] == 1
    assert snapshot["sessions"][0]["model"] == "local-model"
    assert snapshot["buckets"]["codex"]["primary"]["used_percent"] == 10
    assert scanner.scan()["sessions"][0]["total_turns"] == 1
    # Callers must not mutate the scanner's cached state.
    snapshot["sessions"][0]["limits"]["primary"]["used_percent"] = 99
    assert scanner.scan()["buckets"]["codex"]["primary"]["used_percent"] == 10


def test_metadata_schema_is_optional_and_read_only(tmp_path):
    db = tmp_path / "state_5.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE threads (id TEXT, title TEXT, cwd TEXT, tokens_used INTEGER)"
        )
        conn.execute(
            "INSERT INTO threads VALUES ('s1','A title',?,42)", (str(tmp_path),)
        )
    original = db.read_bytes()
    append(tmp_path / "r.jsonl", {"type": "session_meta", "payload": {"id": "s1"}})
    result = SessionScanner(tmp_path, tmp_path).scan()
    assert result["sessions"][0]["title"] == "A title"
    assert result["sessions"][0]["tokens_used"] == 42
    assert db.read_bytes() == original
    assert not result["warnings"]


def test_resumed_turn_invalidates_old_interruption(tmp_path):
    path = tmp_path / "r.jsonl"
    append(
        path,
        {"type": "session_meta", "payload": {"id": "s1"}},
        event("task_complete", error={"codex_error_info": "usage_limit_exceeded"}),
    )
    scanner = SessionScanner(tmp_path, tmp_path)
    assert scanner.scan()["sessions"][0]["task_status"] == "rate_limited"
    append(path, event("task_started"))
    assert scanner.scan()["sessions"][0]["task_status"] == "running"
    append(path, event("task_complete"))
    assert scanner.scan()["sessions"][0]["task_status"] == "completed"


def test_weekly_limit_is_respected():
    limits = {
        "primary": {"used_percent": 100, "resets_at": 200},
        "secondary": {"used_percent": 100, "resets_at": 900},
    }
    assert blocking_reset(limits, 100) == 900
    assert blocking_reset(limits, 1000) == 0


def test_missing_models_are_not_invented(tmp_path):
    assert get_available_models(tmp_path) == []
    (tmp_path / "models_cache.json").write_text(
        json.dumps(
            {
                "models": [
                    {"slug": "a", "display_name": "A"},
                    {"slug": "hidden", "visibility": "hide"},
                ]
            }
        )
    )
    assert [m["slug"] for m in get_available_models(tmp_path)] == ["a"]


def test_unknown_data_remains_unknown(tmp_path):
    snapshot = SessionScanner(tmp_path / "missing", tmp_path).scan()
    assert snapshot["buckets"] == {}
    assert snapshot["warnings"]


def test_catalog_excludes_internal_and_archived_without_losing_older_chats(tmp_path):
    db = tmp_path / "state_5.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE threads (id TEXT, name TEXT, title TEXT, source TEXT, thread_source TEXT, archived INTEGER, recency_at INTEGER, updated_at INTEGER)"
        )
        conn.executemany(
            "INSERT INTO threads VALUES (?,?,?,?,?,?,?,?)",
            [
                (
                    "old",
                    "优化项目描述",
                    "Original prompt",
                    "vscode",
                    "user",
                    0,
                    100,
                    900,
                ),
                (
                    "new",
                    "Implement Codex desktop app",
                    "Original prompt",
                    "vscode",
                    "user",
                    0,
                    200,
                    200,
                ),
                (
                    "guardian",
                    "Guardian review",
                    "Review",
                    '{"subagent":{"other":"guardian"}}',
                    "guardian_review",
                    0,
                    400,
                    400,
                ),
                (
                    "child",
                    "Subtask",
                    "Prompt",
                    '{"subagent":{"thread_spawn":{}}}',
                    "subagent",
                    0,
                    300,
                    300,
                ),
                ("archived", "Archived", "Prompt", "vscode", "user", 1, 800, 800),
                ("exec", "Background execution", "Prompt", "exec", "user", 0, 800, 800),
                (
                    "named-guardian",
                    "Guardian review",
                    "User named it",
                    "vscode",
                    "user",
                    0,
                    50,
                    50,
                ),
            ],
        )
    original = db.read_bytes()
    # The only recently scanned log is an internal review. Older user chats
    # still appear via the full index, while its quota observation is retained.
    append(
        tmp_path / "r.jsonl",
        {
            "type": "session_meta",
            "payload": {
                "id": "guardian",
                "source": {"subagent": {"other": "guardian"}},
            },
        },
        event(
            "token_count",
            rate_limits={"primary": {"used_percent": 90, "resets_at": 900}},
        ),
        event("task_complete", error={"codex_error_info": "usage_limit_exceeded"}),
    )
    result = SessionScanner(tmp_path, tmp_path).scan(limit=1)
    assert [s["session_id"] for s in result["sessions"]] == [
        "new",
        "old",
        "named-guardian",
    ]
    assert result["sessions"][1]["title"] == "优化项目描述"
    assert result["sessions"][1]["task_status"] == "unknown"
    assert result["sessions"][1]["total_turns"] is None
    assert result["buckets"]["codex"]["primary"]["used_percent"] == 90
    assert db.read_bytes() == original
    assert not result["warnings"]


def test_project_membership_names_order_and_windows_paths(tmp_path):
    with sqlite3.connect(tmp_path / "state_5.sqlite") as conn:
        conn.execute(
            "CREATE TABLE threads (id TEXT, name TEXT, cwd TEXT, source TEXT, recency_at INTEGER, project_id TEXT)"
        )
        conn.executemany(
            "INSERT INTO threads VALUES (?,?,?,?,?,?)",
            [
                (
                    "root",
                    "Root conversation",
                    r"\\?\D:\Work\Repo\src",
                    "vscode",
                    300,
                    None,
                ),
                (
                    "child",
                    "Child project",
                    r"d:\work\repo\child\src",
                    "vscode",
                    500,
                    None,
                ),
                ("moved", "Explicit membership", r"D:\Elsewhere", "vscode", 100, None),
                ("new-id", "Migrated project", r"D:\Elsewhere", "vscode", 200, "db-a"),
                ("no-project", "Projectless", r"D:\Work\Repo", "vscode", 600, None),
            ],
        )
        conn.execute("CREATE TABLE projects (id TEXT, name TEXT, position INTEGER)")
        conn.execute("INSERT INTO projects VALUES ('db-a','Renamed project',0)")
        conn.execute(
            "CREATE TABLE project_roots (project_id TEXT, path TEXT, position INTEGER)"
        )
        conn.execute(
            "INSERT INTO project_roots VALUES ('db-a',?,0)", (r"D:\Work\Repo",)
        )
    state = {
        "local-projects": {
            "a": {"name": "Old name", "rootPaths": [r"D:\Work\Repo"]},
            "b": {"name": "Child folder", "rootPaths": [r"D:\Work\Repo\child"]},
        },
        "project-order": ["a", "b"],
        "app-server-project-id-by-legacy-project-id-by-host": {
            "local:" + str(tmp_path): {"a": "db-a"}
        },
        "thread-project-assignments": {
            "moved": {"projectKind": "local", "projectId": "a"}
        },
        "projectless-thread-ids": ["no-project"],
    }
    state_file = tmp_path / ".codex-global-state.json"
    state_file.write_text(json.dumps(state), encoding="utf-8")
    result = SessionScanner(tmp_path, tmp_path).scan()["sessions"]
    assert [s["session_id"] for s in result] == [
        "root",
        "new-id",
        "moved",
        "child",
        "no-project",
    ]
    assert [s["project_name"] for s in result] == ["Renamed project"] * 3 + [
        "Child folder",
        "",
    ]
    assert json.loads(state_file.read_text("utf-8")) == state


def test_missing_database_still_hides_internal_rollouts(tmp_path):
    append(
        tmp_path / "internal.jsonl",
        {
            "type": "session_meta",
            "payload": {
                "id": "internal",
                "source": {"subagent": {"other": "guardian"}},
            },
        },
    )
    append(
        tmp_path / "user.jsonl",
        {
            "type": "session_meta",
            "payload": {
                "id": "user",
                "source": "vscode",
            },
        },
    )
    assert [
        s["session_id"] for s in SessionScanner(tmp_path, tmp_path).scan()["sessions"]
    ] == ["user"]
