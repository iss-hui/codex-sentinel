"""Update UI and its cancellable network/handoff worker."""

from threading import Event

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from codex_sentinel import __version__
from codex_sentinel.gui.common import tr
from codex_sentinel.updates import (
    RELEASES_URL,
    check_for_update,
    download_release,
    installation_kind,
    launch_updater,
)


class UpdateWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)
    progress = Signal(int, int)

    def __init__(self, operation, value, directory, parent=None):
        super().__init__(parent)
        self.operation = operation
        self.value = value
        self.directory = directory
        self.cancel = Event()

    def run(self):
        try:
            if self.operation == "check":
                result = check_for_update(installation_kind() or "folder")
            elif self.operation == "download":
                result = download_release(self.value, self.directory, self.cancel, self.progress.emit)
            else:
                result = launch_updater(self.value, self.cancel)
            if not self.cancel.is_set():
                self.completed.emit(result)
        except Exception as error:  # noqa: BLE001 - Qt worker boundary; report instead of crashing.
            if not self.cancel.is_set():
                self.failed.emit(str(error))


class UpdateDialog(QDialog):
    check_requested = Signal()
    download_requested = Signal()
    install_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.release = None
        self.setWindowTitle(tr("软件更新", "Software update"))
        self.resize(580, 500)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(16)
        title = QLabel(tr("Codex Sentinel 更新", "Codex Sentinel updates"))
        title.setObjectName("heading")
        layout.addWidget(title)
        layout.addWidget(QLabel(tr(f"当前版本  v{__version__}", f"Current version  v{__version__}")))
        self.status = QLabel(tr("检查是否有新版本。", "Check for a new version."))
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        self.notes = QTextBrowser()
        self.notes.setOpenExternalLinks(False)
        self.notes.setPlainText(tr("发现新版后会在这里显示更新说明。", "Release notes will appear here."))
        layout.addWidget(self.notes, 1)
        self.progress = QProgressBar()
        self.progress.setObjectName("downloadProgress")
        self.progress.hide()
        layout.addWidget(self.progress)
        self.support = QLabel(tr(
            "从 GitHub Release 下载；当前任务结束后才重启更新。",
            "Downloads from GitHub Releases; restarts after the current task finishes.",
        ) if installation_kind() else tr(
            "内置安装支持 Windows x64 打包版。当前运行方式请从发布页下载新版。",
            "In-app installation supports packaged Windows x64 builds. Download other builds from Releases.",
        ))
        self.support.setWordWrap(True)
        self.support.setObjectName("hint")
        layout.addWidget(self.support)
        buttons = QHBoxLayout()
        self.check = QPushButton(tr("检查更新", "Check for updates"))
        self.check.clicked.connect(self.check_requested)
        buttons.addWidget(self.check)
        self.open_release = QPushButton(tr("发布页", "Release page"))
        self.open_release.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(
            self.release.url if self.release else RELEASES_URL)))
        buttons.addWidget(self.open_release)
        buttons.addStretch()
        self.cancel = QPushButton(tr("取消下载", "Cancel download"))
        self.cancel.clicked.connect(self.cancel_requested)
        self.cancel.hide()
        buttons.addWidget(self.cancel)
        self.download = QPushButton(tr("下载更新", "Download update"))
        self.download.setObjectName("primary")
        self.download.clicked.connect(self.download_requested)
        self.download.setEnabled(False)
        buttons.addWidget(self.download)
        self.install = QPushButton(tr("重启更新", "Restart and update"))
        self.install.setObjectName("primary")
        self.install.clicked.connect(self.install_requested)
        self.install.hide()
        buttons.addWidget(self.install)
        layout.addLayout(buttons)

    def set_release(self, release):
        self.release = release
        if release:
            self.status.setText(tr(f"发现新版本 v{release.version}", f"Version v{release.version} is available"))
            self.notes.setPlainText(release.notes or tr("此版本未提供更新说明。", "No release notes provided."))
            self.download.setEnabled(installation_kind() is not None)
        else:
            self.status.setText(tr("当前已是最新版本。", "You are up to date."))
            self.notes.clear()
            self.download.setEnabled(False)

    def set_busy(self, operation):
        self.check.setEnabled(not operation)
        self.download.setEnabled(not operation and self.release is not None and installation_kind() is not None)
        self.install.setEnabled(not operation)
        self.cancel.setVisible(operation == "download")
        if operation:
            self.progress.show()
            self.progress.setRange(0, 0)
            self.status.setText({
                "check": tr("正在检查更新…", "Checking for updates…"),
                "download": tr("正在下载更新…", "Downloading update…"),
                "launch": tr("正在校验并准备更新，请稍候…", "Verifying and preparing the update…"),
            }[operation])
        else:
            self.progress.hide()

    def on_progress(self, received, total):
        self.progress.setRange(0, 100)
        self.progress.setValue(received * 100 // total)
        self.status.setText(tr(
            f"正在下载：{received / 1024**2:.1f} / {total / 1024**2:.1f} MB",
            f"Downloading: {received / 1024**2:.1f} / {total / 1024**2:.1f} MB",
        ))
