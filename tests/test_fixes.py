import json
import time
from pathlib import Path
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox

from codex_sentinel.detector import parse_session_file
from codex_sentinel.gui.common import populate_sessions
from codex_sentinel.gui.pages.quota_timer import QuotaTimerPage
from codex_sentinel.gui.pages.task_queue import TaskQueuePage
from codex_sentinel.gui.tray_icon import SentinelTrayIcon
from codex_sentinel.quota_scheduler import QuotaScheduler
from codex_sentinel.session_catalog import _timestamp


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_detector_handles_string_error(tmp_path: Path):
    file = tmp_path / "str_error_session.jsonl"
    future_reset = time.time() + 1800
    lines = [
        json.dumps({"type": "session_meta", "payload": {"id": "test-str-err", "cwd": "/work"}}),
        json.dumps({"type": "turn_context", "payload": {"model": "gpt-5"}}),
        json.dumps({
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "rate_limits": {
                    "primary": {
                        "used_percent": 100.0,
                        "resets_at": future_reset,
                    }
                },
            },
        }),
        json.dumps({
            "type": "event_msg",
            "payload": {
                "type": "task_complete",
                "error": "You hit the usage limit. Try again later.",
            },
        }),
    ]
    file.write_text("\n".join(lines), encoding="utf-8")
    result = parse_session_file(file)
    assert result is not None
    assert result["session_id"] == "test-str-err"
    assert "usage limit" in result["error_msg"].lower()


def test_quota_scheduler_get_missing_raises_key_error(tmp_path: Path):
    sched = QuotaScheduler(tmp_path)
    with pytest.raises(KeyError):
        sched.get("non-existent-task-id")


def test_session_catalog_timestamp_iso_and_fallback():
    assert _timestamp({"ts": "2026-10-03T12:00:00Z"}, "ts") > 0
    assert _timestamp({"ts_ms": 1700000000000}, "ts") == 1700000000.0
    assert _timestamp({"ts": 1700000000}, "ts") == 1700000000.0
    assert _timestamp({}, "ts", fallback=42.0) == 42.0
    assert _timestamp({"ts": "invalid-time"}, "ts", fallback=99.0) == 99.0


def test_combo_folder_heading_unselectable(app):
    from PySide6.QtWidgets import QStyleFactory

    combo = QComboBox()
    fusion = QStyleFactory.create("Fusion")
    if fusion:
        combo.setStyle(fusion)
    populate_sessions(combo, [
        {"session_id": "s1", "title": "Session 1", "cwd": "/project/a"},
        {"session_id": "s2", "title": "Session 2", "cwd": "/project/b"},
    ])
    # Heading items (index 1 and index 3) must have NoItemFlags
    assert combo.model().item(1).flags() == Qt.ItemFlag.NoItemFlags
    assert not (combo.model().item(1).flags() & Qt.ItemFlag.ItemIsSelectable)
    assert not (combo.model().item(1).flags() & Qt.ItemFlag.ItemIsEnabled)
    assert combo.model().item(3).flags() == Qt.ItemFlag.NoItemFlags
    assert not (combo.model().item(3).flags() & Qt.ItemFlag.ItemIsSelectable)
    assert not (combo.model().item(3).flags() & Qt.ItemFlag.ItemIsEnabled)
    combo.setCurrentIndex(combo.findData("s1"))
    QTest.keyClick(combo, Qt.Key.Key_Down)
    assert combo.currentData() == "s2"


def test_quota_timer_saved_with_none_scheduled_at(app):
    page = QuotaTimerPage()
    sched = QuotaScheduler()
    task = sched.add_task("name", "prompt", str(Path.cwd()), scheduled_at=None)
    page.saved(task)
    assert "—" in page.lbl_summary.text()


def test_task_queue_show_detail_preserves_scroll(app):
    page = TaskQueuePage()
    sched = QuotaScheduler()
    task = sched.add_task("name", "prompt", str(Path.cwd()))
    page.refresh_table([task])
    page.table.selectRow(0)
    page.show_detail()
    orig_text = page.detail.toPlainText()
    # Calling show_detail again with same text should no-op
    page.show_detail()
    assert page.detail.toPlainText() == orig_text


def test_tray_icon_single_click_and_state(app):
    tray = SentinelTrayIcon()
    activated_reasons = []
    tray.show_dashboard_requested.connect(lambda: activated_reasons.append("show"))
    tray._on_activated(tray.ActivationReason.Trigger)
    assert "show" in activated_reasons
    tray.set_state("limited")
    assert "Codex Sentinel" in tray.toolTip()
    assert "限额" in tray.toolTip() or "Rate" in tray.toolTip()


