from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from codex_sentinel.config import DEFAULT_CONFIG
from codex_sentinel.gui.common import tr
from codex_sentinel.gui.ui import Toggle, card, field, heading, label


class SettingsPage(QWidget):
    settings_changed = Signal(dict)
    theme_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)
        heading(
            layout,
            tr("设置", "Settings"),
            tr(
                "配置外观、本地扫描与桌面执行方式。",
                "Configure appearance, local monitoring and desktop execution.",
            ),
        )
        grid = QGridLayout()
        grid.setSpacing(14)
        general, general_layout = card(tr("外观与语言", "Appearance and language"))
        self.cmb_theme = QComboBox()
        for title, value in (
            (tr("暗黑", "Dark"), "dark"),
            (tr("白色", "Light"), "light"),
            (tr("跟随系统", "System"), "system"),
        ):
            self.cmb_theme.addItem(title, value)
        self.cmb_theme.currentIndexChanged.connect(
            lambda: self.theme_changed.emit(self.cmb_theme.currentData())
        )
        general_layout.addWidget(
            field(tr("主题 · 立即生效", "Theme · applies immediately"), self.cmb_theme)
        )
        self.cmb_lang = QComboBox()
        self.cmb_lang.addItems(["auto", "zh", "en"])
        general_layout.addWidget(
            field(tr("语言（重启生效）", "Language (restart required)"), self.cmb_lang)
        )
        grid.addWidget(general, 0, 0)
        timing, timing_layout = card(tr("扫描与预约", "Monitoring and schedules"))
        self.spin_poll = QSpinBox()
        self.spin_poll.setRange(1, 300)
        self.spin_poll.setSuffix(tr(" 秒", " s"))
        timing_layout.addWidget(
            field(tr("本地扫描间隔", "Local scan interval"), self.spin_poll)
        )
        self.spin_grace = QSpinBox()
        self.spin_grace.setRange(0, 86400)
        self.spin_grace.setSuffix(tr(" 秒", " s"))
        timing_layout.addWidget(
            field(tr("错过预约的宽限时间", "Missed schedule grace"), self.spin_grace)
        )
        timing_layout.addWidget(
            label(
                tr(
                    "休眠期间不执行；超过宽限的预约需重新排期。",
                    "Schedules missed beyond the grace period require rescheduling.",
                ),
                "hint",
            )
        )
        grid.addWidget(timing, 0, 1)
        desktop, desktop_layout = card(tr("桌面与通知", "Desktop and notifications"))
        for name, title, description in (
            (
                "chk_take_over",
                tr("执行前接管 Codex 桌面", "Take over Codex desktop"),
                tr(
                    "关闭占用的桌面，结束后重新打开；会中断桌面中的任务。",
                    "Closes busy desktop tasks and reopens after execution; interrupts desktop work.",
                ),
            ),
            ("chk_minimize", tr("关闭窗口时留在托盘", "Keep running in tray on close"), ""),
            ("chk_notifs", tr("显示执行结果通知", "Execution notifications"), ""),
            ("chk_sound", tr("执行结束提示音", "Completion sound"), ""),
        ):
            control = Toggle(title)
            setattr(self, name, control)
            desktop_layout.addWidget(control)
            if description:
                desktop_layout.addWidget(label(description, "hint"))
        grid.addWidget(desktop, 1, 0)
        data, data_layout = card(tr("本地数据与 CLI", "Local data and CLI"))
        self.txt_sessions_dir = QLineEdit()
        self.txt_sessions_dir.setPlaceholderText("CODEX_HOME/sessions")
        row = QHBoxLayout()
        row.addWidget(self.txt_sessions_dir, 1)
        browse = QPushButton(tr("浏览…", "Browse…"))
        browse.clicked.connect(self._browse_sessions)
        row.addWidget(browse)
        data_layout.addWidget(field(tr("本地会话目录", "Local sessions directory"), row))
        self.txt_cli_path = QLineEdit()
        self.txt_cli_path.setPlaceholderText(
            tr("留空自动检测本机 Codex CLI", "Blank: auto-detect Codex CLI")
        )
        row = QHBoxLayout()
        row.addWidget(self.txt_cli_path, 1)
        browse_cli = QPushButton(tr("浏览…", "Browse…"))
        browse_cli.clicked.connect(self._browse_cli)
        row.addWidget(browse_cli)
        data_layout.addWidget(field("Codex CLI", row))
        data_layout.addWidget(
            label(
                tr(
                    "仅读取本地会话索引和日志，不写入 Codex 数据库。",
                    "Reads local indexes and logs; never writes the Codex database.",
                ),
                "hint",
            )
        )
        grid.addWidget(data, 1, 1)
        updates, updates_layout = card(tr("软件更新", "Software updates"))
        row = QHBoxLayout()
        self.chk_updates = Toggle(
            tr("自动检查软件更新（GitHub）", "Check updates automatically (GitHub)")
        )
        row.addWidget(self.chk_updates, 1)
        row.addSpacing(18)
        self.btn_updates = QPushButton(tr("检查软件更新", "Check for software updates"))
        row.addWidget(self.btn_updates)
        updates_layout.addLayout(row)
        grid.addWidget(updates, 2, 0, 1, 2)
        for panel_layout in (
            general_layout,
            timing_layout,
            desktop_layout,
            data_layout,
            updates_layout,
        ):
            panel_layout.setSpacing(11)
            panel_layout.setContentsMargins(18, 16, 18, 16)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        buttons = QHBoxLayout()
        buttons.addWidget(
            label(
                tr(
                    "主题即时保存；其他设置保存后生效。",
                    "Theme saves immediately; save other settings below.",
                ),
                "hint",
            ),
            1,
        )
        reset = QPushButton(tr("恢复默认设置", "Reset defaults"))
        reset.clicked.connect(lambda: self.settings_changed.emit(DEFAULT_CONFIG.copy()))
        buttons.addWidget(reset)
        save = QPushButton(tr("保存设置", "Save settings"))
        save.setObjectName("primary")
        save.clicked.connect(self.save_settings)
        buttons.addWidget(save)
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
        previous = self.cmb_theme.blockSignals(True)
        self.cmb_theme.setCurrentIndex(self.cmb_theme.findData(config["theme"]))
        self.cmb_theme.blockSignals(previous)
        self.cmb_lang.setCurrentText(config["language"])
        self.spin_poll.setValue(config["poll_interval"])
        self.spin_grace.setValue(config["missed_grace_seconds"])
        self.chk_minimize.setChecked(config["minimize_to_tray"])
        self.chk_notifs.setChecked(config["show_notifications"])
        self.chk_sound.setChecked(config["play_sound"])
        self.chk_take_over.setChecked(config["take_over_desktop"])
        self.chk_updates.setChecked(config["check_updates"])
        self.txt_sessions_dir.setText(config["sessions_dir"])
        self.txt_cli_path.setText(config["cli_path"])

    def save_settings(self):
        self.settings_changed.emit(
            {
                "language": self.cmb_lang.currentText(),
                "theme": self.cmb_theme.currentData(),
                "poll_interval": self.spin_poll.value(),
                "missed_grace_seconds": self.spin_grace.value(),
                "minimize_to_tray": self.chk_minimize.isChecked(),
                "show_notifications": self.chk_notifs.isChecked(),
                "play_sound": self.chk_sound.isChecked(),
                "take_over_desktop": self.chk_take_over.isChecked(),
                "check_updates": self.chk_updates.isChecked(),
                "sessions_dir": self.txt_sessions_dir.text(),
                "cli_path": self.txt_cli_path.text(),
            }
        )
