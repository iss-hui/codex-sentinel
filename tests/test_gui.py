import time

import pytest
from PySide6.QtCore import QDateTime
from PySide6.QtWidgets import QApplication, QPushButton

from codex_sentinel.config import ConfigManager
from codex_sentinel.gui.main_window import MainWindow
from codex_sentinel.i18n import set_lang
from codex_sentinel.quota_scheduler import QuotaScheduler


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, tmp_path):
    manager = ConfigManager(tmp_path / "app")
    manager.load()
    set_lang("zh")
    window = MainWindow(manager=manager, start_workers=False)
    yield window
    if window.executor:
        window.executor.stop()
        window.executor.wait(5000)
        app.processEvents()
    window.request_quit()
    app.processEvents()


def snapshot(tmp_path):
    now = time.time()
    return {
        "scanned_at": now,
        "buckets": {
            "codex": {
                "observed_at": now,
                "primary": {
                    "window_minutes": 300,
                    "used_percent": 42,
                    "resets_at": now + 3600,
                },
            }
        },
        "sessions": [
            {
                "session_id": "test-session",
                "title": "测试对话",
                "model": "cached-model",
                "cwd": str(tmp_path),
                "task_status": "completed",
                "total_turns": 2,
                "updated_at": now,
                "limits": {},
            }
        ],
        "models": [{"slug": "cached-model"}],
        "warnings": [],
    }


def test_pages_settings_and_schedule_persist(window, tmp_path):
    window._on_snapshot(snapshot(tmp_path))
    assert window.stacked.count() == 5
    assert window.page_sessions.table.rowCount() == 1
    assert window.page_quota.cmb_model.findText("cached-model") >= 0
    window.page_dashboard.chk_auto_resume.setChecked(True)
    assert ConfigManager(window.manager.config_dir).load()["auto_resume"] is True
    window.page_dashboard.spin_buffer.setValue(60)
    window.page_dashboard.txt_prompt.setPlainText("接着完成任务")
    window.page_dashboard.btn_save.click()
    assert ConfigManager(window.manager.config_dir).load()["buffer_seconds"] == 60
    page = window.page_quota
    page.cmb_session.setCurrentIndex(page.cmb_session.findData("test-session"))
    page.txt_prompt.setPlainText("test prompt")
    page.cmb_schedule.setCurrentIndex(1)
    page.date_edit.setDateTime(QDateTime.currentDateTime().addSecs(120))
    page.btn_schedule.click()
    task = window.scheduler.task_queue[0]
    assert task.session_id == "test-session"
    assert task.model == "cached-model"
    assert task.cwd == str(tmp_path)
    assert task.buffer_seconds == 60
    assert window.page_tasks.table.rowCount() == 1
    window.page_tasks.table.selectRow(0)
    delete = next(
        button for button in window.page_tasks.findChildren(QPushButton)
        if button.text() == "删除"
    )
    delete.click()
    assert window.scheduler.task_queue == []
    assert window.page_tasks.table.rowCount() == 0
    assert window.page_tasks.detail.toPlainText() == ""
    assert QuotaScheduler(window.manager.config_dir).task_queue == []


def test_recovery_is_independent_of_queue_and_always_writable(window, tmp_path, monkeypatch):
    window.dry_run = True
    now = time.time()
    data = snapshot(tmp_path)
    data["sessions"][0].update(task_status="rate_limited", limited_at=now - 100,
        limits={"limit_id": "codex", "primary": {"used_percent": 100, "resets_at": now - 40}})
    data["buckets"] = {}
    window._on_snapshot(data)
    window._save_settings({"auto_resume": True, "queue_enabled": False})
    manual = window.scheduler.add_task("manual", "hello", str(tmp_path), scheduled_at=now - 40)
    window._tick()
    assert window.scheduler.task_queue == [manual]
    assert manual.status == "pending" and manual.sandbox == "read-only"
    history = window.recovery.history_tasks()
    assert len(history) == 1 and history[0].status == "simulated"
    assert history[0].sandbox == "workspace-write"
    window._tick()
    assert len(window.recovery.history_tasks()) == 1
    assert "测试对话" in window.page_dashboard.lbl_recovery.text()


