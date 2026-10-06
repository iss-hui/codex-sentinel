import copy

import pytest

from codex_sentinel.config import DEFAULT_CONFIG
from codex_sentinel.quota_scheduler import QuotaScheduler
from codex_sentinel.recovery_monitor import RecoveryMonitor


def settings(**updates):
    return {**DEFAULT_CONFIG, "auto_resume": True, **updates}


def session(tmp_path, sid="latest", at=900, reset=1000, **updates):
    return {"session_id": sid, "title": sid, "cwd": str(tmp_path), "model": "m",
            "limited_at": at, "task_status": "rate_limited", "status_at": at,
            "limits": {"limit_id": "codex", "primary": {"used_percent": 100, "resets_at": reset}},
            **updates}


def observe(monitor, *sessions, now=1030, **snapshot):
    monitor.observe({"sessions": list(sessions), **snapshot}, now)


def test_latest_interruption_not_file_mtime_or_queue_order(tmp_path):
    monitor = RecoveryMonitor(tmp_path)
    older = session(tmp_path, "old", at=800, updated_at=9999)
    newest = session(tmp_path, "new", at=900, updated_at=1000)
    observe(monitor, older, newest)
    assert monitor.due_task(settings(queue_enabled=False), 1029) is None
    task = monitor.due_task(settings(queue_enabled=False), 1030)
    assert task.session_id == "new" and task.sandbox == "workspace-write"
    assert not (tmp_path / "task_queue.json").exists()
    observe(monitor, older, newest, session(tmp_path, "newer", at=950, reset=1100))
    assert monitor.target["session_id"] == "newer"
    assert monitor.due_task(settings(), 1030) is None


def test_internal_and_manually_stopped_chats_are_not_resumed(tmp_path):
    monitor = RecoveryMonitor(tmp_path)
    hidden = session(tmp_path, "guardian", at=950, source="subagent")
    observe(monitor, session(tmp_path), hidden)
    assert monitor.target["session_id"] == "latest"
    stopped = session(tmp_path, "stopped", at=975, task_status="interrupted")
    observe(monitor, session(tmp_path), stopped)
    assert monitor.due_task(settings(), 2000) is None
    # Never fall back to an older interruption when the newest chat continued.
    observe(monitor, session(tmp_path))
    assert monitor.due_task(settings(), 2000) is None


def test_user_continuation_cancels_wait_and_no_historical_fallback(tmp_path):
    monitor = RecoveryMonitor(tmp_path)
    latest = session(tmp_path)
    observe(monitor, latest)
    latest["task_status"] = "running"
    observe(monitor, latest, session(tmp_path, "old", at=800))
    assert monitor.target["status"] == "cancelled"
    assert monitor.due_task(settings(), 2000) is None


def test_expired_record_and_weekly_limit_require_known_times(tmp_path):
    monitor = RecoveryMonitor(tmp_path)
    s = session(tmp_path, reset=850)
    observe(monitor, s)
    assert monitor.due_task(settings(), 5000) is None
    s["limits"]["primary"]["resets_at"] = 1000
    s["limits"]["secondary"] = {"used_percent": 100, "resets_at": 2000}
    observe(monitor, s)
    assert monitor.due_task(settings(), 2029) is None
    assert monitor.due_task(settings(), 2030) is not None
    s["limits"]["secondary"]["resets_at"] = None
    observe(monitor, s)
    assert monitor.due_task(settings(), 3000) is None


def test_latest_shared_bucket_delays_recovery_and_sleep_has_no_missed_grace(tmp_path):
    monitor = RecoveryMonitor(tmp_path)
    s = session(tmp_path)
    observe(monitor, s, buckets={"codex": {"observed_at": 950,
        "primary": {"used_percent": 100, "resets_at": 1400}}})
    assert monitor.due_task(settings(), 1030) is None
    assert monitor.due_task(settings(), 20000) is not None
    assert monitor.due_task(settings(auto_resume=False), 20000) is None


def test_completed_cycle_is_not_replayed_after_restart_and_next_cycle_runs(tmp_path):
    monitor = RecoveryMonitor(tmp_path)
    s = session(tmp_path)
    observe(monitor, s)
    task = monitor.due_task(settings(), 1030)
    monitor.start(task, tmp_path / "recovery.log", 1030)
    monitor.complete(task, {"code": 0}, 1040)
    restored = RecoveryMonitor(tmp_path)
    observe(restored, s, session(tmp_path, "old", at=800))
    assert restored.due_task(settings(), 1041) is None
    observe(restored, session(tmp_path, at=1100, reset=1500), now=1100)
    assert restored.target["next_reset_at"] == 1500
    assert restored.due_task(settings(), 1529) is None
    assert restored.due_task(settings(), 1530) is not None
    assert len(restored.history_tasks()) == 1


