import sys

from PySide6.QtCore import QLockFile, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from codex_sentinel.config import ConfigManager
from codex_sentinel.gui.common import tr
from codex_sentinel.gui.icons import application_icon
from codex_sentinel.gui.main_window import MainWindow
from codex_sentinel.gui.tray_icon import SentinelTrayIcon
from codex_sentinel.i18n import set_lang

DARK_STYLESHEET = """
QMainWindow, QWidget { background-color: #1e1e2e; color: #cdd6f4; }
QPushButton { background-color: #313244; border: 1px solid #45475a; border-radius: 6px; padding: 8px 16px; color: #cdd6f4; }
QPushButton:hover { background-color: #45475a; }
QPushButton:pressed { background-color: #585b70; }
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox, QDateTimeEdit { background-color: #313244; border: 1px solid #45475a; border-radius: 4px; padding: 6px; color: #cdd6f4; }
QPushButton:checked { background-color: #285957; border-color: #52bca7; }
QPushButton:disabled { color: #7f849c; }
QProgressBar { border: none; border-radius: 4px; background: #313244; text-align: center; min-height: 18px; }
QProgressBar::chunk { background: #31786e; border-radius: 4px; }
QTableWidget { background-color: #1e1e2e; alternate-background-color: #181825; gridline-color: #313244; }
QTableWidget::item { padding: 4px; }
QHeaderView::section { background-color: #313244; color: #cdd6f4; padding: 6px; border: 1px solid #45475a; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 18px; height: 18px; }
QFrame#statusCard { background-color: #313244; border-radius: 8px; border-left: 3px solid #45475a; }
QScrollBar:vertical { background-color: #181825; width: 10px; }
QScrollBar::handle:vertical { background-color: #45475a; border-radius: 5px; min-height: 20px; }
QLabel#banner { padding: 12px; border-radius: 8px; font-size: 16px; font-weight: bold; }
QLabel#sectionTitle { font-size: 14px; font-weight: bold; color: #cdd6f4; }
"""


def main(overrides=None, dry_run=False, smoke_test=False):
    app = QApplication([sys.argv[0]])
    app.setApplicationName("Codex Sentinel")
    app.setWindowIcon(application_icon())
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(DARK_STYLESHEET)
    manager = ConfigManager()
    manager.config_dir.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(manager.config_dir / "desktop.lock"))
    # This lock lives for the whole application lifetime. tryLock already
    # recovers locks owned by dead processes; never force-remove a live lock.
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        if lock.error() == QLockFile.LockError.LockFailedError:
            QMessageBox.information(
                None,
                "Codex Sentinel",
                tr("应用已运行，请查看系统托盘。", "Already running. Check the system tray."),
            )
            return 0
        else:
            QMessageBox.critical(
                None,
                "Codex Sentinel",
                tr(
                    "无法创建应用锁，请检查配置目录的权限和可用空间：",
                    "Cannot create the app lock. Check directory permissions and free space: ",
                ) + str(manager.config_dir),
            )
            return 1
    try:
        settings = manager.load()
        if overrides:
            manager.save(overrides)
            settings = manager.load()
        set_lang(settings["language"])
        window = MainWindow(
            manager=manager, dry_run=dry_run, start_workers=not smoke_test
        )
    except Exception as exc:
        QMessageBox.critical(None, "Codex Sentinel", str(exc))
        lock.unlock()
        return 1
    if QSystemTrayIcon.isSystemTrayAvailable():
        tray = SentinelTrayIcon(window)
        window.tray = tray
        tray.show_dashboard_requested.connect(
            lambda: (window.showNormal(), window.raise_(), window.activateWindow())
        )
        tray.resume_now_requested.connect(window.refresh_recovery)
        tray.pause_requested.connect(window.toggle_recovery)
        tray.settings_requested.connect(
            lambda: (window.showNormal(), window.switch_page(4))
        )
        tray.quit_requested.connect(window.request_quit)
        tray.show()
    window.show()
    if smoke_test:
        QTimer.singleShot(200, window.request_quit)
    code = app.exec()
    lock.unlock()
    return code


if __name__ == "__main__":
    sys.exit(main())
