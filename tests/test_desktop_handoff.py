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
    root = SimpleNamespace(pid=100, info={"exe": exe, "ppid": 1})
    renderer = SimpleNamespace(pid=101, info={"exe": exe, "ppid": 100})
    other = SimpleNamespace(pid=102, info={"exe": r"C:\Other\ChatGPT.exe", "ppid": 1})
    monkeypatch.setattr(
        "codex_sentinel.desktop_handoff.psutil.process_iter",
        lambda attrs: [root, renderer, other],
    )
    assert desktop_roots() == [root]


def test_handoff_never_kills_its_own_ancestor(monkeypatch):
    import psutil

    ancestor = psutil.Process().parent()
    monkeypatch.setattr(
        "codex_sentinel.desktop_handoff.desktop_roots", lambda: [ancestor]
    )
    monkeypatch.setattr(
        "codex_sentinel.desktop_handoff.terminate_tree",
        lambda _: pytest.fail("must not kill ancestor"),
    )
    with pytest.raises(RuntimeError, match="separately"):
        DesktopHandoff().close()
