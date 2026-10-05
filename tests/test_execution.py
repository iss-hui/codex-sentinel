import sys
import threading

import pytest

from codex_sentinel.execution import build_command, execute_task
from codex_sentinel.quota_scheduler import QuotaScheduler


def test_command_preserves_explicit_session_model_and_sandbox(tmp_path):
    task = QuotaScheduler(tmp_path).add_task(
        "test",
        '-m evil\nhello "quoted"',
        str(tmp_path),
        "cached-model",
        session_id="chosen-thread",
    )
    cmd = build_command(task, "codex.exe")
    assert cmd == [
        "codex.exe",
        "-a",
        "never",
        "exec",
        "--sandbox",
        "read-only",
        "resume",
        "--json",
        "--skip-git-repo-check",
        "--model",
        "cached-model",
        "chosen-thread",
        "-",
    ]
    assert task.prompt not in cmd


def fake_program(tmp_path, monkeypatch, code):
    path = tmp_path / "fake_cli.py"
    path.write_text(code, encoding="utf-8")
    monkeypatch.setattr(
        "codex_sentinel.execution.build_command",
        lambda *args: [sys.executable, str(path)],
    )


def test_actual_child_stdin_logs_and_completion(tmp_path, monkeypatch):
    task = QuotaScheduler(tmp_path).add_task("test", '中文\n"hello"', str(tmp_path))
    fake_program(
        tmp_path,
        monkeypatch,
        'import sys,json\nprompt=sys.stdin.buffer.read().decode("utf-8")\nprint(json.dumps({"type":"thread.started","thread_id":"new-thread"}))\nprint(json.dumps({"prompt":prompt}))\nprint(json.dumps({"type":"turn.completed"}))\n',
    )
    log = tmp_path / "run.log"
    result = execute_task(task, log, binary="fake")
    assert result["code"] == 0
    assert result["session_id"] == "new-thread"
    import json

    assert json.loads(log.read_text().splitlines()[1])["prompt"] == task.prompt


def test_zero_exit_without_completed_event_is_not_success(tmp_path, monkeypatch):
    task = QuotaScheduler(tmp_path).add_task("test", "hello", str(tmp_path))
    fake_program(
        tmp_path, monkeypatch, 'import sys\nsys.stdin.read()\nprint("warning only")\n'
    )
    assert execute_task(task, tmp_path / "run.log", binary="fake")["code"] != 0


def test_lock_does_not_spawn_or_kill_desktop(tmp_path, monkeypatch):
    task = QuotaScheduler(tmp_path).add_task(
        "test", "hello", str(tmp_path), session_id="occupied"
    )
    monkeypatch.setattr("codex_sentinel.execution.is_thread_locked", lambda _: True)
    monkeypatch.setattr(
        "codex_sentinel.execution.subprocess.Popen",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("must not spawn")),
    )
    assert execute_task(task, tmp_path / "run.log")["code"] == 75


def test_timeout_and_cancel_are_not_success(tmp_path, monkeypatch):
    task = QuotaScheduler(tmp_path).add_task("test", "hello", str(tmp_path))
    fake_program(
        tmp_path, monkeypatch, "import time,sys\nsys.stdin.read()\ntime.sleep(30)\n"
    )
    assert (
        execute_task(task, tmp_path / "run.log", binary="fake", timeout=0.1)["code"]
        == 124
    )
    cancelled = threading.Event()
    cancelled.set()
    assert (
        execute_task(task, tmp_path / "cancel.log", binary="fake", cancel=cancelled)[
            "code"
        ]
        == 130
    )


@pytest.mark.parametrize("linger", [False, True])
def test_completed_turn_reaps_helpers_and_releases_writer_lock(
    tmp_path, monkeypatch, isolated_codex_home, linger
):
    import json
    import time

    import psutil

    from codex_sentinel.lock_manager import is_thread_locked

    session_id = "owned-thread"
    lock = isolated_codex_home / "thread-writer-locks" / (session_id + ".lock")
    lock.parent.mkdir()
    ready, pids = tmp_path / "ready", tmp_path / "pids.json"
    child = tmp_path / "child.py"
    child.write_text(
        "import os,time\nfrom pathlib import Path\n"
        f"f=open({str(lock)!r}, 'w+b');f.write(b'x');f.flush();f.seek(0)\n"
        "if os.name=='nt':\n import msvcrt\n msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)\n"
        "else:\n import fcntl\n fcntl.flock(f.fileno(),fcntl.LOCK_EX)\n"
        f"Path({str(ready)!r}).write_text('ready')\ntime.sleep(60)\n",
        encoding="utf-8",
    )
    fake_program(
        tmp_path,
        monkeypatch,
        "import os,sys,time,json,subprocess\nfrom pathlib import Path\nsys.stdin.read()\n"
        f"child=subprocess.Popen([sys.executable,{str(child)!r}])\n"
        f"Path({str(pids)!r}).write_text(json.dumps([os.getpid(),child.pid]))\n"
        f"while not Path({str(ready)!r}).exists():time.sleep(.01)\n"
        f"print(json.dumps({{'type':'thread.started','thread_id':{session_id!r}}}),flush=True)\n"
        "print(json.dumps({'type':'turn.completed'}),flush=True)\n"
        + ("time.sleep(60)\n" if linger else ""),
    )
    task = QuotaScheduler(tmp_path).add_task(
        "test", "hello", str(tmp_path), session_id=session_id
    )
    result = execute_task(
        task, tmp_path / "owned.log", binary="fake", timeout=5, exit_grace=0.1
    )
    assert result["code"] == 0, result
    assert result["cleanup_ok"], result
    deadline = time.monotonic() + 3
    while is_thread_locked(session_id) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not is_thread_locked(session_id)
    deadline = time.monotonic() + 3
    while any(psutil.pid_exists(pid) for pid in json.loads(pids.read_text())) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not any(psutil.pid_exists(pid) for pid in json.loads(pids.read_text()))


