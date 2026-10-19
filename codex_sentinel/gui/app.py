import sys

from PySide6.QtCore import QLockFile, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from codex_sentinel.config import ConfigManager
from codex_sentinel.gui.common import tr
from codex_sentinel.gui.icons import application_icon
from codex_sentinel.gui.main_window import MainWindow
from codex_sentinel.gui.theme import DARK_STYLESHEET
from codex_sentinel.gui.tray_icon import SentinelTrayIcon
from codex_sentinel.i18n import set_lang


def main(overrides=None, dry_run=False, smoke_test=False):
    app = QApplication([sys.argv[0]])
    app.setApplicationName("Codex Sentinel")
    app.setStyle("Fusion")
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