def test_recovery_priority_and_manual_permissions_are_separate(window, tmp_path):
    window.dry_run = True
    now = time.time()
    data = snapshot(tmp_path)
    data["sessions"][0].update(task_status="rate_limited", limited_at=now - 100,
        limits={"primary": {"used_percent": 100, "resets_at": now - 40}})
    data["buckets"] = {}
    window._on_snapshot(data)
    window._save_settings({"auto_resume": True})
    manual = window.scheduler.add_task("manual", "hello", str(tmp_path), scheduled_at=now - 40)
    window._tick()
    assert manual.status == "pending"
    assert window.recovery.target["status"] == "simulated"
    window._tick()
    assert manual.status == "simulated" and manual.sandbox == "read-only"


def test_disabling_recovery_does_not_pause_manual_queue(window, tmp_path):
    window.dry_run = True
    window._on_snapshot(snapshot(tmp_path))
    window._save_settings({"auto_resume": False})
    task = window.scheduler.add_task("manual", "hello", str(tmp_path), scheduled_at=time.time() - 40)
    window._tick()
    assert task.status == "simulated"
    assert window.settings["queue_enabled"]


def test_worker_recovers_latest_chat_without_adding_to_queue(app, window, tmp_path, monkeypatch):
    calls = []
    def execute(task, log_path, **kwargs):
        calls.append((task.session_id, task.sandbox))
        return {"code": 0, "error": "", "session_id": task.session_id}
    monkeypatch.setattr("codex_sentinel.gui.workers.execute_task", execute)
    now = time.time()
    data = snapshot(tmp_path)
    data["sessions"][0].update(task_status="rate_limited", limited_at=now - 100,
        limits={"primary": {"used_percent": 100, "resets_at": now - 40}})
    data["buckets"] = {}
    window._on_snapshot(data)
    window._save_settings({"auto_resume": True, "queue_enabled": False})
    window._tick()
    deadline = time.monotonic() + 5
    while window.executor is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert window.executor is None
    assert calls == [("test-session", "workspace-write")]
    assert window.scheduler.task_queue == []
    assert window.recovery.history_tasks()[0].status == "completed"
    window._on_snapshot(data)
    window._tick()
    assert len(calls) == 1


def test_recovery_worker_start_failure_does_not_remain_running(window, tmp_path, monkeypatch):
    now = time.time()
    data = snapshot(tmp_path)
    data["sessions"][0].update(task_status="rate_limited", limited_at=now - 100,
        limits={"primary": {"used_percent": 100, "resets_at": now - 40}})
    data["buckets"] = {}
    window._on_snapshot(data)
    window._save_settings({"auto_resume": True})
    def fail(*args, **kwargs):
        raise RuntimeError("could not create worker")
    monkeypatch.setattr(window, "executor_factory", fail)
    window._tick()
    assert window.executor is None
    assert window.recovery.target["status"] == "failed"
    assert not window.settings["auto_resume"]


def test_no_execution_without_fresh_snapshot(window, tmp_path, monkeypatch):
    task = window.scheduler.add_task(
        "test", "hello", str(tmp_path), scheduled_at=time.time() - 31
    )
    monkeypatch.setattr(
        window,
        "executor_factory",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("must not execute")),
    )
    window._tick()
    window.snapshot = {"scanned_at": time.time() - 1000}
    window._tick()
    assert task.status == "pending"


def test_worker_executes_once_and_shutdown(app, window, tmp_path, monkeypatch):
    calls = []

    def fake_execute(task, log_path, **kwargs):
        assert kwargs["take_over_desktop"] is True
        calls.append(task.prompt)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("mock execution\n", encoding="utf-8")
        return {"code": 0, "error": "", "session_id": "new-session"}

    monkeypatch.setattr("codex_sentinel.gui.workers.execute_task", fake_execute)
    window._on_snapshot(snapshot(tmp_path))
    task = window.scheduler.add_task(
        "run", "hello", str(tmp_path), scheduled_at=time.time() - 31
    )
    window._tick()
    deadline = time.monotonic() + 5
    while window.executor is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert window.executor is None
    assert task.status == "completed"
    window._on_snapshot(snapshot(tmp_path))
    window._tick()
    assert calls == ["hello"]
    window.request_quit()
    assert window._shutdown_complete


