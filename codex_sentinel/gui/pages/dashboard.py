import time
from pathlib import Path

from PySide6.QtCore import Qt, Signal
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

from codex_sentinel.gui.common import status_text, time_text, tr
from codex_sentinel.gui.widgets.countdown_ring import CountdownRing
from codex_sentinel.i18n import t


class DashboardPage(QWidget):
    resume_now_requested = Signal()
    stop_requested = Signal()
    history_requested = Signal()
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
        self.chk_auto_resume = QCheckBox(tr(
            "自动恢复最新的限额中断聊天（独立监控，不加入队列）",
            "Automatically recover the latest quota-interrupted chat (independent of queue)",
        ))
        form.addRow(self.chk_auto_resume)
        permissions = QLabel(tr("恢复权限：工作区可读写＋自动审批", "Recovery permissions: workspace write + automatic approval reviews"))
        permissions.setWordWrap(True)
        form.addRow(permissions)
        self.lbl_recovery = QLabel()
        self.lbl_recovery.setWordWrap(True)
        self.lbl_recovery.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow(self.lbl_recovery)
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
        self.btn_resume = QPushButton(tr("刷新检测", "Refresh detection"))
        self.btn_resume.clicked.connect(self.resume_now_requested)
        self.btn_stop = QPushButton(tr("停止本次恢复", "Stop current recovery"))
        self.btn_stop.clicked.connect(self.stop_requested)
        self.btn_history = QPushButton(tr("恢复记录与日志", "Recovery history and logs"))
        self.btn_history.clicked.connect(self.history_requested)
        for button in (self.btn_save, self.btn_resume, self.btn_stop, self.btn_history):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.lbl_status = QLabel()
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)
        layout.addStretch()

    def load_settings(self, config):
        self.chk_auto_resume.setChecked(config["auto_resume"])
        self.spin_buffer.setValue(config["buffer_seconds"])
        self.txt_prompt.setPlainText(
            config["resume_prompt"] or t("default_resume_prompt")
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
        self.render_limits()

    def render_recovery(self, target, settings):
        active = settings["auto_resume"]
        if not target:
            self.lbl_recovery.setText(tr("等待新的限额中断聊天", "Waiting for a new quota interruption")
                                     if active else tr("自动恢复已关闭", "Automatic recovery is off"))
            self.btn_stop.setEnabled(False)
            return
        name = " › ".join(part for part in (target.get("project"), target.get("title")) if part)
        status = status_text(target["status"]) if active else tr("自动恢复已关闭", "Automatic recovery is off")
        if active and not target.get("available"):
            status = tr("等待目标聊天的本地记录", "Waiting for the target's local record")
        elif active and (not target.get("cwd") or not Path(target["cwd"]).is_dir()):
            status = tr("目标工作目录不可用", "Target working directory unavailable")
        reset = target.get("reset_at")
        due = max(reset + settings["buffer_seconds"], target.get("not_before", 0)) if reset is not None else None
        remaining = max(0, int(due - time.time())) if due is not None else None
        countdown = f"{remaining // 3600:02}:{remaining // 60 % 60:02}:{remaining % 60:02}" if remaining is not None else "—"
        self.lbl_recovery.setText(
            f"{tr('恢复目标', 'Recovery target')}: {name}\n"
            f"{tr('状态', 'Status')}: {status}\n"
            f"{tr('最早恢复（含缓冲）', 'Earliest recovery (with buffer)')}: {time_text(due)} · {countdown}\n"
            f"{tr('下次本地重置记录', 'Next locally recorded reset')}: {time_text(target.get('next_reset_at'))}"
        )
        self.lbl_recovery.setToolTip(f"ID: {target['session_id']}\n{target.get('error', '')}")
        self.btn_stop.setEnabled(target["status"] == "running")

    def render_limits(self, *args):
        now = time.time()
        limits = self.snapshot.get("buckets", {}).get(self.cmb_bucket.currentData(), {})
        exhausted = False
        reset = 0
        for i, key in enumerate(("primary", "secondary")):
            if i == 1 and limits and "secondary" in limits and limits.get("secondary") is None:
                name = tr("周 / 次窗口", "Weekly / secondary")
                value = tr("无", "None")
                self.window_labels[i].setText(f"{name} · {value}\n{tr('重置', 'Reset')}: —")
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
