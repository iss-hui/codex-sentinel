import json
import time
from pathlib import Path

from codex_sentinel.detector import parse_session_file


def test_parse_session_normal(tmp_path: Path):
    file = tmp_path / "normal_session.jsonl"
    lines = [
        json.dumps({"type": "session_meta", "payload": {"id": "test-session-1", "cwd": "/work"}}),
        json.dumps({"type": "turn_context", "payload": {"model": "gpt-5-preview"}}),
        json.dumps({"type": "event_msg", "payload": {"type": "token_count", "rate_limits": {"primary": {"used_percent": 30.0, "resets_at": time.time() + 3600}}}}),
        json.dumps({"type": "event_msg", "payload": {"type": "task_complete", "error": None}}),
    ]
    file.write_text("\n".join(lines), encoding="utf-8")

    result = parse_session_file(file)
    assert result is None


def test_parse_session_rate_limited(tmp_path: Path):
    file = tmp_path / "rate_limited_session.jsonl"
    future_reset = time.time() + 1800
    lines = [
        json.dumps({"type": "session_meta", "payload": {"id": "test-session-rate-limit", "cwd": "/work"}}),
        json.dumps({"type": "turn_context", "payload": {"model": "gpt-6-astra"}}),
        json.dumps({
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "rate_limits": {
                    "primary": {
                        "used_percent": 100.0,
                        "resets_at": future_reset,
                    }
                },
            },
        }),
        json.dumps({
            "type": "event_msg",
            "payload": {
                "type": "task_complete",
                "error": {
                    "message": "You've hit the usage limit.",
                    "codex_error_info": "usage_limit_exceeded",
                },
            },
        }),
    ]
    file.write_text("\n".join(lines), encoding="utf-8")

    result = parse_session_file(file)
    assert result is not None
    assert result["session_id"] == "test-session-rate-limit"
    assert result["model"] == "gpt-6-astra"
    assert result["resets_at"] == future_reset
    assert result["cwd"] == "/work"


def test_parse_session_expired_rate_limit(tmp_path: Path):
    file = tmp_path / "expired_session.jsonl"
    past_reset = time.time() - 100
    lines = [
        json.dumps({"type": "session_meta", "payload": {"id": "test-session-expired", "cwd": "/work"}}),
        json.dumps({"type": "turn_context", "payload": {"model": "gpt-6-astra"}}),
        json.dumps({
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "rate_limits": {
                    "primary": {
                        "used_percent": 100.0,
                        "resets_at": past_reset,
                    }
                },
            },
        }),
        json.dumps({
            "type": "event_msg",
            "payload": {
                "type": "task_complete",
                "error": {
                    "codex_error_info": "usage_limit_exceeded",
                },
            },
        }),
    ]
    file.write_text("\n".join(lines), encoding="utf-8")

    result = parse_session_file(file)
    assert result is None