def test_failed_cleanup_pauses_queue_but_preserves_completed_turn(window, tmp_path):
    from types import SimpleNamespace

    task = window.scheduler.add_task("test", "hello", str(tmp_path))
    window.scheduler.update(task, status="running")
    window.executor = SimpleNamespace(task=task)
    window._execution_completed(
        {
            "code": 0,
            "error": "cleanup failed",
            "cleanup_ok": False,
            "session_id": "target",
        }
    )
    window.executor = None
    assert task.status == "completed"
    assert not window.settings["queue_enabled"]
    assert not ConfigManager(window.manager.config_dir).load()["queue_enabled"]
    assert "cleanup failed" in task.last_error


def test_gui_finishes_when_completed_cli_lingers(app, window, tmp_path, monkeypatch):
    import sys

    import psutil

    helper = tmp_path / "lingering_cli.py"
    pid_file = tmp_path / "cli.pid"
    helper.write_text(
        "import os,sys,time\nfrom pathlib import Path\nsys.stdin.read()\n"
        f"Path({str(pid_file)!r}).write_text(str(os.getpid()))\n"
        'print(\'{"type":"turn.completed"}\',flush=True)\ntime.sleep(60)\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "codex_sentinel.execution.build_command",
        lambda *args: [sys.executable, str(helper)],
    )
    # Avoid probing installed Codex binaries during this simulated run.
    window.settings["cli_path"] = sys.executable
    window._on_snapshot(snapshot(tmp_path))
    task = window.scheduler.add_task(
        "test", "hello", str(tmp_path), scheduled_at=time.time() - 31
    )
    window._tick()
    deadline = time.monotonic() + 6
    while window.executor is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert window.executor is None
    assert task.status == "completed"
    assert ConfigManager(window.manager.config_dir).load()["queue_enabled"]
    assert not psutil.pid_exists(int(pid_file.read_text()))


def test_dry_run_never_starts_cli(window, tmp_path, monkeypatch):
    window.dry_run = True
    window._on_snapshot(snapshot(tmp_path))
    task = window.scheduler.add_task(
        "test", "hello", str(tmp_path), scheduled_at=time.time() - 31
    )
    monkeypatch.setattr(
        window,
        "executor_factory",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("must not execute")),
    )
    window._tick()
    assert task.status == "simulated"


def test_readonly_monitor_can_start_and_stop(app, tmp_path):
    from codex_sentinel.gui.workers import MonitorWorker

    worker = MonitorWorker(str(tmp_path), poll_interval=1)
    results = []
    worker.snapshot_ready.connect(results.append)
    worker.start()
    deadline = time.monotonic() + 5
    while not results and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    worker.stop()
    assert worker.wait(3000)
    assert results and results[0]["sessions"] == []


def test_unavailable_data_source_prevents_execution(window, tmp_path, monkeypatch):
    window._on_snapshot({**snapshot(tmp_path), "available": False})
    task = window.scheduler.add_task(
        "test", "hello", str(tmp_path), scheduled_at=time.time() - 31
    )
    monkeypatch.setattr(
        window,
        "executor_factory",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("must not execute")),
    )
    window._tick()
    assert task.status == "pending"


def test_disappearing_selected_conversation_is_not_retargeted(window, tmp_path):
    page = window.page_quota
    page.on_snapshot(snapshot(tmp_path))
    page.cmb_session.setCurrentIndex(page.cmb_session.findData("test-session"))
    page.on_snapshot({**snapshot(tmp_path), "sessions": []})
    assert page.cmb_session.currentData() == "test-session"


