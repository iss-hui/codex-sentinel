from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from codex_sentinel.gui.common import tr
from codex_sentinel.gui.icons import application_icon
from codex_sentinel.gui.theme import colors as theme_colors


class SentinelTrayIcon(QSystemTrayIcon):
    show_dashboard_requested = Signal()
    resume_now_requested = Signal()
    pause_requested = Signal()
    settings_requested = Signal()
    quit_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._logo = application_icon()
        self.menu = QMenu(parent)
        for label, signal in (
            (tr("打开仪表盘", "Open dashboard"), self.show_dashboard_requested),
            (
                tr("检查最新限额中断", "Check latest quota interruption"),
                self.resume_now_requested,
            ),
            (tr("暂停 / 继续自动恢复", "Pause / resume automatic recovery"), self.pause_requested),
            (tr("设置", "Settings"), self.settings_requested),
            (tr("退出 Sentinel", "Quit Sentinel"), self.quit_requested),
        ):
            action = QAction(label, self.menu)
            action.triggered.connect(signal)
            self.menu.addAction(action)
        self.setContextMenu(self.menu)
        self.set_state("unknown")
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_dashboard_requested.emit()

    def refresh_theme(self):
        self.set_state(self._state)

    def set_state(self, state):
        colors = {
            "unknown": "#7f849c",
            "normal": "#10b981",
            "limited": "#f59e0b",
            "resuming": "#3b82f6",
            "error": "#ef4444",
        }
        labels = {
            "unknown": tr("状态未知 / 等待本地更新", "Unknown / awaiting local update"),
            "normal": tr("正常监控中", "Monitoring"),
            "limited": tr("限额冷却中", "Rate limited"),
            "resuming": tr("正在恢复会话", "Resuming session"),
            "error": tr("错误", "Error"),
        }
        self._state = state
        border_color = theme_colors(self.parent())["sidebar"]
        presentation = (state, labels.get(state, state), border_color)
        if getattr(self, "_presentation", None) == presentation:
            return
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.drawPixmap(0, 0, self._logo.pixmap(32, 32))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(border_color))
        painter.drawEllipse(20, 20, 12, 12)
        painter.setBrush(QColor(colors.get(state, "#10b981")))
        painter.drawEllipse(22, 22, 8, 8)
        painter.end()
        self.setIcon(QIcon(pixmap))
        self.setToolTip(f"Codex Sentinel · {labels.get(state, state)}")
        self._presentation = presentation

    def show_notification(self, title, message):
        self.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 3000)
