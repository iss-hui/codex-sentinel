"""Real process checks, using only the test's isolated application directory."""

import os
import subprocess
import sys
import time
from pathlib import Path


def test_single_instance_rejects_live_owner_and_recovers_after_crash(tmp_path):
    directory = Path(os.environ["CODEX_SENTINEL_HOME"])
    directory.mkdir()
    ready = tmp_path / "ready"
    holder = """
import os, sys
from pathlib import Path
from PySide6.QtCore import QCoreApplication, QLockFile
app = QCoreApplication([])
lock = QLockFile(str(Path(os.environ['CODEX_SENTINEL_HOME']) / 'desktop.lock'))
lock.setStaleLockTime(0)
assert lock.tryLock(0)
Path(sys.argv[1]).touch()
sys.stdin.read()
os._exit(0)  # Simulate a crash without running QLockFile's destructor.
"""
    probe = """
from codex_sentinel.gui import app
app.QMessageBox.information = lambda *args: print('already-running', flush=True)
app.QMessageBox.critical = lambda *args: print('lock-error', flush=True)
raise SystemExit(app.main(smoke_test=True))
"""
    proc = subprocess.Popen([sys.executable, "-c", holder, str(ready)], stdin=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 5
        while not ready.exists() and proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready.exists(), "lock holder did not start"
        first = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                               text=True, timeout=10)
        assert first.returncode == 0, first.stderr
        assert "already-running" in first.stdout
        assert (directory / "desktop.lock").exists()
        proc.communicate(timeout=5)
        assert (directory / "desktop.lock").exists()
        second = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                                text=True, timeout=10)
        assert second.returncode == 0, second.stderr
        assert "already-running" not in second.stdout
        assert "lock-error" not in second.stdout
        assert not (directory / "desktop.lock").exists()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
        if proc.stdin:
            proc.stdin.close()
