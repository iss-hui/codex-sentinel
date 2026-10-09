import time
from pathlib import Path

from PySide6.QtCore import QDateTime, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from codex_sentinel.gui.common import populate_models, status_text, time_text, tr
from codex_sentinel.i18n import t


def _label(text="", role="muted", selectable=False):
    label = QLabel(text)
    label.setObjectName(role)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
    if role == "pill":
        label.setWordWrap(False)
    if selectable:
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def _card():
    card = QFrame()
    card.setObjectName("overviewCard")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(12)
    return card, layout


def _duration(due):
    if due is None:
        return "—"
    seconds = max(0, int(due - time.time()))
    return f"{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}"


class DashboardPage(QWidget):
    resume_now_requested = Signal()
    stop_requested = Signal()
    history_requested = Signal()
    settings_changed = Signal(dict)
    activation_requested = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.snapshot = {}
        self._preferred_activation_bucket = ""
        self.setObjectName("dashboard")
        self.setStyleSheet("""
            QWidget#dashboard { background: #1e1e2e; }
            QFrame#overviewCard { background: #262736; border: 1px solid #3b3d51; border-radius: 14px; }
            QLabel { background: transparent; }
            QLabel#heading { font-size: 25px; font-weight: 700; color: #f1f3fa; }
            QLabel#section { font-size: 14px; font-weight: 600; color: #eff1f8; }
            QLabel#target { font-size: 21px; font-weight: 600; color: #f1f3fa; }
            QLabel#muted { color: #9fa6be; }
            QLabel#path { color: #aab6d0; font-family: 'Consolas', monospace; font-size: 12px; }
            QLabel#activationStatus { color: #8de0ce; font-size: 21px; font-weight: 600; }
            QLabel#clock { color: #8de0ce; font-size: 30px; font-weight: 600; }
            QLabel#pill { color: #8de0ce; background: #2c4445; padding: 6px 10px; border-radius: 8px; }
            QPushButton#mode { text-align: left; padding: 13px 18px; font-size: 13px; border-radius: 10px; }
            QPushButton#mode:checked { background: #284542; border: 1px solid #69c9b6; color: #a0eddb; }
            QPushButton#primary { background: #79d6c1; border-color: #79d6c1; color: #172e2b; font-weight: 600; }
            QPushButton#primary:hover { background: #9ae7d6; }
            QPushButton#primary:disabled { background: #333b43; border-color: #45475a; color: #8c98a5; }
            QProgressBar { min-height: 7px; max-height: 7px; }
            QProgressBar::chunk { background: #69bdaa; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(14)
        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(4)
        titles.addWidget(_label(tr("自动化总览", "Automation overview"), "heading"))
        titles.addWidget(
            _label(
                tr(
                    "把限额到期后的下一步，提前安排好。",
                    "Plan what happens when your quota becomes available.",
                )
            )
        )
        header.addLayout(titles, 1)
        self.lbl_monitor = _label(tr("本地监测", "Local monitoring"), "pill")
        header.addWidget(self.lbl_monitor, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(header)

        modes = QHBoxLayout()
        self.btn_recovery_mode = QPushButton(
            tr(
                "01   恢复最新限额中断\n继续原来的对话与任务",
                "01   Resume latest interruption\nContinue the original conversation",
            )
        )
        self.btn_activation_mode = QPushButton(
            tr(
                "02   仅激活五小时窗口\n窗口到期后，新建对话发轻量消息",
                "02   Activate a five-hour window\nFollow resets with a fresh conversation",
            )
        )
        for index, button in enumerate(
            (self.btn_recovery_mode, self.btn_activation_mode)
        ):
            button.setObjectName("mode")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, i=index: self.set_mode(i))
            modes.addWidget(button, 1)
        layout.addLayout(modes)
        self.mode_stack = QStackedWidget()
        self.mode_stack.addWidget(self._recovery_card())
        self.mode_stack.addWidget(self._activation_card())
        # Hidden mode contents must not force the visible card to their height.
        self.mode_stack.currentChanged.connect(self._fit_mode)
        layout.addWidget(self.mode_stack)
        layout.addWidget(self._quota_card())
        self.lbl_status = _label()
        layout.addWidget(self.lbl_status)
        layout.addStretch()
        self.set_mode(0)

    def _fit_mode(self, index):
        for i in range(self.mode_stack.count()):
            self.mode_stack.widget(i).setSizePolicy(
                QSizePolicy.Policy.Preferred,
                QSizePolicy.Policy.Preferred
                if i == index
                else QSizePolicy.Policy.Ignored,
            )
        self.mode_stack.adjustSize()

    def set_mode(self, index):
        self.mode_stack.setCurrentIndex(index)
        self.btn_recovery_mode.setChecked(index == 0)
        self.btn_activation_mode.setChecked(index == 1)
        self._fit_mode(index)

    def _recovery_card(self):
        card, layout = _card()
        row = QHBoxLayout()
        row.addWidget(
            _label(tr("最新恢复目标", "Latest recovery target"), "section"), 1
        )
        self.chk_auto_resume = QCheckBox(tr("自动恢复", "Automatic recovery"))
        row.addWidget(self.chk_auto_resume)
        layout.addLayout(row)
        self.lbl_recovery = _label(
            tr("等待新的限额中断聊天", "Waiting for a new quota interruption"),
            "target",
            True,
        )
        layout.addWidget(self.lbl_recovery)
        self.lbl_recovery_cwd = _label(tr("目录：—", "Directory: —"), "path", True)
        layout.addWidget(self.lbl_recovery_cwd)
        row = QHBoxLayout()
        self.lbl_recovery_state = _label("", "pill")
        row.addWidget(self.lbl_recovery_state)
        hint = _label(
            tr("实时跟随最新中断 · 不回退到旧对话", "Follows the latest interruption")
        )
        hint.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(hint, 1)
        layout.addLayout(row)
        row = QHBoxLayout()
        clock = QVBoxLayout()
        self.lbl_recovery_countdown = _label("—", "clock")
        clock.addWidget(self.lbl_recovery_countdown)
        clock.addWidget(
            _label(
                tr("距离最早恢复（含缓冲）", "Until earliest recovery (with buffer)")
            )
        )
        row.addLayout(clock, 1)
        self.lbl_recovery_time = _label()
        row.addWidget(self.lbl_recovery_time, 1)
        layout.addLayout(row)

        self.btn_details = QPushButton(tr("恢复设置", "Recovery settings"))
        self.btn_details.setCheckable(True)
        self.recovery_details = QWidget()
        form = QFormLayout(self.recovery_details)
        form.setContentsMargins(0, 0, 0, 0)
        self.spin_buffer = QSpinBox()
        self.spin_buffer.setRange(0, 600)
        self.spin_buffer.setSuffix(tr(" 秒", " s"))
        row = QHBoxLayout()
        row.addWidget(self.spin_buffer)
        for value in (30, 60):
            button = QPushButton(f"{value}s")
            button.clicked.connect(
                lambda checked=False, value=value: self.spin_buffer.setValue(value)
            )
            row.addWidget(button)
        form.addRow(tr("到期后缓冲", "Buffer after reset"), row)
        self.txt_prompt = QTextEdit()
        self.txt_prompt.setMaximumHeight(65)
        form.addRow(tr("恢复语句", "Resume prompt"), self.txt_prompt)
        form.addRow(
            _label(
                tr(
                    "恢复权限：工作区可读写＋自动审批",
                    "Recovery: workspace write + automatic approval reviews",
                )
            )
        )
        self.btn_save = QPushButton(tr("保存恢复设置", "Save resume settings"))
        self.btn_save.setObjectName("primary")
        self.btn_save.clicked.connect(
            lambda: self.settings_changed.emit(self.get_settings())
        )
        form.addRow(self.btn_save)
        self.recovery_details.hide()
        self.btn_details.toggled.connect(self.recovery_details.setVisible)
        layout.addWidget(self.recovery_details)
        row = QHBoxLayout()
        self.btn_resume = QPushButton(tr("刷新目标", "Refresh target"))
        self.btn_resume.clicked.connect(self.resume_now_requested)
        self.btn_history = QPushButton(tr("恢复记录", "Recovery history"))
        self.btn_history.clicked.connect(self.history_requested)
        self.btn_stop = QPushButton(tr("停止本次恢复", "Stop current recovery"))
        self.btn_stop.clicked.connect(self.stop_requested)
        for button in (self.btn_resume, self.btn_history, self.btn_stop):
            row.addWidget(button)
        row.addStretch()
        row.addWidget(self.btn_details)
        layout.addLayout(row)
        return card

    def _activation_card(self):
        card, layout = _card()
        row = QHBoxLayout()
        row.addWidget(
            _label(
                tr("持续激活五小时窗口", "Continuous five-hour activation"), "section"
            ),
            1,
        )
        row.addWidget(
            _label(
                tr("新对话 · 只读 · 自动循环", "New chat · read-only · recurring"),
                "pill",
            )
        )
        layout.addLayout(row)
        layout.addWidget(
            _label(
                tr(
                    "每次本地记录的窗口到期，只在新对话中发送一条启动消息；开启后关闭原对话自动恢复。",
                    "At each recorded reset, send one startup message in a new chat. Enabling this turns off conversation recovery.",
                )
            )
        )
        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        self.cmb_activation_when = QComboBox()
        self.cmb_activation_when.addItem(
            tr("跟随五小时重置时间", "Follow five-hour resets"), "next"
        )
        self.cmb_activation_when.addItem(
            tr("先在指定时间激活", "First activate at a chosen time"), "timed"
        )
        self.cmb_activation_when.currentIndexChanged.connect(
            self._activation_when_changed
        )
        self.activation_date = QDateTimeEdit(QDateTime.currentDateTime().addSecs(300))
        self.activation_date.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.activation_date.setCalendarPopup(True)
        self.activation_date.setEnabled(False)
        self.activation_date.hide()
        row = QHBoxLayout()
        row.addWidget(self.cmb_activation_when, 1)
        row.addWidget(self.activation_date, 1)
        form.addRow(tr("首次激活", "First activation"), row)
        self.txt_activation_cwd = QLineEdit(str(Path.cwd()))
        browse = QPushButton(tr("浏览…", "Browse…"))
        browse.clicked.connect(self._browse_activation)
        row = QHBoxLayout()
        row.addWidget(self.txt_activation_cwd, 1)
        row.addWidget(browse)
        form.addRow(tr("工作目录", "Directory"), row)
        self.cmb_activation_bucket = QComboBox()
        self.cmb_activation_bucket.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.cmb_activation_model = QComboBox()
        self.cmb_activation_model.setEditable(True)
        self.cmb_activation_model.setMinimumWidth(0)
        self.cmb_activation_model.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.cmb_activation_model.lineEdit().setPlaceholderText(
            tr("默认模型", "Default model")
        )
        row = QHBoxLayout()
        row.addWidget(self.cmb_activation_bucket, 1)
        row.addWidget(self.cmb_activation_model, 1)
        form.addRow(tr("额度 / 模型", "Quota / model"), row)
        layout.addLayout(form)
        self.lbl_activation = _label(
            tr("持续激活已关闭", "Continuous activation is off"),
            "activationStatus",
            True,
        )
        layout.addWidget(self.lbl_activation)
        self.lbl_activation_detail = _label("", selectable=True)
        layout.addWidget(self.lbl_activation_detail)
        row = QHBoxLayout()
        self.btn_activate = QPushButton(
            tr("开启持续激活", "Enable continuous activation")
        )
        self.btn_activate.setObjectName("primary")
        self.btn_activate.clicked.connect(self.submit_activation)
        self.btn_cancel_activation = QPushButton(
            tr("关闭持续激活", "Disable activation")
        )
        self.btn_cancel_activation.clicked.connect(
            lambda: self.settings_changed.emit({"auto_activate": False})
        )
        self.btn_queue = QPushButton(tr("激活记录", "Activation history"))
        self.btn_queue.clicked.connect(self.history_requested)
        row.addWidget(self.btn_activate)
        row.addWidget(self.btn_cancel_activation)
        row.addStretch()
        row.addWidget(self.btn_queue)
        layout.addLayout(row)
        return card

    def _quota_card(self):
        card, layout = _card()
        row = QHBoxLayout()
        self.banner = _label(tr("尚无本地限额记录", "No local quota record"), "section")
        row.addWidget(self.banner, 1)
        self.cmb_bucket = QComboBox()
        self.cmb_bucket.setMinimumWidth(160)
        self.cmb_bucket.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.cmb_bucket.currentIndexChanged.connect(self.render_limits)
        row.addWidget(self.cmb_bucket)
        layout.addLayout(row)
        middle = QHBoxLayout()
        self.window_labels, self.window_bars = [], []
        for _ in range(2):
            column = QVBoxLayout()
            label, bar = _label(), QProgressBar()
            bar.setRange(0, 100)
            bar.setTextVisible(False)
            column.addWidget(label)
            column.addWidget(bar)
            column.addStretch()
            middle.addLayout(column, 1)
            self.window_labels.append(label)
            self.window_bars.append(bar)
        layout.addLayout(middle)
        self.lbl_observed = _label()
        layout.addWidget(self.lbl_observed)
        self.lbl_note = _label(
            tr(
                "本地记录仅供参考；实际额度与重置时间由服务器决定。",
                "Local records are indicative; the server determines quota and reset times.",
            )
        )
        layout.addWidget(self.lbl_note)
        return card

    def load_settings(self, config):
        self.chk_auto_resume.setChecked(config["auto_resume"])
        self.spin_buffer.setValue(config["buffer_seconds"])
        self.txt_prompt.setPlainText(
            config["resume_prompt"] or t("default_resume_prompt")
        )
        self._preferred_activation_bucket = config["activation_bucket"]
        index = self.cmb_activation_bucket.findData(config["activation_bucket"])
        if index >= 0:
            self.cmb_activation_bucket.setCurrentIndex(index)
        self.txt_activation_cwd.setText(config["activation_cwd"] or str(Path.cwd()))
        self.cmb_activation_model.setCurrentText(config["activation_model"])
        self.cmb_activation_when.setCurrentIndex(
            1 if config["activation_start_at"] > time.time() else 0
        )
        if config["activation_start_at"]:
            self.activation_date.setDateTime(
                QDateTime.fromSecsSinceEpoch(int(config["activation_start_at"]))
            )
        if config["auto_activate"]:
            self.set_mode(1)
        elif config["auto_resume"]:
            self.set_mode(0)
        self.lbl_monitor.setText(
            tr(
                f"本地监测 · {config['poll_interval']} 秒",
                f"Local monitoring · {config['poll_interval']}s",
            )
        )

    def get_settings(self):
        return {
            "auto_resume": self.chk_auto_resume.isChecked(),
            "buffer_seconds": self.spin_buffer.value(),
            "resume_prompt": self.txt_prompt.toPlainText(),
        }

    def on_snapshot(self, snapshot):
        self.snapshot = snapshot
        key = self.cmb_bucket.currentData()
        self.cmb_bucket.blockSignals(True)
        self.cmb_bucket.clear()
        for bucket, limits in snapshot["buckets"].items():
            self.cmb_bucket.addItem(limits.get("limit_name") or bucket, bucket)
        index = self.cmb_bucket.findData(key)
        if index >= 0:
            self.cmb_bucket.setCurrentIndex(index)
        self.cmb_bucket.blockSignals(False)
        selected = (
            self.cmb_activation_bucket.currentData()
            or self._preferred_activation_bucket
        )
        self.cmb_activation_bucket.blockSignals(True)
        self.cmb_activation_bucket.clear()
        for bucket, limits in snapshot["buckets"].items():
            self.cmb_activation_bucket.addItem(
                limits.get("limit_name") or bucket, bucket
            )
        index = self.cmb_activation_bucket.findData(selected)
        if selected and index < 0:
            self.cmb_activation_bucket.addItem(
                tr("等待记录：", "Waiting for: ") + selected, selected
            )
            index = self.cmb_activation_bucket.count() - 1
        if index >= 0:
            self.cmb_activation_bucket.setCurrentIndex(index)
        self.cmb_activation_bucket.blockSignals(False)
        populate_models(self.cmb_activation_model, snapshot.get("models", []))
        self.render_limits()

    def render_recovery(self, target, settings):
        active = settings["auto_resume"]
        self.btn_stop.setEnabled(bool(target and target["status"] == "running"))
        if not target:
            self.lbl_recovery.setText(
                tr("等待新的限额中断聊天", "Waiting for a new quota interruption")
            )
            self.lbl_recovery.setToolTip("")
            self.lbl_recovery_cwd.setText(tr("目录：—", "Directory: —"))
            self.lbl_recovery_state.setText(
                tr("监测中", "Monitoring")
                if active
                else tr("自动恢复已关闭", "Recovery off")
            )
            self.lbl_recovery_countdown.setText("—")
            self.lbl_recovery_time.setText(
                tr(
                    "检测到限额中断后，实时显示对话标题与目录。",
                    "The title and directory appear when a quota interruption is detected.",
                )
            )
            return
        name = (
            " › ".join(
                part for part in (target.get("project"), target.get("title")) if part
            )
            or target["session_id"]
        )
        self.lbl_recovery.setText(name)
        self.lbl_recovery_cwd.setText(
            target.get("cwd") or tr("目录不可用", "Directory unavailable")
        )
        self.lbl_recovery_cwd.setToolTip(target.get("cwd") or "")
        status = (
            status_text(target["status"])
            if active
            else tr("自动恢复已关闭", "Recovery off")
        )
        if target["status"] == "running":
            status = status_text("running")
        elif active and not target.get("available"):
            status = tr("等待目标聊天的本地记录", "Waiting for target record")
        elif active and (not target.get("cwd") or not Path(target["cwd"]).is_dir()):
            status = tr("目标工作目录不可用", "Directory unavailable")
        self.lbl_recovery_state.setText(status)
        reset = target.get("reset_at")
        due = (
            max(reset + settings["buffer_seconds"], target.get("not_before", 0))
            if reset is not None
            else None
        )
        terminal = target["status"] in (
            "completed",
            "simulated",
            "failed",
            "cancelled",
            "interrupted",
            "running",
        )
        self.lbl_recovery_countdown.setText(
            "—" if terminal or not active else _duration(due)
        )
        self.lbl_recovery_time.setText(
            f"{tr('最早恢复', 'Earliest recovery')}: {time_text(due)}\n"
            f"{tr('本地重置记录', 'Local reset')}: {time_text(target.get('next_reset_at'))}"
        )
        self.lbl_recovery.setToolTip(
            f"ID: {target['session_id']}\n{target.get('error', '')}"
        )

    def _browse_activation(self):
        directory = QFileDialog.getExistingDirectory(
            self, tr("工作目录", "Directory"), self.txt_activation_cwd.text()
        )
        if directory:
            self.txt_activation_cwd.setText(directory)

    def _activation_when_changed(self):
        timed = self.cmb_activation_when.currentData() == "timed"
        self.activation_date.setEnabled(timed)
        self.activation_date.setVisible(timed)

    def submit_activation(self):
        at = 0.0
        if self.cmb_activation_when.currentData() == "timed":
            at = float(self.activation_date.dateTime().toSecsSinceEpoch())
            if at <= time.time():
                self.lbl_status.setText(
                    tr("请选择未来的日期时间。", "Choose a future date and time.")
                )
                return
        cwd = self.txt_activation_cwd.text().strip()
        if not cwd or not Path(cwd).is_dir():
            self.lbl_status.setText(
                tr("请选择有效的工作目录。", "Choose a valid directory.")
            )
            return
        self.activation_requested.emit(
            {
                "activation_cwd": cwd,
                "activation_model": self.cmb_activation_model.currentText().strip(),
                "activation_bucket": self.cmb_activation_bucket.currentData() or "",
                "activation_start_at": at,
                "auto_activate": True,
            }
        )

    def render_activation(self, plan, target, settings):
        active = settings["auto_activate"]
        if (
            target
            and target.get("scheduled_at")
            == self.activation_date.dateTime().toSecsSinceEpoch()
        ):
            self.cmb_activation_when.setCurrentIndex(0)
        self.btn_cancel_activation.setEnabled(active)
        self.btn_activate.setText(
            tr("更新持续激活", "Update continuous activation")
            if active
            else tr("开启持续激活", "Enable continuous activation")
        )
        if not active:
            self.lbl_activation.setText(
                tr("持续激活已关闭", "Continuous activation is off")
            )
        elif target and target["status"] == "running":
            self.lbl_activation.setText(
                tr(
                    "正在新对话中发送启动消息…",
                    "Sending a startup message in a new chat…",
                )
            )
        elif (
            not settings["activation_cwd"]
            or not Path(settings["activation_cwd"]).is_dir()
        ):
            self.lbl_activation.setText(
                tr("已暂停 · 工作目录不可用", "Paused · directory unavailable")
            )
        elif plan:
            self.lbl_activation.setText(
                f"{tr('下次激活', 'Next activation')} · {_duration(plan['due'])}"
            )
        else:
            self.lbl_activation.setText(
                tr(
                    "监测中 · 等待新的五小时重置记录",
                    "Monitoring · waiting for a new five-hour reset record",
                )
            )
        details = []
        if active:
            details.append(
                f"{tr('额度', 'Quota')}: {settings['activation_bucket'] or '—'} · {settings['activation_model'] or tr('默认模型', 'Default model')}"
            )
            if plan:
                details.append(
                    f"{tr('最早执行（含缓冲）', 'Earliest run (with buffer)')}: {time_text(plan['due'])}"
                )
            details.append(settings["activation_cwd"])
        else:
            details.append(
                tr(
                    "首次激活后，继续跟随新的五小时重置记录；无需开启执行队列。",
                    "After the first activation, follow new five-hour reset records. Independent of the task queue.",
                )
            )
        if target:
            details.append(
                f"{tr('上次激活', 'Last activation')}: {status_text(target['status'])} · {time_text(target.get('started_at'))}"
            )
            if target.get("last_error"):
                details.append(target["last_error"])
        self.lbl_activation_detail.setText("\n".join(details))

    def render_limits(self, *args):
        now = time.time()
        limits = self.snapshot.get("buckets", {}).get(self.cmb_bucket.currentData(), {})
        exhausted = False
        for i, key in enumerate(("primary", "secondary")):
            if (
                i == 1
                and limits
                and "secondary" in limits
                and limits.get("secondary") is None
            ):
                name = tr("周 / 次窗口", "Weekly / secondary")
                value = tr("无", "None")
                self.window_labels[i].setText(
                    f"{name} · {value}\n{tr('重置', 'Reset')}: —"
                )
                self.window_bars[i].setValue(0)
                self.window_bars[i].setFormat(value)
                self.window_bars[i].setEnabled(False)
                continue
            window = limits.get(key) or {}
            pct, end = window.get("used_percent"), window.get("resets_at")
            stale = bool(end and end <= now)
            minutes = window.get("window_minutes")
            name = (
                tr("主窗口", "Primary")
                if i == 0
                else tr("周 / 次窗口", "Weekly / secondary")
            )
            if minutes:
                name += f" ({minutes / 60:g}h)"
            value = tr("未知", "Unknown") if pct is None else f"{pct:g}%"
            suffix = tr(" · 记录已过期", " · record expired") if stale else ""
            self.window_labels[i].setText(
                f"{name} · {tr('已用', 'used')} {value}{suffix}\n"
                f"{tr('重置', 'Reset')}: {time_text(end)}"
            )
            self.window_bars[i].setValue(round(max(0, min(100, pct or 0))))
            self.window_bars[i].setFormat(value)
            self.window_bars[i].setEnabled(pct is not None and not stale)
            if end and end > now and pct is not None and pct >= 100:
                exhausted = True
        self.banner.setText(
            tr("本地记录：限额已耗尽", "Local record: quota exhausted")
            if exhausted
            else tr(
                "本地记录：尚有额度或等待更新",
                "Local record: quota available or awaiting update",
            )
            if limits
            else tr("尚无本地限额记录", "No local quota record")
        )
        self.banner.setStyleSheet(
            f"color: {'#f2c078' if exhausted else '#82d8c4'}; background: transparent;"
        )
        self.lbl_observed.setText(
            f"{tr('记录时间', 'Observed')}: {time_text(limits.get('observed_at'))} · "
            f"{tr('套餐', 'Plan')}: {limits.get('plan_type') or '—'}"
        )
        self.lbl_observed.setToolTip(limits.get("source", ""))