def test_terminal_parser_handles_partial_lines_and_does_not_trust_tool_output():
    from codex_sentinel.execution import TurnEvents

    events = TurnEvents("chosen")
    events.feed(
        b'{"type":"item.completed","item":{"type":"command_execution","aggregated_output":"turn.completed"}}\n'
    )
    assert not events.terminal
    events.feed(b'{"type":"turn.com')
    assert not events.terminal
    events.feed(b'pleted"}')
    assert not events.terminal
    events.feed(b"", final=True)
    assert events.terminal == "turn.completed"


def test_handoff_reopens_only_after_cli_cleanup(tmp_path, monkeypatch):
    calls = []

    class Desktop:
        def __init__(self):
            self.closed_executables = []

        def close(self):
            calls.append("close")
            self.closed_executables.append("codex-desktop")
            return True

        def reopen(self):
            calls.append("reopen")

    monkeypatch.setattr("codex_sentinel.execution.DesktopHandoff", Desktop)
    monkeypatch.setattr("codex_sentinel.execution.is_thread_locked", lambda _: True)
    monkeypatch.setattr(
        "codex_sentinel.execution.wait_for_lock_release",
        lambda *a, **kw: calls.append("lock_free") or True,
    )
    from codex_sentinel.owned_process import OwnedProcess

    cleanup = OwnedProcess.cleanup

    def tracked_cleanup(self):
        cleanup(self)
        calls.append("cleaned")

    monkeypatch.setattr(OwnedProcess, "cleanup", tracked_cleanup)
    fake_program(
        tmp_path,
        monkeypatch,
        'import sys\nsys.stdin.read()\nprint(\'{"type":"turn.completed"}\')\n',
    )
    task = QuotaScheduler(tmp_path).add_task(
        "test", "hello", str(tmp_path), session_id="chosen"
    )
    result = execute_task(
        task, tmp_path / "handoff.log", binary="fake", take_over_desktop=True
    )
    assert result["code"] == 0, result
    assert calls == ["close", "lock_free", "cleaned", "lock_free", "reopen"]


@pytest.mark.parametrize("failure", ["spawn", "cancel", "lock"])
def test_handoff_failure_restores_desktop(tmp_path, monkeypatch, failure):
    calls = []
    cancel = threading.Event()

    class Desktop:
        def __init__(self):
            self.closed_executables = []

        def close(self):
            self.closed_executables.append("codex-desktop")
            if failure == "cancel":
                cancel.set()
            return True

        def reopen(self):
            calls.append("reopen")

    monkeypatch.setattr("codex_sentinel.execution.DesktopHandoff", Desktop)
    monkeypatch.setattr("codex_sentinel.execution.is_thread_locked", lambda _: True)
    monkeypatch.setattr(
        "codex_sentinel.execution.wait_for_lock_release",
        lambda *a, **kw: failure == "spawn",
    )
    task = QuotaScheduler(tmp_path).add_task(
        "test", "hello", str(tmp_path), session_id="chosen"
    )
    result = execute_task(
        task,
        tmp_path / "failed.log",
        binary=str(tmp_path / "missing-cli.exe"),
        take_over_desktop=True,
        cancel=cancel,
    )
    assert result["code"] == (130 if failure == "cancel" else 1)
    assert calls == ["reopen"]


def test_failed_turn_cleans_up_without_marking_success(tmp_path, monkeypatch):
    task = QuotaScheduler(tmp_path).add_task("test", "hello", str(tmp_path))
    fake_program(
        tmp_path,
        monkeypatch,
        'import sys,time\nsys.stdin.read()\nprint(\'{"type":"turn.failed","error":{"message":"quota"}}\',flush=True)\ntime.sleep(60)\n',
    )
    result = execute_task(task, tmp_path / "failed.log", binary="fake", exit_grace=0.1)
    assert result["code"] == 1
    assert "quota" in result["error"]
    assert result["cleanup_ok"]


def test_unexpected_started_thread_never_retargets_task(tmp_path, monkeypatch):
    task = QuotaScheduler(tmp_path).add_task(
        "test", "hello", str(tmp_path), session_id="chosen"
    )
    fake_program(
        tmp_path,
        monkeypatch,
        'import sys\nsys.stdin.read()\nprint(\'{"type":"thread.started","thread_id":"other"}\')\nprint(\'{"type":"turn.completed"}\')\n',
    )
    result = execute_task(task, tmp_path / "mismatch.log", binary="fake")
    assert result["code"] != 0
    assert result["session_id"] == "chosen"
    assert "different conversation" in result["error"]
