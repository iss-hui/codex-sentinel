import time

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from codex_sentinel.gui.common import populate_sessions, time_text, tr
from codex_sentinel.gui.widgets.countdown_ring import CountdownRing
from codex_sentinel.i18n import t


class DashboardPage(QWidget):
    resume_now_requested = Signal()
    pause_requested = Signal()
    settings_changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.snapshot = {}
        layout = QVBoxLayout(self)
        self.banner = QLabel(tr("正在读取本地记录…", "Reading local records…"))
        self.banner.setObjectName("banner")
        layout.addWidget(self.banner)
        self.cmb_bucket = QComboBox()
        self.cmb_bucket.currentIndexChanged.connect(self.render_limits)
        layout.addWidget(self.cmb_bucket)
        middle = QHBoxLayout()
        self.countdown = CountdownRing()
        self.countdown.setFixedSize(225, 225)
        middle.addWidget(self.countdown)
        windows = QVBoxLayout()
        self.window_labels, self.window_bars = [], []
        for _ in range(2):
            label, bar = QLabel(), QProgressBar()
            label.setWordWrap(True)
            bar.setRange(0, 100)
            windows.addWidget(label)
            windows.addWidget(bar)
            self.window_labels.append(label)
            self.window_bars.append(bar)
        self.lbl_observed = QLabel()
        self.lbl_observed.setWordWrap(True)
        windows.addWidget(self.lbl_observed)
        middle.addLayout(windows, 1)
        layout.addLayout(middle)
        self.lbl_note = QLabel(
            tr(
                "显示本地最近一次记录；倒计时结束不代表服务器已确认恢复。",
                "Latest local record; countdown expiry is not server confirmation.",
            )
        )
        self.lbl_note.setWordWrap(True)
        layout.addWidget(self.lbl_note)
        form = QFormLayout()
        self.cmb_session = QComboBox()
        form.addRow(tr("恢复对话", "Conversation to resume"), self.cmb_session)
        self.chk_auto_resume = QCheckBox(
            tr(
                "限额到期后自动恢复被中断的对话",
                "Auto-resume conversations interrupted by quota",
            )
        )
        form.addRow(self.chk_auto_resume)
        self.chk_resume_write = QCheckBox(
            tr(
                "允许恢复任务修改工作目录中的文件",
                "Allow resumed tasks to edit workspace files",
            )
        )
        form.addRow(self.chk_resume_write)
        row = QHBoxLayout()
        self.spin_buffer = QSpinBox()
        self.spin_buffer.setRange(0, 600)
        self.spin_buffer.setSuffix(tr(" 秒", " s"))
        row.addWidget(self.spin_buffer)
        for value in (30, 60):
            button = QPushButton(f"{value}s")
            button.clicked.connect(
                lambda checked=False, value=value: self.spin_buffer.setValue(value)
            )
            row.addWidget(button)
        row.addStretch()
        form.addRow(tr("到期后缓冲", "Buffer after reset"), row)
        self.txt_prompt = QTextEdit()
        self.txt_prompt.setMaximumHeight(75)
        form.addRow(tr("恢复语句", "Resume prompt"), self.txt_prompt)
        layout.addLayout(form)
        buttons = QHBoxLayout()
        self.btn_save = QPushButton(tr("保存恢复设置", "Save resume settings"))
        self.btn_save.clicked.connect(
            lambda: self.settings_changed.emit(self.get_settings())
        )
        self.btn_resume = QPushButton(tr("加入恢复队列", "Queue resume"))
        self.btn_resume.clicked.connect(self.resume_now_requested)
        self.btn_pause = QPushButton(tr("暂停自动执行", "Pause execution"))
        self.btn_pause.clicked.connect(self.pause_requested)
        for button in (self.btn_save, self.btn_resume, self.btn_pause):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.lbl_status = QLabel()
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)
        layout.addStretch()

    def load_settings(self, config):
        self.chk_auto_resume.setChecked(config["auto_resume"])
        self.chk_resume_write.setChecked(config["resume_sandbox"] == "workspace-write")
        self.spin_buffer.setValue(config["buffer_seconds"])
        self.txt_prompt.setPlainText(
            config["resume_prompt"] or t("default_resume_prompt")
        )

    def get_settings(self):
        return {
            "auto_resume": self.chk_auto_resume.isChecked(),
            "buffer_seconds": self.spin_buffer.value(),
            "resume_prompt": self.txt_prompt.toPlainText(),
            "resume_sandbox": "workspace-write"
            if self.chk_resume_write.isChecked()
            else "read-only",
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
        populate_sessions(self.cmb_session, snapshot["sessions"], new_session=False)
        self.btn_resume.setEnabled(bool(snapshot["sessions"]))
        self.render_limits()

    def render_limits(self, *args):
        now = time.time()
        limits = self.snapshot.get("buckets", {}).get(self.cmb_bucket.currentData(), {})
        exhausted = False
        reset = 0
        for i, key in enumerate(("primary", "secondary")):
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
                reset = max(reset, end)
        primary = limits.get("primary") or {}
        reset = reset or primary.get("resets_at") or 0
        remaining = max(0, int(reset - now))
        total = max(remaining, (primary.get("window_minutes") or 300) * 60)
        self.countdown.set_countdown(total, remaining)
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
            f"background-color: {'#714c17' if exhausted else '#234c46'};"
        )
        self.lbl_observed.setText(
            f"{tr('记录时间', 'Observed')}: {time_text(limits.get('observed_at'))}\n"
            f"{tr('套餐', 'Plan')}: {limits.get('plan_type') or '—'}"
        )
        self.lbl_observed.setToolTip(limits.get("source", ""))