def test_picker_groups_folders_but_selects_thread_ids(window, tmp_path):
    from PySide6.QtCore import Qt

    data = snapshot(tmp_path)
    data["sessions"][0].update(project_key="project-a", project_name="项目名称")
    data["sessions"].append(
        {**data["sessions"][0], "session_id": "second", "title": "另一对话"}
    )
    window._on_snapshot(data)
    combo = window.page_quota.cmb_session
    assert combo.itemText(1) == "项目名称"
    assert not combo.model().item(1).flags() & Qt.ItemFlag.ItemIsSelectable
    assert combo.itemText(2).strip() == "测试对话"
    assert combo.itemData(2) == "test-session"
    combo.setCurrentIndex(combo.findData("second"))
    window._on_snapshot(data)
    assert combo.currentData() == "second"
    assert "项目名称" in combo.toolTip()
    assert str(tmp_path) in combo.toolTip()
    assert window.page_quota.cmb_session.itemData(0) == ""


def test_long_log_keeps_target_and_actual_thread_ids_visible(window, tmp_path):
    import json

    window._on_snapshot(snapshot(tmp_path))
    task = window.scheduler.add_task(
        "手动恢复", "继续", str(tmp_path), session_id="test-session"
    )
    log = tmp_path / "long.log"
    log.write_text(
        json.dumps({"type": "thread.started", "thread_id": "test-session"})
        + "\n"
        + "x" * 30000
        + "\nOther project titles read by a tool\n",
        encoding="utf-8",
    )
    task.log_file = str(log)
    window._refresh_queue()
    page = window.page_tasks
    page.table.selectRow(0)
    detail = page.detail.toPlainText()
    assert "恢复 / 执行目标: 测试对话" in detail
    assert "目标会话 ID: test-session" in detail
    assert "实际启动会话 ID: test-session" in detail
    assert "Other project titles" in detail
    assert page.table.item(0, 3).text() == "测试对话"


def test_saving_language_keeps_current_ui_until_restart(window):
    from codex_sentinel.i18n import get_lang

    original_title = window.nav_buttons[0].text()
    window._save_settings({"language": "en"})
    assert window.manager.load()["language"] == "en"
    assert get_lang() == "zh"
    assert window.nav_buttons[0].text() == original_title
    assert window.page_dashboard.lbl_status.text() == "设置已保存"


@pytest.mark.parametrize("code, cleanup_ok", [(1, True), (0, False)])
def test_tray_keeps_execution_errors_after_poll(window, tmp_path, code, cleanup_ok):
    from types import SimpleNamespace

    from codex_sentinel.gui.tray_icon import SentinelTrayIcon

    window.tray = SentinelTrayIcon()
    window.settings["show_notifications"] = False
    window._on_snapshot(snapshot(tmp_path))
    task = window.scheduler.add_task("test", "hello", str(tmp_path))
    window.executor = SimpleNamespace(task=task)
    window._execution_completed({"code": code, "error": "failure", "cleanup_ok": cleanup_ok})
    window.executor = None
    window._tick()
    assert "错误" in window.tray.toolTip()


def test_tray_does_not_report_monitoring_with_stale_data(window, tmp_path):
    from codex_sentinel.gui.tray_icon import SentinelTrayIcon

    window.tray = SentinelTrayIcon()
    data = snapshot(tmp_path)
    data["scanned_at"] -= 1000
    window._on_snapshot(data)
    window._tick()
    assert "未知" in window.tray.toolTip()
    data["scanned_at"] = time.time()
    data["buckets"]["codex"]["primary"]["used_percent"] = 100
    window._tick()
    assert "限额冷却" in window.tray.toolTip()
    window._scan_error("unreadable data")
    window._tick()
    assert "未知" in window.tray.toolTip()


def test_secondary_window_returns_after_bucket_changes(window, tmp_path):
    data = snapshot(tmp_path)
    data["buckets"]["codex"]["secondary"] = None
    window._on_snapshot(data)
    page = window.page_dashboard
    assert page.window_bars[1].format() == "无"
    assert not page.window_bars[1].isEnabled()
    data["buckets"]["codex"]["secondary"] = {
        "window_minutes": 10080, "resets_at": time.time() + 86400, "used_percent": 50,
    }
    window._on_snapshot(data)
    assert page.window_bars[1].isEnabled()
    assert page.window_bars[1].value() == 50
