"""Release discovery and real filesystem update transactions, without network."""

import hashlib
import io
import json
import os
import stat
import sys
import zipfile
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import psutil
import pytest

from codex_sentinel import updater, updates


def release_metadata(kind="folder", version="2.0.9"):
    tag = f"v{version}"
    name = (f"CodexSentinel-windows-x64-{tag}.zip" if kind == "folder"
            else f"codex-sentinel-windows-x64-{tag}.exe")
    return {"tag_name": tag, "body": "Release notes", "assets": [{
        "name": name, "size": 8, "digest": "sha256:" + "a" * 64,
        "browser_download_url": f"{updates.RELEASES_URL}/download/{tag}/{name}",
    }]}


@pytest.mark.parametrize("kind", ["folder", "single"])
def test_release_selects_exact_package_and_compares_numeric_versions(monkeypatch, kind):
    metadata = release_metadata(kind, "2.0.10")
    monkeypatch.setattr(updates, "_read_metadata", lambda _: json.dumps(metadata).encode())
    release = updates.check_for_update(kind, current="2.0.9")
    assert release.version == "2.0.10"
    assert release.kind == kind
    assert release.sha256 == "a" * 64
    assert updates.check_for_update(kind, current="2.0.10") is None
    assert updates.check_for_update(kind, current="2.1.0") is None
    metadata["prerelease"] = True
    assert updates.check_for_update(kind, current="2.0.8") is None


def test_checksum_fallback_and_reject_untrusted_asset_url(monkeypatch):
    metadata = release_metadata()
    metadata["assets"][0]["digest"] = None
    checksum_url = f"{updates.RELEASES_URL}/download/v2.0.9/SHA256SUMS.txt"
    metadata["assets"].append({"name": "SHA256SUMS.txt", "browser_download_url": checksum_url})
    def read(url):
        if url == updates.LATEST_URL:
            return json.dumps(metadata).encode()
        assert url == checksum_url
        return ("b" * 64 + "  " + metadata["assets"][0]["name"] + "\n").encode()
    monkeypatch.setattr(updates, "_read_metadata", read)
    assert updates.check_for_update(current="2.0.8").sha256 == "b" * 64
    metadata["assets"][0]["browser_download_url"] = "https://example.com/app.exe"
    with pytest.raises(ValueError, match="URL"):
        updates.check_for_update(current="2.0.8")


def test_missing_checksum_blocks_download(monkeypatch):
    metadata = release_metadata()
    metadata["assets"][0]["digest"] = None
    monkeypatch.setattr(updates, "_read_metadata", lambda _: json.dumps(metadata).encode())
    with pytest.raises(ValueError, match="checksum"):
        updates.check_for_update(current="2.0.8")


def test_verified_download_progress_cancellation_and_corruption(tmp_path, monkeypatch):
    data = b"MZ" + b"test" * 100000
    release = updates.Release("2.0.9", "notes", updates.RELEASES_URL, "app.exe", "https://unused",
                              len(data), hashlib.sha256(data).hexdigest(), "single")
    monkeypatch.setattr(updates, "_open", lambda _: io.BytesIO(data))
    progress = []
    download = updates.download_release(release, tmp_path, Event(), lambda *args: progress.append(args))
    assert download.package.read_bytes() == data
    assert progress[-1] == (len(data), len(data))
    cancelled = Event()
    def cancel(*_):
        cancelled.set()
    with pytest.raises(InterruptedError):
        updates.download_release(release, tmp_path, cancelled, cancel)
    monkeypatch.setattr(updates, "_open", lambda _: io.BytesIO(b"corrupt"))
    with pytest.raises(ValueError, match="checksum or size"):
        updates.download_release(release, tmp_path, Event(), lambda *_: None)
    assert list(tmp_path.rglob("*.part")) == []
    assert len(list(tmp_path.rglob("app.exe"))) == 1


