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


def desktop_roots():
    candidates = {}
    for proc in psutil.process_iter(["exe", "ppid"]):
        if is_codex_desktop(proc.info.get("exe")):
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
        children = root.children(recursive=True)
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
            terminate_tree(root)
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
