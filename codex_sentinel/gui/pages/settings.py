from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from codex_sentinel.config import DEFAULT_CONFIG
from codex_sentinel.gui.common import tr


class SettingsPage(QWidget):
    settings_changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.cmb_lang = QComboBox()
        self.cmb_lang.addItems(["auto", "zh", "en"])
        form.addRow(
            tr("语言（重启生效）", "Language (restart required)"), self.cmb_lang
        )
        self.spin_poll = QSpinBox()
        self.spin_poll.setRange(1, 300)
        form.addRow(
            tr("本地扫描间隔（秒）", "Local scan interval (seconds)"), self.spin_poll
        )
        self.spin_grace = QSpinBox()
        self.spin_grace.setRange(0, 86400)
        form.addRow(
            tr("错过预约的宽限时间（秒）", "Missed schedule grace (seconds)"),
            self.spin_grace,
        )
        for name, label in (
            (
                "chk_take_over",
                tr(
                    "关闭占用的 Codex 后执行，结束后重新打开（会中断桌面中的任务）",
                    "Close busy Codex before execution and reopen afterward (interrupts desktop tasks)",
                ),
            ),
            ("chk_minimize", tr("关闭窗口时留在托盘", "Keep running in tray on close")),
            ("chk_notifs", tr("显示执行结果通知", "Show execution notifications")),
            ("chk_sound", tr("执行结束提示音", "Sound on completion")),
        ):
            widget = QCheckBox(label)
            setattr(self, name, widget)
            form.addRow(widget)
        self.txt_sessions_dir = QLineEdit()
        self.txt_sessions_dir.setPlaceholderText("CODEX_HOME/sessions")
        row = QHBoxLayout()
        row.addWidget(self.txt_sessions_dir)
        browse = QPushButton(tr("浏览…", "Browse…"))
        browse.clicked.connect(self._browse_sessions)
        row.addWidget(browse)
        form.addRow(tr("本地会话目录", "Local sessions directory"), row)
        self.txt_cli_path = QLineEdit()
        self.txt_cli_path.setPlaceholderText(
            tr("自动检测本机 Codex CLI", "Auto-detect installed Codex CLI")
        )
        row = QHBoxLayout()
        row.addWidget(self.txt_cli_path)
        browse_cli = QPushButton(tr("浏览…", "Browse…"))
        browse_cli.clicked.connect(self._browse_cli)
        row.addWidget(browse_cli)
        form.addRow(tr("Codex CLI", "Codex CLI"), row)
        layout.addLayout(form)
        note = QLabel(
            tr(
                "仪表盘和会话列表仅访问本地文件。只有执行预约或恢复对话时才调用 Codex。电脑休眠期间不执行；超出宽限期的预约会标为已错过，需重新排期。",
                "Dashboard and history read local files only. Codex is invoked only for scheduled turns or resumes. Schedules do not run during sleep; those beyond the grace period need rescheduling.",
            )
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QHBoxLayout()
        save = QPushButton(tr("保存设置", "Save settings"))
        save.clicked.connect(self.save_settings)
        reset = QPushButton(tr("恢复默认设置", "Reset defaults"))
        reset.clicked.connect(lambda: self.settings_changed.emit(DEFAULT_CONFIG.copy()))
        buttons.addWidget(save)
        buttons.addWidget(reset)
        layout.addLayout(buttons)
        layout.addStretch()

    def _browse_sessions(self):
        directory = QFileDialog.getExistingDirectory(
            self, tr("会话目录", "Sessions directory")
        )
        if directory:
            self.txt_sessions_dir.setText(directory)

    def _browse_cli(self):
        path, _ = QFileDialog.getOpenFileName(self, "Codex CLI")
        if path:
            self.txt_cli_path.setText(path)

    def load_settings(self, config):
        self.cmb_lang.setCurrentText(config["language"])
        self.spin_poll.setValue(config["poll_interval"])
        self.spin_grace.setValue(config["missed_grace_seconds"])
        self.chk_minimize.setChecked(config["minimize_to_tray"])
        self.chk_notifs.setChecked(config["show_notifications"])
        self.chk_sound.setChecked(config["play_sound"])
        self.chk_take_over.setChecked(config["take_over_desktop"])
        self.txt_sessions_dir.setText(config["sessions_dir"])
        self.txt_cli_path.setText(config["cli_path"])

    def save_settings(self):
        self.settings_changed.emit(
            {
                "language": self.cmb_lang.currentText(),
                "poll_interval": self.spin_poll.value(),
                "missed_grace_seconds": self.spin_grace.value(),
                "minimize_to_tray": self.chk_minimize.isChecked(),
                "show_notifications": self.chk_notifs.isChecked(),
                "play_sound": self.chk_sound.isChecked(),
                "take_over_desktop": self.chk_take_over.isChecked(),
                "sessions_dir": self.txt_sessions_dir.text(),
                "cli_path": self.txt_cli_path.text(),
            }
        )
