"""Independent Windows updater; deliberately imports no GUI modules."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath

import psutil


def prepare_package(request: dict) -> Path:
    executable = Path(request["executable"]).resolve(strict=True)
    package = Path(request["package"]).resolve(strict=True)
    kind = request["kind"]
    if kind not in ("folder", "single") or executable.suffix.lower() != ".exe":
        raise ValueError("Invalid installation type")
    if kind == "folder" and (executable.name != "CodexSentinel.exe"
                             or not (executable.parent / "_internal").is_dir()):
        raise ValueError("The desktop installation is incomplete")
    if package.is_relative_to(executable.parent):
        raise ValueError("The update package must be outside the application folder")
    if not re.fullmatch(r"[0-9a-f]{64}", request["sha256"]):
        raise ValueError("Invalid package checksum")
    if package.stat().st_size != request["size"]:
        raise ValueError("Update package size does not match")
    digest = hashlib.sha256()
    with package.open("rb") as stream:
        for chunk in iter(lambda: stream.read(256 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != request["sha256"]:
        raise ValueError("Update package checksum does not match")
    stage = Path(tempfile.mkdtemp(prefix=".sentinel-update-", dir=executable.parent))
    try:
        payload = stage / "payload"
        payload.mkdir()
        if kind == "single":
            shutil.copy2(package, payload / executable.name)
        else:
            with zipfile.ZipFile(package) as archive:
                entries = archive.infolist()
                if len(entries) > 30000 or sum(item.file_size for item in entries) > 2 * 1024**3:
                    raise ValueError("Update archive is too large")
                seen = set()
                for item in entries:
                    path = PurePosixPath(item.filename)
                    parts = path.parts
                    if (not parts or parts[0] != "CodexSentinel" or path.is_absolute()
                            or "\\" in item.filename or ":" in item.filename
                            or any(part in (".", "..") or part.rstrip(" .") != part for part in parts)
                            or stat.S_ISLNK(item.external_attr >> 16)):
                        raise ValueError("Unsafe path in update archive")
                    reserved = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
                                *(f"lpt{i}" for i in range(1, 10))}
                    if any(part.split(".")[0].casefold() in reserved for part in parts):
                        raise ValueError("Reserved Windows path in update archive")
                    relative = parts[1:]
                    if not relative:
                        if item.is_dir():
                            continue
                        raise ValueError("Invalid update archive root")
                    if relative[0] not in ("CodexSentinel.exe", "_internal"):
                        raise ValueError("Unexpected file in update archive")
                    key = "/".join(relative).casefold()
                    if key in seen:
                        raise ValueError("Duplicate path in update archive")
                    seen.add(key)
                    target = payload.joinpath(*relative)
                    if item.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(item) as source, target.open("wb") as destination:
                            shutil.copyfileobj(source, destination)
            if not (payload / "_internal" / "CodexSentinelUpdater.exe").is_file():
                raise ValueError("Update archive is missing its updater")
        with (payload / executable.name).open("rb") as stream:
            if stream.read(2) != b"MZ":
                raise ValueError("Update package has no Windows executable")
        return stage
    except Exception:
        shutil.rmtree(stage)
        raise


def wait_for_parents(parents: list[dict], abort: Path, timeout=90) -> None:
    if not parents:
        raise ValueError("Missing application process")
    processes = []
    for item in parents:
        if type(item["pid"]) is not int or item["pid"] <= 0 or item["pid"] == os.getpid():
            raise ValueError("Invalid application process")
        try:
            process = psutil.Process(item["pid"])
            if abs(process.create_time() - item["created"]) < 0.01:
                processes.append(process)
        except psutil.NoSuchProcess:
            pass
    deadline = time.monotonic() + timeout
    while True:
        if abort.exists():
            raise InterruptedError("Update cancelled")
        alive = []
        for process in processes:
            try:
                if process.is_running() and process.status() != psutil.STATUS_ZOMBIE:
                    alive.append(process)
            except psutil.NoSuchProcess:
                pass
        processes = alive
        if not processes:
            return
        if time.monotonic() >= deadline:
            raise TimeoutError("The application did not exit; its files were kept unchanged")
        time.sleep(0.1)


def install_prepared(stage: Path, executable: Path, kind: str, restart) -> None:
    """Replace only owned files, restoring them if replacement or launch fails."""
    names = [executable.name] + (["_internal"] if kind == "folder" else [])
    backup = stage / "backup"
    backup.mkdir()
    saved, installed = [], []
    try:
        for name in names:
            (executable.parent / name).rename(backup / name)
            saved.append(name)
        for name in names:
            (stage / "payload" / name).rename(executable.parent / name)
            installed.append(name)
        restart(executable)
    except Exception as error:
        try:
            for name in reversed(installed):
                (executable.parent / name).rename(stage / "payload" / name)
            for name in reversed(saved):
                (backup / name).rename(executable.parent / name)
        except OSError as rollback_error:
            raise RuntimeError(f"{error}; rollback failed: {rollback_error}. Backup: {backup}") from error
        shutil.rmtree(stage, ignore_errors=True)
        raise
    # A successful launch commits the update. Unrelated user files stay in place.
    shutil.rmtree(stage, ignore_errors=True)


def restart_application(executable: Path, arguments=()) -> None:
    environment = os.environ.copy()
    environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    if os.name == "nt":
        import ctypes

        ctypes.windll.kernel32.SetDllDirectoryW(None)
    subprocess.Popen([str(executable), *arguments], cwd=executable.parent, env=environment,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    session = args.request.resolve().parent
    stage = None
    parents_exited = False
    request = None
    restart_old = False
    try:
        request = json.loads(args.request.read_text(encoding="utf-8"))
        arguments = request.get("arguments", [])
        if not isinstance(arguments, list) or not all(isinstance(item, str) for item in arguments):
            raise ValueError("Invalid application arguments")
        stage = prepare_package(request)
        (session / "ready").touch()
        wait_for_parents(request["parents"], session / "abort")
        parents_exited = True
        install_prepared(stage, Path(request["executable"]), request["kind"],
                         lambda executable: restart_application(executable, arguments))
        result = {"success": True, "version": request["version"]}
        try:
            Path(request["package"]).unlink(missing_ok=True)
        except OSError:
            pass  # Cache cleanup cannot turn a committed update into a failure.
    except Exception as error:  # noqa: BLE001 - process boundary; record failure for the GUI.
        result = {"success": False, "error": str(error)}
        # Do not restart a process that is still running. Keep failed backups.
        if parents_exited and request and not (stage / "backup").exists():
            restart_old = True
        if stage and not (stage / "backup").exists():
            shutil.rmtree(stage, ignore_errors=True)
    (session / "result.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    if restart_old:
        try:
            restart_application(Path(request["executable"]), arguments)
        except OSError as error:
            result["error"] += f"; could not restart the old version: {error}"
    if request:
        (Path(request["package"]).parent.parent / "last-result.json").write_text(
            json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return 0 if result["success"] else 1
