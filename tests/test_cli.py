import sys

import pytest

from codex_sentinel.cli import main


def test_gui_receives_cli_overrides_and_dry_run(monkeypatch):
    captured = {}

    def fake_gui(**kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr("codex_sentinel.gui.app.main", fake_gui)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "codex-sentinel",
            "--gui",
            "--buffer",
            "60",
            "--prompt",
            "hello",
            "--lang",
            "zh",
            "--dry-run",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    assert captured == {
        "overrides": {"buffer_seconds": 60, "resume_prompt": "hello", "language": "zh"},
        "dry_run": True,
    }


def test_gui_failure_does_not_fallback_to_daemon(monkeypatch):
    def fail(**kwargs):
        raise RuntimeError("GUI broken")

    monkeypatch.setattr("codex_sentinel.gui.app.main", fail)
    monkeypatch.setattr(
        "codex_sentinel.cli.run_daemon",
        lambda **kwargs: pytest.fail("must not fallback"),
    )
    monkeypatch.setattr(sys, "argv", ["codex-sentinel"])
    with pytest.raises(RuntimeError, match="GUI broken"):
        main()
