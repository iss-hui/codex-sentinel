import time
from pathlib import Path

from PySide6.QtCore import QDateTime, Signal
from PySide6.QtWidgets import (
    QBoxLayout,
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from codex_sentinel.gui.common import populate_models, populate_sessions, time_text, tr
from codex_sentinel.gui.ui import card, field, heading, label
from codex_sentinel.session_scanner import blocking_reset


class QuotaTimerPage(QWidget):
    task_requested = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.snapshot = {}
        self.editing_id = None
        self.buffer_seconds = 30
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)
        heading(
            layout,
            tr("窗口启动与预约", "Window planner"),
            tr(
                "在合适的时间发送消息，或继续你的计划任务。",
                "Send a message or start a planned task at the right time.",
            ),
        )
        self.columns = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.columns.setSpacing(16)
        content, content_layout = card(tr("01  任务内容", "01  Task content"))
        self.txt_name = QLineEdit()
        content_layout.addWidget(field(tr("预约名称", "Schedule name"), self.txt_name))
        self.cmb_kind = QComboBox()
        self.cmb_kind.addItem(
            tr("轻量消息（尝试启动窗口）", "Lightweight message (attempt to start window)"),
            "kick",
        )
        self.cmb_kind.addItem(tr("执行预订任务", "Run a planned task"), "task")
        content_layout.addWidget(field(tr("用途", "Purpose"), self.cmb_kind))
        self.cmb_session = QComboBox()
        self.cmb_session.addItem(tr("新建对话", "New conversation"), "")
        self.cmb_session.currentIndexChanged.connect(self._session_changed)
        self.cmb_model = QComboBox()
        self.cmb_model.setEditable(True)
        self.cmb_model.lineEdit().setPlaceholderText(
            tr("使用 Codex 默认模型", "Use Codex default")
        )
        for combo in (self.cmb_session, self.cmb_model):
            combo.setMinimumWidth(0)
            combo.setMinimumContentsLength(8)
            combo.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row = QHBoxLayout()
        row.addWidget(field(tr("对话", "Conversation"), self.cmb_session), 1)
        row.addWidget(
            field(tr("模型 · 可输入 ID", "Model · editable ID"), self.cmb_model), 1
        )
        content_layout.addLayout(row)
        row = QHBoxLayout()
        self.txt_cwd = QLineEdit(str(Path.cwd()))
        row.addWidget(self.txt_cwd, 1)
        browse = QPushButton(tr("浏览…", "Browse…"))
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        content_layout.addWidget(field(tr("工作目录", "Working directory"), row))
        self.txt_prompt = QTextEdit()
        self.txt_prompt.setPlainText(
            tr(
                "请只回复：已启动。不要调用工具或修改文件。",
                "Reply only: Started. Do not use tools or modify files.",
            )
        )
        self.txt_prompt.setMinimumHeight(84)
        self.txt_prompt.setMaximumHeight(110)
        content_layout.addWidget(
            field(tr("发送语句 / 任务", "Message / task"), self.txt_prompt)
        )
        self.chk_write = QCheckBox(
            tr(
                "允许任务修改文件并使用自动审批",
                "Allow workspace edits and automatic approval reviews",
            )
        )
        content_layout.addWidget(self.chk_write)
        content_layout.addWidget(
            label(
                tr(
                    "默认只读；权限由每条预约单独设置。",
                    "Read-only by default; permissions are per schedule.",
                ),
                "hint",
            )
        )
        content_layout.addStretch()
        self.columns.addWidget(content, 1)
        self.timing_card, timing_layout = card(tr("02  执行时间", "02  When to run"))
        self.timing_card.setMaximumWidth(320)
        self.cmb_schedule = QComboBox()
        self.cmb_schedule.addItem(
            tr("尽快执行（含缓冲）", "As soon as possible (with buffer)"), "now"
        )
        self.cmb_schedule.addItem(tr("指定日期时间", "Choose date and time"), "timed")
        self.cmb_schedule.addItem(
            tr("下一个本地五小时重置点", "Next local five-hour reset"), "next"
        )
        self.cmb_schedule.setMinimumContentsLength(10)
        self.cmb_schedule.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        timing_layout.addWidget(field(tr("执行时机", "When"), self.cmb_schedule))
        self.date_edit = QDateTimeEdit(QDateTime.currentDateTime().addSecs(60))
        self.date_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setEnabled(False)
        timing_layout.addWidget(
            field(
                tr("开始时间（系统时区）", "Start time (system time zone)"), self.date_edit
            )
        )
        self.use_time = QDateTimeEdit(QDateTime.currentDateTime().addSecs(5 * 3600))
        self.use_time.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.use_time.setCalendarPopup(True)
        timing_layout.addWidget(
            field(tr("计划开始使用时间", "Planned work start"), self.use_time)
        )
        row = QHBoxLayout()
        for hours, remaining in ((2, 3), (3, 2)):
            button = QPushButton(tr(f"提前{hours}小时发送", f"Send {hours}h earlier"))
            button.setToolTip(
                tr(
                    f"预计剩余约{remaining}小时；实际窗口由服务器决定。",
                    f"Approximately {remaining}h remaining; the server determines the window.",
                )
            )
            button.clicked.connect(lambda checked=False, h=hours: self._prefill(h))
            row.addWidget(button)
        timing_layout.addLayout(row)
        timing_layout.addWidget(
            label(
                tr(
                    "五小时窗口由服务器决定，不能提前重置。",
                    "The server determines quota windows; they cannot be reset early.",
                ),
                "hint",
            )
        )
        self.lbl_preview = label("", "section", True)
        timing_layout.addWidget(self.lbl_preview)
        timing_layout.addWidget(
            label(
                tr(
                    "预约与已知耗尽窗口取较晚值，再加缓冲；执行还需等待会话空闲。",
                    "Runs after the later of the schedule or exhausted-window reset, plus buffer, and waits for the session lock.",
                ),
                "hint",
            )
        )
        self.btn_schedule = QPushButton(tr("保存到执行队列", "Save to execution queue"))
        self.btn_schedule.setObjectName("primary")
        self.btn_schedule.clicked.connect(self.submit)
        timing_layout.addWidget(self.btn_schedule)
        reset = QPushButton(tr("新建预约", "New schedule"))
        reset.clicked.connect(self.reset_form)
        timing_layout.addWidget(reset)
        self.columns.addWidget(self.timing_card)
        layout.addLayout(self.columns)
        self.lbl_summary = label()
        layout.addWidget(self.lbl_summary)
        layout.addStretch()
        self.cmb_schedule.currentIndexChanged.connect(
            lambda: self.date_edit.setEnabled(self.cmb_schedule.currentData() == "timed")
        )
        self.cmb_schedule.currentIndexChanged.connect(self._update_preview)
        self.date_edit.dateTimeChanged.connect(self._update_preview)
        self.cmb_model.currentTextChanged.connect(self._update_preview)
        self.cmb_session.currentIndexChanged.connect(self._update_preview)
        self._update_preview()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        compact = self.width() < 760
        self.columns.setDirection(
            QBoxLayout.Direction.TopToBottom
            if compact
            else QBoxLayout.Direction.LeftToRight
        )
        self.timing_card.setMaximumWidth(16777215 if compact else 320)

    def set_buffer_seconds(self, value):
        self.buffer_seconds = value
        self._update_preview()

    def _update_preview(self, *args):
        now = time.time()
        buckets = self.snapshot.get("buckets", {})
        session = next(
            (
                s
                for s in self.snapshot.get("sessions", [])
                if s["session_id"] == self.cmb_session.currentData()
            ),
            {},
        )
        key = session.get("limits", {}).get("limit_id")
        limits = (
            [buckets[key]]
            if key in buckets
            and self.cmb_model.currentText().strip() == session.get("model")
            else list(buckets.values())
        )
        mode = self.cmb_schedule.currentData()
        at = self.date_edit.dateTime().toSecsSinceEpoch() if mode == "timed" else now
        if mode == "next":
            resets = [
                w["resets_at"]
                for b in limits
                for w in (b.get("primary"), b.get("secondary"))
                if isinstance(w, dict)
                and w.get("window_minutes") == 300
                and (w.get("resets_at") or 0) > now
            ]
            if not resets:
                self.lbl_preview.setText(
                    tr(
                        "等待有效的五小时重置记录",
                        "Waiting for a valid five-hour reset record",
                    )
                )
                return
            at = min(resets)
        block = max(
            (blocking_reset(b, now - self.buffer_seconds) for b in limits), default=0
        )
        due = max(at, block) + self.buffer_seconds
        try:
            display_time = time_text(due)
        except (OSError, OverflowError, ValueError):
            display_time = tr("时间不可用", "Time unavailable")
        self.lbl_preview.setText(
            tr("最早执行（含缓冲）", "Earliest run (with buffer)") + "\n" + display_time
        )

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
        self._update_preview()

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
