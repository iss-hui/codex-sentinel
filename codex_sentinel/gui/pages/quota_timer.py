import time
from pathlib import Path

from PySide6.QtCore import QDateTime, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from codex_sentinel.gui.common import populate_models, populate_sessions, time_text, tr


class QuotaTimerPage(QWidget):
    task_requested = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.snapshot = {}
        self.editing_id = None
        layout = QVBoxLayout(self)
        note = QLabel(
            tr(
                "在指定时间发送一条消息，或执行预订任务。五小时窗口由服务器决定；已运行的窗口不能被提前重置。",
                "Send a message or start a task at a chosen time. The server determines quota windows; an active window cannot be reset early.",
            )
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.txt_name = QLineEdit()
        form.addRow(tr("预约名称", "Schedule name"), self.txt_name)
        self.cmb_kind = QComboBox()
        self.cmb_kind.addItem(
            tr(
                "轻量消息（尝试启动窗口）",
                "Lightweight message (attempt to start window)",
            ),
            "kick",
        )
        self.cmb_kind.addItem(tr("执行预订任务", "Run a planned task"), "task")
        form.addRow(tr("用途", "Purpose"), self.cmb_kind)
        self.cmb_session = QComboBox()
        self.cmb_session.addItem(tr("新建对话", "New conversation"), "")
        self.cmb_session.currentIndexChanged.connect(self._session_changed)
        form.addRow(tr("对话", "Conversation"), self.cmb_session)
        self.cmb_model = QComboBox()
        self.cmb_model.setEditable(True)
        form.addRow(
            tr("模型（留空使用默认）", "Model (blank = default)"), self.cmb_model
        )
        row = QHBoxLayout()
        self.txt_cwd = QLineEdit(str(Path.cwd()))
        browse = QPushButton(tr("浏览…", "Browse…"))
        browse.clicked.connect(self._browse)
        row.addWidget(self.txt_cwd)
        row.addWidget(browse)
        form.addRow(tr("工作目录", "Working directory"), row)
        self.txt_prompt = QTextEdit()
        self.txt_prompt.setPlainText(
            tr(
                "请只回复：已启动。不要调用工具或修改文件。",
                "Reply only: Started. Do not use tools or modify files.",
            )
        )
        self.txt_prompt.setMaximumHeight(100)
        form.addRow(tr("发送语句 / 任务", "Message / task"), self.txt_prompt)
        self.chk_write = QCheckBox(
            tr("允许任务修改文件并使用自动审批", "Allow workspace edits and automatic approval reviews")
        )
        form.addRow(self.chk_write)
        self.cmb_schedule = QComboBox()
        self.cmb_schedule.addItem(
            tr("尽快执行（含缓冲）", "As soon as possible (with buffer)"), "now"
        )
        self.cmb_schedule.addItem(tr("指定日期时间", "Choose date and time"), "timed")
        self.cmb_schedule.addItem(
            tr("下一个本地记录的五小时重置点", "Next locally recorded five-hour reset"),
            "next",
        )
        self.cmb_schedule.currentIndexChanged.connect(
            lambda: self.date_edit.setEnabled(
                self.cmb_schedule.currentData() == "timed"
            )
        )
        form.addRow(tr("执行时机", "When"), self.cmb_schedule)
        self.date_edit = QDateTimeEdit(QDateTime.currentDateTime().addSecs(60))
        self.date_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setEnabled(False)
        form.addRow(
            tr("开始时间（系统时区）", "Start time (system time zone)"), self.date_edit
        )
        self.use_time = QDateTimeEdit(QDateTime.currentDateTime().addSecs(5 * 3600))
        self.use_time.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.use_time.setCalendarPopup(True)
        form.addRow(tr("计划开始使用时间", "Planned work start"), self.use_time)
        row = QHBoxLayout()
        for hours, remaining in ((2, 3), (3, 2)):
            button = QPushButton(
                tr(
                    f"提前{hours}小时发送（预计剩{remaining}小时）",
                    f"Send {hours}h earlier (~{remaining}h remaining)",
                )
            )
            button.clicked.connect(lambda checked=False, h=hours: self._prefill(h))
            row.addWidget(button)
        form.addRow(row)
        layout.addLayout(form)
        self.lbl_summary = QLabel()
        self.lbl_summary.setWordWrap(True)
        layout.addWidget(self.lbl_summary)
        row = QHBoxLayout()
        self.btn_schedule = QPushButton(tr("保存到执行队列", "Save to execution queue"))
        self.btn_schedule.clicked.connect(self.submit)
        reset = QPushButton(tr("新建预约", "New schedule"))
        reset.clicked.connect(self.reset_form)
        row.addWidget(self.btn_schedule)
        row.addWidget(reset)
        layout.addLayout(row)
        layout.addStretch()

    def _browse(self):
        directory = QFileDialog.getExistingDirectory(
            self, tr("工作目录", "Working directory"), self.txt_cwd.text()
        )
        if directory:
            self.txt_cwd.setText(directory)

    def _prefill(self, hours):
        self.cmb_schedule.setCurrentIndex(1)
        self.date_edit.setDateTime(self.use_time.dateTime().addSecs(-hours * 3600))

    def _session_changed(self):
        for s in self.snapshot.get("sessions", []):
            if s["session_id"] == self.cmb_session.currentData():
                self.txt_cwd.setText(s["cwd"])
                self.cmb_model.setCurrentText(s["model"])
                break

    def on_snapshot(self, snapshot):
        self.snapshot = snapshot
        populate_sessions(self.cmb_session, snapshot["sessions"])
        populate_models(self.cmb_model, snapshot["models"])

    def submit(self):
        now = time.time()
        mode = self.cmb_schedule.currentData()
        at = now
        if mode == "timed":
            at = self.date_edit.dateTime().toSecsSinceEpoch()
            if at <= now:
                QMessageBox.warning(
                    self,
                    tr("预约时间", "Schedule time"),
                    tr("请选择未来的日期时间。", "Choose a future date and time."),
                )
                return
        elif mode == "next":
            buckets = self.snapshot.get("buckets", {})
            session = next(
                (s for s in self.snapshot.get("sessions", [])
                 if s["session_id"] == self.cmb_session.currentData()),
                {},
            )
            key = session.get("limits", {}).get("limit_id")
            limits = (
                [buckets[key]]
                if key in buckets
                and self.cmb_model.currentText().strip() == session.get("model")
                else buckets.values()
            )
            resets = [
                w["resets_at"]
                for b in limits
                for w in (b.get("primary"), b.get("secondary"))
                if isinstance(w, dict)
                and w.get("window_minutes") == 300
                and (w.get("resets_at") or 0) > now
            ]
            if not resets:
                QMessageBox.warning(
                    self,
                    tr("无重置时间", "No reset time"),
                    tr(
                        "没有有效的五小时重置记录，请手动指定时间。",
                        "No valid five-hour reset record. Choose a time manually.",
                    ),
                )
                return
            at = min(resets)
        self.task_requested.emit(
            dict(
                id=self.editing_id,
                name=self.txt_name.text(),
                prompt=self.txt_prompt.toPlainText(),
                cwd=self.txt_cwd.text(),
                model=self.cmb_model.currentText().strip(),
                session_id=self.cmb_session.currentData() or "",
                scheduled_at=at,
                kind=self.cmb_kind.currentData(),
                sandbox="workspace-write"
                if self.chk_write.isChecked()
                else "read-only",
            )
        )

    def edit_task(self, task):
        self.editing_id = task.id
        self.txt_name.setText(task.name)
        self.txt_prompt.setPlainText(task.prompt)
        self.cmb_session.setCurrentIndex(
            max(0, self.cmb_session.findData(task.session_id))
        )
        if task.session_id and self.cmb_session.findData(task.session_id) < 0:
            self.cmb_session.addItem(task.session_id, task.session_id)
            self.cmb_session.setCurrentIndex(self.cmb_session.count() - 1)
        self.txt_cwd.setText(task.cwd)
        self.cmb_model.setCurrentText(task.model)
        self.cmb_kind.setCurrentIndex(max(0, self.cmb_kind.findData(task.kind)))
        self.cmb_schedule.setCurrentIndex(1)
        self.date_edit.setDateTime(
            QDateTime.fromSecsSinceEpoch(int(task.scheduled_at or time.time() + 60))
        )
        self.chk_write.setChecked(task.sandbox == "workspace-write")
        self.lbl_summary.setText(tr("正在编辑：", "Editing: ") + task.name)

    def reset_form(self):
        self.editing_id = None
        self.txt_name.clear()
        self.lbl_summary.clear()
        self.cmb_schedule.setCurrentIndex(1)
        self.date_edit.setDateTime(QDateTime.currentDateTime().addSecs(60))

    def saved(self, task):
        self.editing_id = None
        due = (
            task.scheduled_at + task.buffer_seconds
            if task.scheduled_at is not None else None
        )
        self.lbl_summary.setText(
            tr(
                "已保存；最早执行时间（含缓冲）：",
                "Saved; earliest execution (including buffer): ",
            )
            + time_text(due)
        )
