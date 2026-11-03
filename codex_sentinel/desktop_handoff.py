"""Close identified Codex desktop instances and restore only those instances."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import psutil


def is_codex_desktop(executable):
    path = str(executable or "").replace("\\", "/").lower()
    name = path.rsplit("/", 1)[-1]
    return (
        name in ("chatgpt.exe", "codex.exe")
        and ("/windowsapps/openai.codex_" in path or "/openai/codex/" in path)
        and "/resources/" not in path
        and "/bin/" not in path
    ) or path.endswith(("/codex.app/contents/macos/codex", "/codex-desktop"))


def is_live(proc):
    """判断进程是否仍在运行，而不只是残留的进程对象。

    Windows 上卡在退出中的进程线程数为 0、退出码仍是 STILL_ACTIVE，
    无法挂起或等待，只会返回 AccessDenied；它既不持有会话锁也不会再拉起子进程。
    """
    try:
        return proc.status() != psutil.STATUS_ZOMBIE and proc.num_threads() > 0
    except psutil.NoSuchProcess:
        return False
    except psutil.AccessDenied:
        # 无法确认状态时按存活处理，交给后续关闭流程报出明确错误。
        return True


def desktop_roots():
    candidates = {}
    for proc in psutil.process_iter(["exe", "ppid"]):
        # 残留进程若被当成桌面实例，接管会在挂起时失败，恢复时也会误判桌面仍在运行。
        if is_codex_desktop(proc.info.get("exe")) and is_live(proc):
            candidates[proc.pid] = proc
    return [p for p in candidates.values() if p.info["ppid"] not in candidates]


def terminate_tree(root):
    """Freeze the supervisor before collecting workers to prevent respawning."""
    try:
        root.suspend()
    except psutil.NoSuchProcess:
        return
    children = []
    try:
        children = [p for p in root.children(recursive=True) if is_live(p)]
        root.kill()
        for proc in reversed(children):
            try:
                proc.kill()
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs([root, *children], timeout=5)
        if alive:
            raise RuntimeError(
                "Codex desktop processes did not exit: "
                + ", ".join(str(p.pid) for p in alive)
            )
    finally:
        # On permission/error paths never leave the user's desktop suspended.
        try:
            root.resume()
        except psutil.NoSuchProcess:
            pass


def launch_desktop(executable):
    path = Path(executable)
    if os.name == "nt":
        package = next(
            (p for p in path.parts if p.startswith("OpenAI.Codex_") and "__" in p), None
        )
        command = (
            [
                "explorer.exe",
                "shell:AppsFolder\\OpenAI.Codex_" + package.rsplit("__", 1)[1] + "!App",
            ]
            if package
            else [str(path)]
        )
        subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    else:
        subprocess.Popen(
            [str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )


class DesktopHandoff:
    def __init__(self):
        self.closed_executables = []
        self.closed_pids = []

    def close(self):
        roots = desktop_roots()
        ancestors = {p.pid for p in psutil.Process().parents()} | {os.getpid()}
        if any(p.pid in ancestors for p in roots):
            raise RuntimeError(
                "Sentinel was started by Codex. Start Sentinel separately before taking over the desktop."
            )
        for root in roots:
            executable = root.info.get("exe")
            if not executable:
                try:
                    executable = root.exe()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            # Remember before closing so partial failures still restore the app.
            if executable and executable not in self.closed_executables:
                self.closed_executables.append(executable)
            self.closed_pids.append(root.pid)
            try:
                terminate_tree(root)
            except Exception as exc:
                # psutil 异常的文本只有 "(pid=N)"，补上进程路径和异常类型便于排查。
                raise RuntimeError(
                    f"Could not close Codex desktop process {root.pid} "
                    f"({executable or 'unknown path'}): {type(exc).__name__} {exc}"
                ) from exc
        return bool(roots)

    def reopen(self):
        running = set()
        for p in desktop_roots():
            exe = p.info.get("exe")
            if not exe:
                try:
                    exe = p.exe()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            if exe:
                running.add(exe)
        for executable in self.closed_executables:
            if executable not in running:
                launch_desktop(executable)
