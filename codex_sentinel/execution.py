"""Run one CLI turn, release its entire process group, then restore the desktop."""

from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path

from codex_sentinel.desktop_handoff import DesktopHandoff
from codex_sentinel.lock_manager import is_thread_locked, wait_for_lock_release
from codex_sentinel.owned_process import OwnedProcess
from codex_sentinel.resume import find_codex_binary


def build_command(task, binary):
    command = [binary, "-a", "never", "exec", "--sandbox", task.sandbox]
    if task.session_id:
        command.append("resume")
    command.extend(["--json", "--skip-git-repo-check"])
    if task.model:
        command.extend(["--model", task.model])
    if task.session_id:
        command.append(task.session_id)
    command.append("-")  # Preserve prompt quotes/newlines through stdin.
    return command


class TurnEvents:
    """Parse only top-level lifecycle events, never nested command output."""

    def __init__(self, session_id=""):
        self.session_id = session_id
        self.pending = b""
        self.terminal = ""
        self.error = ""

    def feed(self, chunk, final=False):
        lines = (self.pending + chunk).split(b"\n")
        self.pending = b"" if final else lines.pop()
        for line in lines:
            try:
                event = json.loads(line)
            except (ValueError, UnicodeError):
                continue
            if not isinstance(event, dict):
                continue
            kind = event.get("type")
            if kind == "thread.started":
                self.session_id = event.get("thread_id") or self.session_id
            elif kind in ("turn.completed", "turn.failed"):
                self.terminal = kind
                if kind == "turn.failed":
                    self.error = str(event.get("error") or "Turn failed")
            elif kind == "error":
                self.error = str(event.get("error") or event.get("message") or event)


def execute_task(
    task,
    log_path: Path,
    *,
    binary="",
    cancel=None,
    output=None,
    timeout=None,
    take_over_desktop=False,
    progress=None,
    exit_grace=2.0,
):
    cancel = cancel or threading.Event()
    output = output or (lambda text: None)
    progress = progress or (lambda phase: None)
    result = {"code": 1, "error": "", "session_id": task.session_id, "cleanup_ok": True}
    if cancel.is_set():
        return {**result, "code": 130, "error": "Cancelled"}
    if not Path(task.cwd).is_dir():
        return {**result, "error": "Working directory no longer exists"}
    if task.session_id and is_thread_locked(task.session_id) and not take_over_desktop:
        return {
            **result,
            "code": 75,
            "error": "Conversation is busy in Codex; waiting for its writer lock.",
        }

    owner, desktop = OwnedProcess(), DesktopHandoff()
    events = TurnEvents(task.session_id)
    timeout = timeout if timeout is not None else (120 if task.kind == "kick" else 3600)
    try:
        # Resolve the CLI and prepare its log before interrupting the desktop.
        command = build_command(task, binary or find_codex_binary())
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("wb") as log:
            if task.session_id and is_thread_locked(task.session_id):
                if not take_over_desktop:
                    result.update(
                        code=75,
                        error="Conversation is busy in Codex; waiting for its writer lock.",
                    )
                    return result
                progress("closing_desktop")
                if not desktop.close():
                    raise RuntimeError(
                        "Conversation is locked, but no Codex desktop instance was identified. No unrelated process was stopped."
                    )
                progress("waiting_for_lock")
                if not wait_for_lock_release(task.session_id, cancel=cancel):
                    if cancel.is_set():
                        result.update(code=130, error="Cancelled")
                    else:
                        result["error"] = (
                            "Codex was closed, but the conversation lock is still held. Execution was not started."
                        )
                    return result
            if cancel.is_set():
                result.update(code=130, error="Cancelled")
                return result
            progress("running")
            process = owner.start(
                command,
                cwd=task.cwd,
                stdin=subprocess.PIPE,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            process.stdin.write(task.prompt.encode("utf-8"))
            process.stdin.close()
            started, terminal_at = time.monotonic(), None
            with log_path.open("rb") as reader:
                while True:
                    chunk = reader.read(262144)
                    if chunk:
                        output(chunk.decode("utf-8", errors="replace"))
                        events.feed(chunk)
                    ended = process.poll() is not None
                    if ended:
                        # Drain the final output, including an unterminated last line.
                        rest = reader.read()
                        if rest:
                            output(rest.decode("utf-8", errors="replace"))
                        events.feed(rest, final=True)
                    if (
                        events.session_id
                        and task.session_id
                        and events.session_id != task.session_id
                    ):
                        result["error"] = (
                            "CLI started a different conversation; execution stopped."
                        )
                        break
                    if events.terminal:
                        if terminal_at is None:
                            terminal_at = time.monotonic()
                            progress("cleanup")
                        if (
                            ended
                            or cancel.is_set()
                            or time.monotonic() - terminal_at >= exit_grace
                        ):
                            result["code"] = (
                                0 if events.terminal == "turn.completed" else 1
                            )
                            result["error"] = (
                                "" if result["code"] == 0 else events.error
                            )
                            break
                    elif ended:
                        result["code"] = process.returncode or 1
                        result["error"] = (
                            events.error
                            or "CLI exited without a turn.completed event; completion is unverified."
                        )
                        break
                    elif cancel.is_set():
                        result.update(
                            code=130,
                            error="Cancelled; inspect the log before retrying.",
                        )
                        break
                    elif time.monotonic() - started >= timeout:
                        result.update(
                            code=124,
                            error="Execution timed out; inspect the log before retrying.",
                        )
                        break
                    cancel.wait(0.1)
    except Exception as exc:
        result["error"] = str(exc)
    finally:
        result["session_id"] = task.session_id or events.session_id
        if owner.process is not None:
            progress("cleanup")
            try:
                owner.cleanup()
                # Do not reopen the desktop while this CLI still owns the writer.
                if events.session_id and not wait_for_lock_release(
                    events.session_id, timeout=5
                ):
                    raise RuntimeError(
                        "Conversation lock was not released after CLI cleanup"
                    )
            except Exception as exc:
                result["cleanup_ok"] = False
                result["error"] = (
                    result["error"] + "\n" if result["error"] else ""
                ) + f"Process cleanup failed: {exc}"
        if desktop.closed_executables and result["cleanup_ok"]:
            progress("reopening_desktop")
            try:
                desktop.reopen()
            except Exception as exc:
                result["error"] = (
                    result["error"] + "\n" if result["error"] else ""
                ) + f"Could not reopen Codex: {exc}"
    return result
