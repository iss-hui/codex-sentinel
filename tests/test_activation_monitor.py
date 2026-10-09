from pathlib import Path

import pytest

from codex_sentinel.activation_monitor import ACTIVATION_PROMPT, ActivationMonitor
from codex_sentinel.config import DEFAULT_CONFIG, ConfigManager


def settings(tmp_path, **updates):
    return {
        **DEFAULT_CONFIG,
        "auto_activate": True,
        "activation_cwd": str(tmp_path),
        "activation_bucket": "codex",
        "activation_model": "chosen-model",
        **updates,
    }


def snapshot(reset=1000, secondary=None):
    return {
        "buckets": {
            "codex": {
                "primary": {
                    "window_minutes": 300,
                    "used_percent": 100,
                    "resets_at": reset,
                },
                "secondary": secondary,
            }
        }
    }


def finish(monitor, task, now, **result):
    monitor.start(task, Path(task.cwd) / "activation.log", now)
    monitor.complete(task, {"code": 0, "session_id": "new-session", **result}, now + 1)


def test_activation_waits_for_reset_and_buffer_then_uses_fresh_readonly_chat(tmp_path):
    monitor = ActivationMonitor(tmp_path)
    config = settings(tmp_path)
    assert monitor.due_task(snapshot(), config, 1029) is None
    task = monitor.due_task(snapshot(), config, 1030)
    assert task.session_id == "" and task.sandbox == "read-only"
    assert task.kind == "activation" and task.model == "chosen-model"
    assert task.prompt == ACTIVATION_PROMPT
    assert task.cwd == str(tmp_path)


def test_each_recorded_window_runs_once_even_after_restart(tmp_path):
    config = settings(tmp_path, queue_enabled=False)
    monitor = ActivationMonitor(tmp_path)
    task = monitor.due_task(snapshot(), config, 1030)
    finish(monitor, task, 1030)
    monitor = ActivationMonitor(tmp_path)
    assert monitor.due_task(snapshot(), config, 1040) is None
    assert monitor.due_task(snapshot(), config, 20000) is None  # No invented reset.
    task = monitor.due_task(snapshot(19000), config, 19030)
    assert task.session_id == ""  # Never reuse the previous activation's chat.
    finish(monitor, task, 19030)
    assert len(monitor.history_tasks()) == 2
    assert (
        monitor.due_task(snapshot(1000), config, 20000) is None
    )  # Old records cannot replay.


@pytest.mark.parametrize("code", [1, 130])
def test_failed_or_cancelled_attempt_does_not_loop_in_same_window(tmp_path, code):
    config = settings(tmp_path)
    monitor = ActivationMonitor(tmp_path)
    finish(
        monitor,
        monitor.due_task(snapshot(), config, 1030),
        1030,
        code=code,
        error="stopped",
    )
    restarted = ActivationMonitor(tmp_path)
    assert restarted.due_task(snapshot(), config, 2000) is None
    assert restarted.due_task(snapshot(2000), config, 2030) is not None


def test_crash_after_start_is_recorded_and_never_replayed(tmp_path):
    config = settings(tmp_path)
    monitor = ActivationMonitor(tmp_path)
    task = monitor.due_task(snapshot(), config, 1030)
    monitor.start(task, tmp_path / "run.log", 1030)
    restarted = ActivationMonitor(tmp_path)
    assert restarted.target["status"] == "interrupted"
    assert restarted.history_tasks()[0].log_file == str(tmp_path / "run.log")
    assert restarted.due_task(snapshot(), config, 1100) is None


def test_weekly_quota_delays_activation(tmp_path):
    monitor = ActivationMonitor(tmp_path)
    data = snapshot(
        1000, {"window_minutes": 10080, "used_percent": 100, "resets_at": 5000}
    )
    config = settings(tmp_path)
    assert monitor.plan(data, config, 1030)["due"] == 5030
    assert monitor.due_task(data, config, 5029) is None
    assert monitor.due_task(data, config, 5030) is not None