def make_package(tmp_path, kind="folder", extras=()):
    install = tmp_path / "portable app"
    install.mkdir()
    executable = install / ("CodexSentinel.exe" if kind == "folder" else "renamed sentinel.exe")
    executable.write_bytes(b"MZold")
    (install / "user notes.txt").write_text("keep", encoding="utf-8")
    cache = tmp_path / "cache"
    cache.mkdir()
    package = cache / ("update.zip" if kind == "folder" else "update.exe")
    if kind == "folder":
        (install / "_internal").mkdir()
        (install / "_internal" / "old.dll").write_bytes(b"old")
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("CodexSentinel/CodexSentinel.exe", b"MZnew")
            archive.writestr("CodexSentinel/_internal/new.dll", b"new")
            archive.writestr("CodexSentinel/_internal/CodexSentinelUpdater.exe", b"MZhelper")
            for name, content in extras:
                archive.writestr(name, content)
    else:
        package.write_bytes(b"MZnew")
    return {"executable": str(executable), "package": str(package), "kind": kind,
            "size": package.stat().st_size, "sha256": hashlib.sha256(package.read_bytes()).hexdigest()}


@pytest.mark.parametrize("kind", ["folder", "single"])
def test_update_replaces_owned_files_and_preserves_user_data(tmp_path, kind):
    request = make_package(tmp_path, kind)
    executable = Path(request["executable"])
    stage = updater.prepare_package(request)
    assert executable.read_bytes() == b"MZold"
    launches = []
    updater.install_prepared(stage, executable, kind, launches.append)
    assert executable.read_bytes() == b"MZnew"
    assert launches == [executable]
    assert (executable.parent / "user notes.txt").read_text("utf-8") == "keep"
    if kind == "folder":
        assert not (executable.parent / "_internal" / "old.dll").exists()
        assert (executable.parent / "_internal" / "new.dll").read_bytes() == b"new"
    assert not stage.exists()


@pytest.mark.parametrize("failure", ["backup", "install", "restart"])
def test_failure_restores_complete_old_installation(tmp_path, monkeypatch, failure):
    request = make_package(tmp_path)
    stage = updater.prepare_package(request)
    executable = Path(request["executable"])
    rename = Path.rename
    def failing_rename(path, target):
        if failure == "backup" and path == executable.parent / "_internal":
            raise PermissionError("locked library")
        if failure == "install" and path == stage / "payload" / "_internal":
            raise OSError("disk error")
        return rename(path, target)
    monkeypatch.setattr(Path, "rename", failing_rename)
    def restart(_):
        if failure == "restart":
            raise OSError("cannot launch")
    with pytest.raises(OSError):
        updater.install_prepared(stage, executable, "folder", restart)
    assert executable.read_bytes() == b"MZold"
    assert (executable.parent / "_internal" / "old.dll").read_bytes() == b"old"
    assert not (executable.parent / "_internal" / "new.dll").exists()
    assert not stage.exists()


@pytest.mark.parametrize("name", [
    "CodexSentinel/../../escape.exe", "CodexSentinel/_internal/../../escape.exe",
    "C:/escape.exe", "CodexSentinel/_internal/foo:stream", "CodexSentinel\\escape.exe",
    "CodexSentinel/_internal/NUL.txt", "CodexSentinel/_internal/trailing. ",
    "CodexSentinel/user notes.txt", "CodexSentinel/_internal/NEW.dll",
])
def test_unsafe_archive_never_changes_the_installation(tmp_path, name):
    request = make_package(tmp_path, extras=[(name, b"unsafe")])
    with pytest.raises(ValueError):
        updater.prepare_package(request)
    assert Path(request["executable"]).read_bytes() == b"MZold"
    assert not (tmp_path / "escape.exe").exists()
    assert not list(Path(request["executable"]).parent.glob(".sentinel-update-*"))


def test_symlink_archive_is_rejected(tmp_path):
    entry = zipfile.ZipInfo("CodexSentinel/_internal/link")
    entry.external_attr = (stat.S_IFLNK | 0o777) << 16
    request = make_package(tmp_path, extras=[(entry, "../../outside")])
    with pytest.raises(ValueError, match="Unsafe"):
        updater.prepare_package(request)