def test_quota_error_waits_for_new_reset_instead_of_immediate_loop(tmp_path):
    monitor = RecoveryMonitor(tmp_path)
    s = session(tmp_path)
    observe(monitor, s)
    task = monitor.due_task(settings(), 1030)
    monitor.start(task, tmp_path / "run.log", 1030)
    monitor.complete(task, {"code": 1, "error": "usage limit reached"}, 1040)
    observe(monitor, s)
    assert monitor.due_task(settings(), 2000) is None
    s["limits"]["primary"]["resets_at"] = 3000
    observe(monitor, s)
    assert monitor.due_task(settings(), 3029) is None
    assert monitor.due_task(settings(), 3030) is not None


def test_network_retry_has_backoff_and_stops_after_three_attempts(tmp_path):
    monitor = RecoveryMonitor(tmp_path)
    s = session(tmp_path)
    observe(monitor, s)
    for start, finish, retry in ((1030, 1040, 1070), (1070, 1080, 1140), (1140, 1150, None)):
        task = monitor.due_task(settings(), start)
        assert task is not None
        monitor.start(task, tmp_path / "run.log", start)
        monitor.complete(task, {"code": 1, "error": "network connection lost"}, finish)
        s.update(task_status="error", status_at=finish - 1)
        observe(monitor, s, now=finish)
        if retry:
            assert monitor.due_task(settings(), retry - 1) is None
            assert monitor.due_task(settings(), retry) is not None
    assert monitor.target["status"] == "failed"
    assert monitor.due_task(settings(), 9000) is None
    assert len(monitor.history_tasks()) == 3


@pytest.mark.parametrize("result", [{"code": 130}, {"code": 1, "error": "approval denied"},
                                   {"code": 0, "cleanup_ok": False}])
def test_cancel_permissions_and_cleanup_failure_are_not_retried(tmp_path, result):
    monitor = RecoveryMonitor(tmp_path)
    observe(monitor, session(tmp_path))
    task = monitor.due_task(settings(), 1030)
    monitor.start(task, tmp_path / "run.log", 1030)
    monitor.complete(task, result, 1040)
    assert monitor.due_task(settings(), 9000) is None


def test_crash_does_not_repeat_running_recovery(tmp_path):
    monitor = RecoveryMonitor(tmp_path)
    s = session(tmp_path)
    observe(monitor, s)
    task = monitor.due_task(settings(), 1030)
    monitor.start(task, tmp_path / "run.log", 1030)
    restored = RecoveryMonitor(tmp_path)
    observe(restored, s)
    assert restored.due_task(settings(), 1100) is None
    assert restored.history_tasks()[0].status == "interrupted"
    assert len(RecoveryMonitor(tmp_path).history_tasks()) == 1


def test_save_failure_does_not_advance_monitor(tmp_path, monkeypatch):
    monitor = RecoveryMonitor(tmp_path)
    observe(monitor, session(tmp_path))
    before = copy.deepcopy(monitor.state)
    task = monitor.due_task(settings(), 1030)
    def fail(*args):
        raise OSError("disk full")
    monkeypatch.setattr("codex_sentinel.recovery_monitor.write_json", fail)
    with pytest.raises(OSError):
        monitor.start(task, tmp_path / "run.log", 1030)
    assert monitor.state == before


def test_missing_directory_never_uses_sentinel_working_directory(tmp_path):
    monitor = RecoveryMonitor(tmp_path)
    observe(monitor, session(tmp_path, "old", at=800), session(tmp_path, cwd=""))
    assert monitor.due_task(settings(), 9000) is None
    observe(monitor, session(tmp_path, cwd=str(tmp_path / "gone")))
    assert monitor.due_task(settings(), 9000) is None


def test_legacy_queue_migration_preserves_history_and_manual_permissions(tmp_path, monkeypatch):
    queue = QuotaScheduler(tmp_path)
    old = queue.add_task("old recovery", "go", str(tmp_path), kind="resume", auto_key="s:800:1000")
    queue.update(old, status="completed")
    pending = queue.add_task("waiting recovery", "go", str(tmp_path), kind="resume", auto_key="s:900:1000")
    manual = queue.add_task("manual", "go", str(tmp_path), sandbox="read-only")
    monitor = RecoveryMonitor(tmp_path)
    save = queue.save
    monkeypatch.setattr(queue, "save", lambda: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        monitor.migrate_legacy(queue)
    assert len(queue.task_queue) == 3
    monkeypatch.setattr(queue, "save", save)
    monitor = RecoveryMonitor(tmp_path)
    monitor.migrate_legacy(queue)
    assert queue.task_queue == [manual] and manual.sandbox == "read-only"
    assert [task.id for task in monitor.history_tasks()] == [old.id, pending.id]
    observe(monitor, session(tmp_path, at=800))
    assert monitor.due_task(settings(), 1030) is None
    observe(monitor, session(tmp_path, at=900))
    assert monitor.due_task(settings(), 1030) is not None
