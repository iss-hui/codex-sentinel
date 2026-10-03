"""Workers perform local scanning and one CLI invocation off the GUI thread."""

import threading
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from codex_sentinel.execution import execute_task
from codex_sentinel.session_scanner import SessionScanner, get_available_models


class MonitorWorker(QThread):
    snapshot_ready = Signal(dict)
    error_occurred = Signal(str)

    def __init__(self, sessions_dir="", poll_interval=5, parent=None):
        super().__init__(parent)
        self.sessions_dir = sessions_dir
        self.poll_interval = poll_interval
        self._stop = threading.Event()
        self._wake = threading.Event()

    def run(self):
        scanner = None
        while not self._stop.is_set():
            try:
                directory = Path(self.sessions_dir) if self.sessions_dir else None
                if scanner is None or directory != getattr(self, "_directory", None):
                    scanner = SessionScanner(sessions_dir=directory)
                    self._directory = directory
                snapshot = scanner.scan()
                snapshot["models"] = get_available_models(scanner.codex_dir)
                if not self._stop.is_set():
                    self.snapshot_ready.emit(snapshot)
            except Exception as exc:
                self.error_occurred.emit(str(exc))
            self._wake.wait(self.poll_interval)
            self._wake.clear()

    def refresh(self):
        self._wake.set()

    def stop(self):
        self._stop.set()
        self._wake.set()


class ExecutionWorker(QThread):
    completed = Signal(dict)
    output_line = Signal(str)
    progress = Signal(str)

    def __init__(self, task, log_path, binary="", parent=None, take_over_desktop=False):
        super().__init__(parent)
        self.task = task
        self.log_path = log_path
        self.binary = binary
        self.take_over_desktop = take_over_desktop
        self.cancel = threading.Event()

    def run(self):
        try:
            result = execute_task(
                self.task,
                self.log_path,
                binary=self.binary,
                cancel=self.cancel,
                output=self.output_line.emit,
                take_over_desktop=self.take_over_desktop,
                progress=self.progress.emit,
            )
        except Exception as exc:
            result = {"code": 1, "error": str(exc), "session_id": self.task.session_id}
        self.completed.emit(result)

    def stop(self):
        self.cancel.set()