def test_updater_rechecks_download_hash(tmp_path):
    request = make_package(tmp_path)
    package = Path(request["package"])
    data = package.read_bytes()
    package.write_bytes(b"X" + data[1:])
    with pytest.raises(ValueError, match="checksum"):
        updater.prepare_package(request)
    assert Path(request["executable"]).read_bytes() == b"MZold"


def test_parent_wait_timeout_and_abort_never_kill_application(tmp_path):
    child = psutil.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        parents = [{"pid": child.pid, "created": child.create_time()}]
        abort = tmp_path / "abort"
        with pytest.raises(TimeoutError):
            updater.wait_for_parents(parents, abort, timeout=0)
        assert child.is_running()
        abort.touch()
        with pytest.raises(InterruptedError):
            updater.wait_for_parents(parents, abort)
        assert child.is_running()
        abort.unlink()
        child.terminate()
        child.wait(5)
        updater.wait_for_parents(parents, abort)
    finally:
        if child.is_running():
            child.kill()
            child.wait(5)


def test_updater_main_restarts_old_version_and_records_error(tmp_path, monkeypatch):
    request = make_package(tmp_path)
    request.update(version="2.0.9", arguments=["--gui", "--dry-run"],
                   parents=[{"pid": os.getpid(), "created": psutil.Process().create_time()}])
    request_file = Path(request["package"]).parent / "request.json"
    request_file.write_text(json.dumps(request), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["updater", "--request", str(request_file)])
    monkeypatch.setattr(updater, "wait_for_parents", lambda *_: None)
    launches = []
    def restart(executable, arguments=()):
        assert arguments == ["--gui", "--dry-run"]
        launches.append(executable.read_bytes())
        if len(launches) == 1:
            raise OSError("cannot start new version")
    monkeypatch.setattr(updater, "restart_application", restart)
    assert updater.main() == 1
    assert launches == [b"MZnew", b"MZold"]
    result = json.loads((request_file.parent / "result.json").read_text("utf-8"))
    assert not result["success"] and "cannot start" in result["error"]


def test_handoff_uses_independent_runtime_and_fresh_markers_on_retry(tmp_path, monkeypatch):
    import ctypes

    request = make_package(tmp_path, "single")
    package = Path(request["package"])
    helper_dir = tmp_path / "bundled helper"
    helper_dir.mkdir()
    (helper_dir / "CodexSentinelUpdater.exe").write_bytes(b"MZhelper")
    release = updates.Release("2.0.9", "", updates.RELEASES_URL, package.name, "", request["size"], request["sha256"], "single")
    monkeypatch.setattr(updates, "installation_kind", lambda: "single")
    monkeypatch.setattr(sys, "executable", request["executable"])
    monkeypatch.setattr(sys, "_MEIPASS", str(helper_dir), raising=False)
    monkeypatch.setattr(sys, "argv", [request["executable"], "--gui", "--dry-run"])
    monkeypatch.setattr(updates, "_parent_processes", lambda: [{"pid": 123, "created": 1.0}])
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(kernel32=SimpleNamespace(SetDllDirectoryW=lambda _: None)), raising=False)
    monkeypatch.setattr(updates.subprocess, "CREATE_NO_WINDOW", 0x8000000, raising=False)
    monkeypatch.setattr(updates.subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200, raising=False)
    launches = []
    def launch(command, **options):
        launches.append((command, options))
        (options["cwd"] / "ready").touch()
        return SimpleNamespace(poll=lambda: None)
    monkeypatch.setattr(updates.subprocess, "Popen", launch)
    download = updates.Download(release, package)
    updates.launch_updater(download, Event())
    updates.launch_updater(download, Event())
    assert len(launches) == 2
    assert launches[0][1]["cwd"] != launches[1][1]["cwd"]
    for command, options in launches:
        assert options["env"]["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
        assert Path(command[0]).read_bytes() == b"MZhelper"
        assert not Path(command[0]).is_relative_to(Path(request["executable"]).parent)
        handed_off = json.loads(Path(command[2]).read_text("utf-8"))
        assert handed_off["parents"] == [{"pid": 123, "created": 1.0}]
        assert handed_off["arguments"] == ["--gui", "--dry-run"]