@pytest.mark.parametrize(
    "updates",
    [
        {"auto_activate": False},
        {"activation_cwd": ""},
        {"activation_cwd": "missing-folder"},
        {"activation_bucket": "missing-quota"},
    ],
)
def test_disabled_or_missing_target_never_executes(tmp_path, updates):
    assert (
        ActivationMonitor(tmp_path).due_task(
            snapshot(), settings(tmp_path, **updates), 1030
        )
        is None
    )


def test_chosen_quota_is_used_instead_of_another_groups_reset(tmp_path):
    data = snapshot(1000)
    data["buckets"]["other"] = snapshot(2000)["buckets"]["codex"]
    monitor = ActivationMonitor(tmp_path)
    config = settings(tmp_path, activation_bucket="other")
    assert monitor.due_task(data, config, 1030) is None
    assert monitor.due_task(data, config, 2030) is not None


def test_manual_first_activation_then_follows_only_new_records(tmp_path):
    config = settings(tmp_path, activation_start_at=1500.0)
    monitor = ActivationMonitor(tmp_path)
    assert monitor.due_task({}, config, 1529) is None
    finish(monitor, monitor.due_task({}, config, 1530), 1530)
    assert monitor.due_task(snapshot(1000), config, 1540) is None
    assert monitor.due_task(snapshot(2000), config, 2029) is None
    task = monitor.due_task(snapshot(2000), config, 2030)
    assert task is not None and task.scheduled_at == 2000
    finish(monitor, task, 2030)
    assert monitor.due_task(snapshot(2000), config, 3000) is None


def test_no_new_activation_while_one_is_running(tmp_path):
    config = settings(tmp_path)
    monitor = ActivationMonitor(tmp_path)
    task = monitor.due_task(snapshot(), config, 1030)
    monitor.start(task, tmp_path / "run.log", 1030)
    assert monitor.due_task(snapshot(2000), config, 2030) is None
    monitor.complete(task, {"code": 0}, 2040)
    assert monitor.due_task(snapshot(2000), config, 2041) is not None


def test_failed_persistence_prevents_start_without_losing_cycle(tmp_path, monkeypatch):
    config = settings(tmp_path)
    monitor = ActivationMonitor(tmp_path)
    task = monitor.due_task(snapshot(), config, 1030)
    monkeypatch.setattr(
        "codex_sentinel.activation_monitor.write_json",
        lambda *args: (_ for _ in ()).throw(OSError("disk full")),
    )
    with pytest.raises(OSError, match="disk full"):
        monitor.start(task, tmp_path / "run.log", 1030)
    assert monitor.target is None and task.status == "pending"
    assert monitor.due_task(snapshot(), config, 1030) is not None


def test_configuration_rejects_two_automatic_modes(tmp_path):
    manager = ConfigManager(tmp_path)
    manager.load()
    with pytest.raises(ValueError, match="either"):
        manager.save({"auto_activate": True, "auto_resume": True})


def test_initial_activation_without_quota_cannot_replay_old_records_when_group_appears(
    tmp_path,
):
    config = settings(tmp_path, activation_bucket="", activation_start_at=1500.0)
    monitor = ActivationMonitor(tmp_path)
    finish(monitor, monitor.due_task({}, config, 1530), 1530)
    config["activation_bucket"] = "codex"
    assert monitor.due_task(snapshot(1000), config, 1540) is None
    assert monitor.due_task(snapshot(2000), config, 2030) is not None


def test_changing_model_does_not_replay_the_same_quota_window(tmp_path):
    monitor = ActivationMonitor(tmp_path)
    config = settings(tmp_path)
    finish(monitor, monitor.due_task(snapshot(), config, 1030), 1030)
    config["activation_model"] = "another-model"
    assert monitor.due_task(snapshot(), config, 1100) is None
    assert monitor.due_task(snapshot(2000), config, 2030).model == "another-model"
