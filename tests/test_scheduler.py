import pytest

from codex_sentinel.config import DEFAULT_CONFIG, ConfigManager
from codex_sentinel.quota_scheduler import QuotaScheduler


def settings(**changes):
    return {**DEFAULT_CONFIG, **changes}


def test_schedule_buffer_weekly_and_once(tmp_path):
    queue = QuotaScheduler(tmp_path)
    task = queue.add_task(
        "test", "hello", str(tmp_path), scheduled_at=1000, buffer_seconds=30
    )
    snapshot = {
        "buckets": {
            "codex": {
                "primary": {"used_percent": 100, "resets_at": 1100},
                "secondary": {"used_percent": 100, "resets_at": 2000},
            }
        }
    }
    assert queue.due_task(snapshot, settings(), 1030) is None
    assert task.deferred_until == 2000
    assert queue.due_task(snapshot, settings(), 2029) is None
    assert queue.due_task(snapshot, settings(), 2030) is task
    queue.update(task, status="running")
    assert queue.due_task(snapshot, settings(), 2031) is None
    queue.update(task, status="completed")
    assert QuotaScheduler(tmp_path).due_task(snapshot, settings(), 2032) is None


def test_missed_and_interrupted_are_not_replayed(tmp_path):
    queue = QuotaScheduler(tmp_path)
    task = queue.add_task("one", "hello", str(tmp_path), scheduled_at=1000)
    assert queue.due_task({}, settings(), 1500) is None
    assert task.status == "missed"
    queue.retry(task.id, now=1500)
    assert queue.due_task({}, settings(), 1530) is task
    queue.update(task, status="running")
    restored = QuotaScheduler(tmp_path)
    assert restored.get(task.id).status == "interrupted"
    assert restored.due_task({}, settings(), 1531) is None


def test_disabled_queue_and_unscheduled_legacy_items(tmp_path):
    queue = QuotaScheduler(tmp_path)
    legacy = queue.add_task("legacy", "hello", str(tmp_path))
    assert queue.due_task({}, settings(), 1000) is None
    scheduled = queue.add_task("new", "hello", str(tmp_path), scheduled_at=1000)
    assert queue.due_task({}, settings(queue_enabled=False), 1030) is None
    queue.reorder_tasks([scheduled.id, scheduled.id, legacy.id])
    assert len(queue.task_queue) == 2
    assert queue.due_task({}, settings(), 1030) is scheduled


def test_atomic_save_failure_never_marks_running(tmp_path, monkeypatch):
    queue = QuotaScheduler(tmp_path)
    task = queue.add_task("test", "hello", str(tmp_path), scheduled_at=1000)

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr("codex_sentinel.quota_scheduler.write_json", fail)
    with pytest.raises(OSError):
        queue.update(task, status="running")
    assert task.status == "pending"
    assert QuotaScheduler(tmp_path).get(task.id).status == "pending"


def test_config_round_trip_and_corrupt_file_preserved(tmp_path):
    config = ConfigManager(tmp_path)
    assert config.load()["auto_resume"] is False
    config.save({"buffer_seconds": 60, "resume_prompt": "继续\n完成任务"})
    assert ConfigManager(tmp_path).load()["resume_prompt"] == "继续\n完成任务"
    with pytest.raises(ValueError):
        config.save({"buffer_seconds": -1})
    assert ConfigManager(tmp_path).load()["buffer_seconds"] == 60
    config.config_file.write_text("broken", encoding="utf-8")
    with pytest.raises(ValueError):
        ConfigManager(tmp_path).load()
    assert config.config_file.read_text() == "broken"
