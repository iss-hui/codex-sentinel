"""GitHub Release discovery, verified downloads, and updater handoff."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from urllib.request import Request, urlopen
from uuid import uuid4

import psutil

from codex_sentinel import __version__
from codex_sentinel.config import write_json

REPOSITORY = "iss-hui/codex-sentinel"
RELEASES_URL = f"https://github.com/{REPOSITORY}/releases"
LATEST_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
MAX_PACKAGE_SIZE = 1024 * 1024 * 1024


@dataclass(frozen=True)
class Release:
    version: str
    notes: str
    url: str
    asset_name: str
    download_url: str
    size: int
    sha256: str
    kind: str


@dataclass(frozen=True)
class Download:
    release: Release
    package: Path


def version_tuple(version: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", version)
    if not match:
        raise ValueError(f"Invalid release version: {version}")
    return tuple(int(part) for part in match.groups())


def installation_kind() -> str | None:
    if (not getattr(sys, "frozen", False) or sys.platform != "win32"
            or platform.machine().lower() not in ("amd64", "x86_64")):
        return None
    executable = Path(sys.executable)
    if executable.name == "CodexSentinel.exe" and (executable.parent / "_internal").is_dir():
        return "folder"
    return "single"


def _open(url: str):
    request = Request(url, headers={
        "User-Agent": f"CodexSentinel/{__version__}",
        "Accept": "application/vnd.github+json" if url == LATEST_URL else "application/octet-stream",
    })
    return urlopen(request, timeout=15)


def _read_metadata(url: str) -> bytes:
    with _open(url) as response:
        data = response.read(2 * 1024 * 1024 + 1)
    if len(data) > 2 * 1024 * 1024:
        raise ValueError("Release metadata is too large")
    return data


def check_for_update(kind: str = "folder", current: str = __version__) -> Release | None:
    metadata = json.loads(_read_metadata(LATEST_URL))
    tag = metadata["tag_name"]
    if metadata.get("draft") or metadata.get("prerelease"):
        return None
    if version_tuple(tag) <= version_tuple(current):
        return None
    if kind not in ("folder", "single"):
        raise ValueError("Unsupported update package")
    name = (f"CodexSentinel-windows-x64-{tag}.zip" if kind == "folder"
            else f"codex-sentinel-windows-x64-{tag}.exe")
    assets = metadata.get("assets", [])
    asset = next((item for item in assets if item["name"] == name), None)
    if asset is None:
        raise ValueError(f"Release has no Windows package: {name}")
    prefix = f"{RELEASES_URL}/download/{tag}/"
    if asset.get("browser_download_url") != prefix + name:
        raise ValueError("Unexpected release download URL")
    size = asset.get("size", 0)
    if type(size) is not int or not 0 < size <= MAX_PACKAGE_SIZE:
        raise ValueError("Invalid update package size")
    digest = asset.get("digest") or ""
    if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
        checksums = next((item for item in assets if item["name"] == "SHA256SUMS.txt"), None)
        if not checksums or checksums.get("browser_download_url") != prefix + "SHA256SUMS.txt":
            raise ValueError("Release is missing the SHA-256 checksum")
        digest = ""
        for line in _read_metadata(checksums["browser_download_url"]).decode("utf-8").splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].lstrip("*") == name:
                digest = "sha256:" + parts[0]
                break
        if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
            raise ValueError("Release is missing the package checksum")
    return Release(tag.lstrip("v"), str(metadata.get("body") or ""),
                   f"{RELEASES_URL}/tag/{tag}", name, prefix + name, size,
                   digest[7:].lower(), kind)


def download_release(release: Release, directory: Path, cancel: Event, progress) -> Download:
    session = directory / "updates" / uuid4().hex
    session.mkdir(parents=True)
    package = session / release.asset_name
    partial = package.with_suffix(package.suffix + ".part")
    digest = hashlib.sha256()
    received = 0
    try:
        with _open(release.download_url) as response, partial.open("wb") as stream:
            while True:
                if cancel.is_set():
                    raise InterruptedError("Download cancelled")
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                received += len(chunk)
                if received > release.size:
                    raise ValueError("Update download exceeds the expected size")
                stream.write(chunk)
                digest.update(chunk)
                progress(received, release.size)
        if received != release.size or digest.hexdigest() != release.sha256:
            raise ValueError("Update package checksum or size does not match")
        if cancel.is_set():
            raise InterruptedError("Download cancelled")
        partial.replace(package)
        return Download(release, package)
    finally:
        partial.unlink(missing_ok=True)


def _parent_processes() -> list[dict]:
    process = psutil.Process()
    parents = [{"pid": process.pid, "created": process.create_time()}]
    # A one-file PyInstaller app also has a bootloader holding the EXE open.
    parent = process.parent()
    if parent and Path(parent.exe()).resolve() == Path(sys.executable).resolve():
        parents.append({"pid": parent.pid, "created": parent.create_time()})
    return parents


def launch_updater(download: Download, cancel: Event) -> None:
    if installation_kind() != download.release.kind:
        raise ValueError("This installation cannot apply the downloaded package")
    # Every attempt gets fresh readiness/abort markers, including after a retry.
    session = download.package.parent.resolve() / ("apply-" + uuid4().hex)
    session.mkdir()
    executable = Path(sys.executable).resolve()
    if session.is_relative_to(executable.parent):
        raise ValueError("The update cache must be outside the application folder")
    helper = Path(sys._MEIPASS) / "CodexSentinelUpdater.exe"
    cached_helper = session / helper.name
    shutil.copy2(helper, cached_helper)
    request = session / "request.json"
    write_json(request, {
        "executable": str(executable), "kind": download.release.kind,
        "package": str(download.package.resolve()), "sha256": download.release.sha256,
        "size": download.release.size, "parents": _parent_processes(),
        "version": download.release.version,
        "arguments": list(sys.argv[1:]),
    })
    environment = os.environ.copy()
    environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    # The helper has its own runtime and must outlive the GUI's extracted files.
    import ctypes

    ctypes.windll.kernel32.SetDllDirectoryW(None)
    try:
        process = subprocess.Popen(
            [str(cached_helper), "--request", str(request)], cwd=session,
            env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    finally:
        ctypes.windll.kernel32.SetDllDirectoryW(str(sys._MEIPASS))
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if cancel.is_set():
            (session / "abort").touch()
            raise InterruptedError("Update cancelled")
        if (session / "ready").exists():
            return
        if process.poll() is not None:
            result = session / "result.json"
            message = json.loads(result.read_text("utf-8")).get("error") if result.exists() else None
            raise RuntimeError(message or "The updater could not start")
        time.sleep(0.1)
    (session / "abort").touch()
    raise TimeoutError("The updater did not become ready; the application was kept running")