@pytest.mark.parametrize("row, expected", [
    ({"ts": "1700000000"}, 1700000000.0),
    ({"ts_ms": "1700000000000"}, 1700000000.0),
    ({"ts_ms": "nan", "ts": 42}, 42.0),
    ({"ts": float("inf")}, 99.0),
    ({"ts": -1e100}, 99.0),
])
def test_timestamp_numeric_strings_and_invalid_values(row, expected):
    assert _timestamp(row, "ts", fallback=99) == expected


def test_log_update_preserves_selected_text(app, tmp_path):
    page = TaskQueuePage()
    log = tmp_path / "run.log"
    log.write_text("Selected log text\n", encoding="utf-8")
    task = QuotaScheduler().add_task("test", "prompt", str(tmp_path), log_file=str(log))
    page.refresh_table([task])
    page.table.selectRow(0)
    cursor = page.detail.document().find("Selected log text")
    page.detail.setTextCursor(cursor)
    with log.open("a", encoding="utf-8") as stream:
        stream.write("New output\n")
    page.show_detail()
    assert page.detail.textCursor().selectedText() == "Selected log text"
    cursor.clearSelection()
    page.detail.setTextCursor(cursor)
    page.show_detail()
    assert "New output" in page.detail.toPlainText()


def test_long_multiline_log_keeps_target_header(app, tmp_path):
    page = TaskQueuePage()
    log = tmp_path / "run.log"
    log.write_text("output\n" * 1200, encoding="utf-8")
    task = QuotaScheduler().add_task("test", "prompt", str(tmp_path),
                                   session_id="target-id", log_file=str(log))
    page.refresh_table([task])
    page.table.selectRow(0)
    assert "target-id" in page.detail.toPlainText()
    cursor = page.detail.document().find("target-id")
    page.detail.setTextCursor(cursor)
    page.refresh_table([task])
    assert page.detail.textCursor().selectedText() == "target-id"


def test_unchanged_windows_log_does_not_reset_document(app, tmp_path):
    page = TaskQueuePage()
    log = tmp_path / "run.log"
    log.write_bytes(b"line one\r\nline two\r\n")
    task = QuotaScheduler().add_task("test", "prompt", str(tmp_path), log_file=str(log))
    page.refresh_table([task])
    page.table.selectRow(0)
    changes = []
    page.detail.document().contentsChanged.connect(lambda: changes.append(True))
    page.show_detail()
    assert not changes


def test_log_scroll_follows_bottom_but_keeps_reading_position(app, tmp_path):
    page = TaskQueuePage()
    page.resize(800, 600)
    page.show()
    try:
        log = tmp_path / "run.log"
        log.write_text("output\n" * 150, encoding="utf-8")
        scheduler = QuotaScheduler()
        first = scheduler.add_task("first", "prompt", str(tmp_path), log_file=str(log))
        second = scheduler.add_task("second", "prompt", str(tmp_path), log_file=str(log))
        page.refresh_table([first, second])
        page.table.selectRow(0)
        app.processEvents()
        scrollbar = page.detail.verticalScrollBar()
        assert scrollbar.maximum() > 20
        scrollbar.setValue(10)
        reading_position = scrollbar.value()
        reading_block = page.detail.firstVisibleBlock().blockNumber()
        with log.open("a", encoding="utf-8") as stream:
            stream.write("new\n" * 5)
        page.show_detail()
        assert scrollbar.value() == reading_position
        assert page.detail.firstVisibleBlock().blockNumber() == reading_block
        scrollbar.setValue(scrollbar.maximum())
        with log.open("a", encoding="utf-8") as stream:
            stream.write("new\n" * 5)
        page.show_detail()
        assert scrollbar.value() == scrollbar.maximum()
        page.table.selectRow(1)
        assert scrollbar.value() == 0
        assert page.detail.textCursor().position() == 0
    finally:
        page.close()


@pytest.mark.parametrize("selected, expected", [("selected", 2000), ("", 1500)])
def test_next_reset_uses_selected_conversation_bucket(app, tmp_path, monkeypatch,
                                                     selected, expected):
    monkeypatch.setattr("codex_sentinel.gui.pages.quota_timer.time.time", lambda: 1000)
    page = QuotaTimerPage()
    page.on_snapshot({
        "sessions": [{"session_id": "selected", "title": "Selected", "model": "m",
                      "cwd": str(tmp_path), "limits": {"limit_id": "selected-bucket"}}],
        "models": [{"slug": "m"}],
        "buckets": {
            "unrelated": {"primary": {"window_minutes": 300, "resets_at": 1500}},
            "selected-bucket": {"primary": {"window_minutes": 300, "resets_at": 2000}},
        },
    })
    page.cmb_session.setCurrentIndex(page.cmb_session.findData(selected))
    page.cmb_schedule.setCurrentIndex(page.cmb_schedule.findData("next"))
    submitted = []
    page.task_requested.connect(submitted.append)
    page.submit()
    assert submitted[0]["scheduled_at"] == expected
