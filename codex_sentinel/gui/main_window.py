import time
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from codex_sentinel.config import ConfigManager
from codex_sentinel.gui.common import tr
from codex_sentinel.gui.pages.dashboard import DashboardPage
from codex_sentinel.gui.pages.quota_timer import QuotaTimerPage
from codex_sentinel.gui.pages.sessions import SessionsPage
from codex_sentinel.gui.pages.settings import SettingsPage
from codex_sentinel.gui.pages.task_queue import TaskQueuePage
from codex_sentinel.gui.workers import ExecutionWorker, MonitorWorker
from codex_sentinel.recovery_monitor import RecoveryMonitor
from codex_sentinel.quota_scheduler import QuotaScheduler


class MainWindow(QMainWindow):
    def __init__(self, parent=None, *, manager=None, start_workers=True, dry_run=False):
        super().__init__(parent)
        self.manager = manager or ConfigManager()
        self.settings = self.manager.load()
        self.scheduler = QuotaScheduler(self.manager.config_dir)
        self.recovery = RecoveryMonitor(self.manager.config_dir)
        self.recovery.migrate_legacy(self.scheduler)
        self.recovery_dialog = None
        self.snapshot = {}
        self.executor = None
        self._execution_error = False
        self.executor_factory = ExecutionWorker
        self.tray = None
        self._quitting = False
        self._shutdown_complete = False
        self._start_workers = start_workers
        self.dry_run = dry_run
        self.setWindowTitle("Codex Sentinel · " + tr("使用时间管理", "Usage planner"))
        self.resize(1160, 820)
        self.setMinimumSize(940, 700)
        self.monitor_worker = MonitorWorker(
            self.settings["sessions_dir"], self.settings["poll_interval"], self
        )
        self._setup_ui()
        self._connect_signals()
        self._load_settings()
        self._refresh_queue()
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)
        if start_workers:
            self.monitor_worker.start()
            self.timer.start()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        sidebar = QVBoxLayout()
        self.nav_buttons = []
        for index, title in enumerate(
            (
                tr("总览", "Overview"),
                tr("窗口启动与预约", "Window planner"),
                tr("执行队列", "Task queue"),
                tr("本地对话", "Local conversations"),
                tr("设置", "Settings"),
            )
        ):
            button = QPushButton(title)
            button.setCheckable(True)
            button.setMinimumWidth(150)
            button.clicked.connect(lambda checked=False, i=index: self.switch_page(i))
            sidebar.addWidget(button)
            self.nav_buttons.append(button)
        sidebar.addStretch()
        layout.addLayout(sidebar)
        self.stacked = QStackedWidget()
        self.page_dashboard = DashboardPage()
        self.page_quota = QuotaTimerPage()
        self.page_tasks = TaskQueuePage()
        self.page_sessions = SessionsPage()
        self.page_settings = SettingsPage()
        for page in (
            self.page_dashboard,
            self.page_quota,
            self.page_tasks,
            self.page_sessions,
            self.page_settings,
        ):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            scroll.setWidget(page)
            self.stacked.addWidget(scroll)
        layout.addWidget(self.stacked, 1)
        self.switch_page(0)

    def _connect_signals(self):
        self.monitor_worker.snapshot_ready.connect(self._on_snapshot)
        self.monitor_worker.error_occurred.connect(self._scan_error)
        self.page_dashboard.settings_changed.connect(self._save_settings)
        # Automatic recovery has its own switch, independent of the queue.
        self.page_dashboard.chk_auto_resume.toggled.connect(
            lambda value: self._save_settings({"auto_resume": value}, reload=False)
        )
        self.page_dashboard.resume_now_requested.connect(self.refresh_recovery)
        self.page_dashboard.stop_requested.connect(self.stop_execution)
        self.page_dashboard.history_requested.connect(self.show_recovery_history)
        self.page_settings.settings_changed.connect(self._save_settings)
        self.page_quota.task_requested.connect(self._save_task)
        self.page_tasks.add_requested.connect(
            lambda: (self.page_quota.reset_form(), self.switch_page(1))
        )
        self.page_tasks.edit_requested.connect(self._edit_task)
        self.page_tasks.delete_requested.connect(self._delete_task)
        self.page_tasks.retry_requested.connect(self._retry_task)
        self.page_tasks.move_requested.connect(self._move_task)
        self.page_tasks.stop_requested.connect(self.stop_execution)
        self.page_tasks.enabled_changed.connect(
            lambda value: self._save_settings({"queue_enabled": value})
        )

    def _load_settings(self):
        self.page_dashboard.chk_auto_resume.blockSignals(True)
        self.page_dashboard.load_settings(self.settings)
        self.page_dashboard.chk_auto_resume.blockSignals(False)
        self.page_settings.load_settings(self.settings)
        self.page_tasks.chk_auto.blockSignals(True)
        self.page_tasks.chk_auto.setChecked(self.settings["queue_enabled"])
        self.page_tasks.chk_auto.blockSignals(False)
        self._refresh_recovery()

    def _save_settings(self, updates, reload=True):
        try:
            self.manager.save(updates)
            self.settings = self.manager.load()
            self.monitor_worker.sessions_dir = self.settings["sessions_dir"]
            self.monitor_worker.poll_interval = self.settings["poll_interval"]
            if "sessions_dir" in updates:
                self.snapshot = {}  # Never execute from a previous data source.
            self.monitor_worker.refresh()
            if updates.get("auto_resume") is False and self.executor and self.executor.task.kind == "auto_resume":
                self.executor.stop()
            if reload:
                self._load_settings()
            self.page_dashboard.lbl_status.setText(tr("设置已保存", "Settings saved"))
        except Exception as exc:
            self._error(str(exc))

    def _on_snapshot(self, snapshot):
        if self._quitting:
            return
        self.snapshot = snapshot
        self.page_dashboard.on_snapshot(snapshot)
        self.page_quota.on_snapshot(snapshot)
        self.page_sessions.on_scan_completed(snapshot["sessions"])
        self.page_tasks.set_sessions(snapshot["sessions"])
        message = " | ".join(snapshot["warnings"])
        self.statusBar().showMessage(
            message or tr("本地读取 · 无网络轮询", "Local reads · no network polling")
        )

    def _scan_error(self, message):
        self.snapshot = {}
        self.statusBar().showMessage(
            tr("扫描失败，自动执行暂停：", "Scan failed; execution paused: ") + message
        )

    def _save_task(self, data):
        data = data.copy()
        task_id = data.pop("id", None)
        try:
            if task_id:
                task = self.scheduler.get(task_id)
                if task.status == "running":
                    raise ValueError(tr("运行中不能编辑", "Cannot edit a running task"))
                if not data["prompt"].strip() or not Path(data["cwd"]).is_dir():
                    raise ValueError(
                        tr(
                            "请填写语句和有效工作目录",
                            "Enter a prompt and valid directory",
                        )
                    )
                self.scheduler.update(
                    task,
                    **data,
                    status="pending",
                    deferred_until=0,
                    completed_at=None,
                    buffer_seconds=self.settings["buffer_seconds"],
                    last_error="",
                )
            else:
                task = self.scheduler.add_task(
                    **data, buffer_seconds=self.settings["buffer_seconds"]
                )
            self.page_quota.saved(task)
            self._refresh_queue()
        except Exception as exc:
            self._error(str(exc))

    def refresh_recovery(self):
        self.monitor_worker.refresh()

    def toggle_recovery(self):
        self._save_settings({"auto_resume": not self.settings["auto_resume"]})

    def show_recovery_history(self):
        if self.recovery_dialog is None:
            self.recovery_dialog = QDialog(self)
            self.recovery_dialog.setWindowTitle(tr("自动恢复记录", "Automatic recovery history"))
            self.recovery_dialog.resize(1000, 650)
            layout = QVBoxLayout(self.recovery_dialog)
            self.recovery_history = TaskQueuePage(read_only=True)
            layout.addWidget(self.recovery_history)
        self._refresh_recovery()
        self.recovery_dialog.show()
        self.recovery_dialog.raise_()

    def _refresh_recovery(self):
        self.monitor_worker.recovery_session_id = self.recovery.target["session_id"] if self.recovery.target else ""
        self.page_dashboard.render_recovery(self.recovery.target, self.settings)
        if self.recovery_dialog is not None:
            tasks = self.recovery.history_tasks()
            if self.executor and self.executor.task.kind == "auto_resume" and self.executor.task.status == "running":
                tasks.append(self.executor.task)
            self.recovery_history.refresh_table(tasks)

    def _edit_task(self, task_id):
        task = self.scheduler.get(task_id)
        if task.status == "running":
            return
        self.page_quota.edit_task(task)
        self.switch_page(1)

    def _delete_task(self, task_id):
        try:
            self.scheduler.remove_task(task_id)
            self._refresh_queue()
        except Exception as exc:
            self._error(str(exc))

    def _retry_task(self, task_id):
        try:
            self.scheduler.retry(task_id)
            self._refresh_queue()
        except Exception as exc:
            self._error(str(exc))

    def _move_task(self, task_id, delta):
        ids = [task.id for task in self.scheduler.task_queue]
        index = ids.index(task_id)
        target = index + delta
        if 0 <= target < len(ids):
            ids[index], ids[target] = ids[target], ids[index]
            try:
                self.scheduler.reorder_tasks(ids)
                self._refresh_queue()
            except Exception as exc:
                self._error(str(exc))

    def toggle_pause(self):
        self._save_settings({"queue_enabled": not self.settings["queue_enabled"]})

    def _tick(self):
        self.page_dashboard.render_limits()
        if self._quitting:
            return
        now = time.time()
        if self.tray and self.executor is None:
            self._update_tray_state(now)
        if (not self.snapshot or not self.snapshot.get("available", True)
                or now - self.snapshot.get("scanned_at", 0) > max(30, self.settings["poll_interval"] * 3)):
            self._refresh_recovery()
            return
        try:
            self.recovery.observe(self.snapshot, now)
            self._refresh_recovery()
            if self.executor is not None:
                return
            # Recovery has its own switch and no missed-schedule grace period.
            task = self.recovery.due_task(self.settings, now)
            task = task or self.scheduler.due_task(self.snapshot, self.settings, now)
            if task:
                try:
                    self._dispatch(task, now)
                except Exception as exc:
                    if self.executor is not None and not self.executor.isRunning():
                        self.executor.deleteLater()
                        self.executor = None
                    if self.executor is None and task.status == "running":
                        if task.kind == "auto_resume" and self.recovery.target["status"] == "running":
                            self.recovery.complete(task, {"code": 1, "error": str(exc)}, now)
                        elif task.kind != "auto_resume":
                            self.scheduler.update(task, status="failed", completed_at=now, last_error=str(exc))
                    raise
            self._refresh_queue()
            self._refresh_recovery()
        except Exception as exc:
            # Never execute if recording the run or its completion failed.
            self._execution_error = True
            self.settings.update(queue_enabled=False, auto_resume=False)
            self._load_settings()
            self.statusBar().showMessage(tr("执行已暂停：", "Execution paused: ") + str(exc))

    def _dispatch(self, task, now):
        automatic = task.kind == "auto_resume"
        log_path = self.manager.config_dir / "logs" / f"{task.id}-{int(now)}.log"
        if automatic:
            self.recovery.start(task, log_path, now)
        else:
            self.scheduler.update(task, status="running", started_at=now,
                                  log_file=str(log_path), last_error="")
        if self.dry_run:
            message = tr("模拟完成：没有调用 Codex", "Dry run: Codex was not invoked")
            if automatic:
                self.recovery.complete(task, {"code": 0, "error": message, "simulated": True}, now)
            else:
                self.scheduler.update(task, status="simulated", completed_at=now, last_error=message)
            return
        worker = self.executor_factory(task, log_path, binary=self.settings["cli_path"],
                                       parent=self, take_over_desktop=self.settings["take_over_desktop"])
        self.executor = worker
        self._execution_error = False
        worker.completed.connect(self._execution_completed)
        worker.output_line.connect(lambda _: self._refresh_recovery() if automatic else self.page_tasks.show_detail())
        worker.progress.connect(self._execution_progress)
        worker.finished.connect(self._execution_finished)
        worker.start()
        self.page_dashboard.lbl_status.setText(tr("正在执行：", "Running: ") + task.name)
        if self.tray:
            self.tray.set_state("resuming")

    def _update_tray_state(self, now):
        if self._execution_error:
            state = "error"
        elif (
            not self.snapshot
            or not self.snapshot.get("available", True)
            or now - self.snapshot.get("scanned_at", 0)
            > max(30, self.settings["poll_interval"] * 3)
        ):
            state = "unknown"
        else:
            limited = any(
                isinstance(w, dict)
                and (w.get("used_percent") or 0) >= 100
                and (w.get("resets_at") or 0) > now
                for bucket in self.snapshot.get("buckets", {}).values()
                for w in (bucket.get("primary"), bucket.get("secondary"))
            )
            state = "limited" if limited else "normal"
        self.tray.set_state(state)

    def _execution_progress(self, phase):
        labels = {
            "closing_desktop": ("正在关闭占用的 Codex 桌面", "Closing Codex desktop"),
            "waiting_for_lock": ("正在等待会话锁释放", "Waiting for the writer lock"),
            "running": ("正在执行任务", "Running task"),
            "cleanup": (
                "正在清理执行进程并释放会话",
                "Cleaning up processes and releasing the conversation",
            ),
            "reopening_desktop": ("正在重新打开 Codex 桌面", "Reopening Codex desktop"),
        }
        if self.executor:
            message = tr(*labels.get(phase, (phase, phase)))
            self.page_dashboard.lbl_status.setText(message)
            self.statusBar().showMessage(message)

    def _execution_completed(self, result):
        task = self.executor.task
        code = result["code"]
        self._execution_error = (
            code not in (0, 75)
            or not result.get("cleanup_ok", True)
            or (code == 0 and bool(result.get("error")))
        )
        try:
            if not result.get("cleanup_ok", True):
                self.manager.save({"queue_enabled": False, "auto_resume": False})
                self.settings.update(queue_enabled=False, auto_resume=False)
                self._load_settings()
            if task.kind == "auto_resume":
                self.recovery.complete(task, result, time.time())
            elif code == 75:
                self.scheduler.update(
                    task,
                    status="waiting",
                    deferred_until=time.time() + 5,
                    last_error=result["error"],
                )
            else:
                status = (
                    "completed"
                    if code == 0
                    else "interrupted"
                    if code == 130
                    else "failed"
                )
                self.scheduler.update(
                    task,
                    status=status,
                    completed_at=time.time(),
                    last_error=result["error"]
                    or ("" if code == 0 else f"Exit code {code}"),
                    session_id=result.get("session_id") or task.session_id,
                )
            message = (
                tr("执行完成：", "Completed: ")
                if code == 0
                else tr("执行未完成：", "Not completed: ")
            ) + task.name
            self.page_dashboard.lbl_status.setText(message)
            if self.tray and self.settings["show_notifications"] and code != 75:
                self.tray.show_notification("Codex Sentinel", message)
            if self.tray:
                self._update_tray_state(time.time())
            if self.settings["play_sound"] and code != 75:
                QApplication.beep()
            self._refresh_queue()
            self._refresh_recovery()
            self.monitor_worker.refresh()
        except Exception as exc:
            self._execution_error = True
            self.settings.update(queue_enabled=False, auto_resume=False)
            self.statusBar().showMessage(str(exc))

    def _execution_finished(self):
        worker = self.executor
        if worker:
            # A worker must never leave a running record behind, even if an
            # unexpected exception prevented its completion result.
            if worker.task.status == "running":
                self._execution_completed(
                    {
                        "code": 1,
                        "error": tr(
                            "执行器已退出，但未收到完成结果；队列已暂停，请检查日志。",
                            "Worker exited without a result; queue paused. Inspect the log.",
                        ),
                        "session_id": worker.task.session_id,
                        "cleanup_ok": False,
                    }
                )
            worker.deleteLater()
        self.executor = None
        # Refresh before any further scheduling; a turn may have consumed the last quota.
        self.snapshot = {}
        self.monitor_worker.refresh()
        if self._quitting:
            QTimer.singleShot(0, self.request_quit)

    def _refresh_queue(self):
        self.page_tasks.refresh_table(self.scheduler.task_queue)

    def stop_execution(self):
        if self.executor:
            self.executor.stop()

    def switch_page(self, index):
        self.stacked.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)

    def _error(self, message):
        QMessageBox.warning(self, "Codex Sentinel", message)

    def request_quit(self):
        self._quitting = True
        self.timer.stop()
        self.monitor_worker.stop()
        if self.executor:
            self.executor.stop()
            self.statusBar().showMessage(
                tr("正在停止当前执行…", "Stopping current execution…")
            )
            return
        if self.monitor_worker.isRunning():
            QTimer.singleShot(100, self.request_quit)
            return
        self._shutdown_complete = True
        if self.tray:
            self.tray.hide()
        self.close()
        QApplication.instance().quit()

    def closeEvent(self, event):
        if self._shutdown_complete:
            event.accept()
        elif (
            not self._quitting
            and self.settings["minimize_to_tray"]
            and self.tray
            and QSystemTrayIcon.isSystemTrayAvailable()
        ):
            self.hide()
            event.ignore()
        else:
            event.ignore()
            self.request_quit()
