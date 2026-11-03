from types import SimpleNamespace

import pytest

from codex_sentinel.desktop_handoff import (
    DesktopHandoff,
    desktop_roots,
    is_codex_desktop,
)


def test_desktop_identification_excludes_cli_sentinel_and_other_chatgpt():
    assert is_codex_desktop(
        r"C:\Program Files\WindowsApps\OpenAI.Codex_26.928_x64__publisher\app\ChatGPT.exe"
    )
    assert is_codex_desktop(
        r"C:\Users\me\AppData\Local\Programs\OpenAI\Codex\Codex.exe"
    )
    for path in (
        r"C:\Users\me\AppData\Local\OpenAI\Codex\bin\version\codex.exe",
        r"C:\Program Files\WindowsApps\OpenAI.Codex_26.928_x64__publisher\app\resources\codex.exe",
        r"C:\Program Files\ChatGPT\ChatGPT.exe",
        r"D:\CodexSentinel.exe",
    ):
        assert not is_codex_desktop(path)


def test_only_supervisor_roots_are_selected(monkeypatch):
    exe = r"C:\Program Files\WindowsApps\OpenAI.Codex_26.928_x64__publisher\app\ChatGPT.exe"
    live = {"status": lambda: "running", "num_threads": lambda: 4}
    root = SimpleNamespace(pid=100, info={"exe": exe, "ppid": 1}, **live)
    renderer = SimpleNamespace(pid=101, info={"exe": exe, "ppid": 100}, **live)
    other = SimpleNamespace(pid=102, info={"exe": r"C:\Other\ChatGPT.exe", "ppid": 1}, **live)
    monkeypatch.setattr(
        "codex_sentinel.desktop_handoff.psutil.process_iter",
        lambda attrs: [root, renderer, other],
    )
    assert desktop_roots() == [root]


def test_handoff_never_kills_its_own_ancestor(monkeypatch):
    import os
    import psutil

    ancestor = SimpleNamespace(pid=os.getpid(), info={"exe": "codex.exe"})
    monkeypatch.setattr(
        "codex_sentinel.desktop_handoff.desktop_roots", lambda: [ancestor]
    )
    monkeypatch.setattr(
        "codex_sentinel.desktop_handoff.terminate_tree",
        lambda _: pytest.fail("must not kill ancestor"),
    )
    with pytest.raises(RuntimeError, match="separately"):
        DesktopHandoff().close()


def test_handoff_uses_enumerated_path_when_process_query_is_denied(monkeypatch):
    import psutil

    executable = r"C:\Users\me\AppData\Local\OpenAI\Codex\Codex.exe"

    def denied():
        raise psutil.AccessDenied(100)

    root = SimpleNamespace(pid=100, info={"exe": executable}, exe=denied)
    monkeypatch.setattr("codex_sentinel.desktop_handoff.desktop_roots", lambda: [root])
    monkeypatch.setattr("codex_sentinel.desktop_handoff.psutil.Process",
                        lambda: SimpleNamespace(parents=lambda: []))
    killed, launched = [], []
    monkeypatch.setattr("codex_sentinel.desktop_handoff.terminate_tree", killed.append)
    monkeypatch.setattr("codex_sentinel.desktop_handoff.launch_desktop", launched.append)
    handoff = DesktopHandoff()
    assert handoff.close()
    assert killed == [root]
    handoff.reopen()
    assert launched == []  # An already restarted desktop must not be duplicated.
    monkeypatch.setattr("codex_sentinel.desktop_handoff.desktop_roots", lambda: [])
    handoff.reopen()
    assert launched == [executable]


def test_process_stuck_in_termination_is_not_a_desktop_instance(monkeypatch):
    import psutil

    # 对应实际故障：残留的 ChatGPT.exe 线程数为 0，挂起它只会得到 AccessDenied。
    exe = r"C:\Program Files\WindowsApps\OpenAI.Codex_26.1027_x64__publisher\app\ChatGPT.exe"

    def denied():
        raise psutil.AccessDenied(1844)

    stuck = SimpleNamespace(pid=1844, info={"exe": exe, "ppid": 48436},
                            status=lambda: "stopped", num_threads=lambda: 0, suspend=denied)
    live = SimpleNamespace(pid=104464, info={"exe": exe, "ppid": 3432},
                           status=lambda: "running", num_threads=lambda: 60)
    monkeypatch.setattr("codex_sentinel.desktop_handoff.psutil.process_iter",
                        lambda attrs: [stuck, live])
    assert desktop_roots() == [live]

    # 关闭真实桌面后只剩残留进程时，仍需重新拉起桌面。
    monkeypatch.setattr("codex_sentinel.desktop_handoff.psutil.process_iter",
                        lambda attrs: [stuck])
    launched = []
    monkeypatch.setattr("codex_sentinel.desktop_handoff.launch_desktop", launched.append)
    handoff = DesktopHandoff()
    handoff.closed_executables.append(exe)
    handoff.reopen()
    assert launched == [exe]


def test_close_failure_names_the_desktop_process(monkeypatch):
    import psutil

    executable = r"C:\Program Files\WindowsApps\OpenAI.Codex_26.1027_x64__publisher\app\ChatGPT.exe"
    root = SimpleNamespace(pid=1844, info={"exe": executable})
    monkeypatch.setattr("codex_sentinel.desktop_handoff.desktop_roots", lambda: [root])
    monkeypatch.setattr("codex_sentinel.desktop_handoff.psutil.Process",
                        lambda: SimpleNamespace(parents=lambda: []))

    def denied(_):
        raise psutil.AccessDenied(1844)

    monkeypatch.setattr("codex_sentinel.desktop_handoff.terminate_tree", denied)
    handoff = DesktopHandoff()
    with pytest.raises(RuntimeError, match=r"process 1844 \(.*ChatGPT\.exe\): AccessDenied"):
        handoff.close()
    assert handoff.closed_executables == [executable]  # 失败后仍会尝试恢复桌面。
