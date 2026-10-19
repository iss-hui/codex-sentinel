import json

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from codex_sentinel.config import DEFAULT_CONFIG, ConfigManager
from codex_sentinel.gui.main_window import MainWindow
from codex_sentinel.gui.theme import colors
from codex_sentinel.i18n import set_lang
from codex_sentinel.quota_scheduler import TaskItem


@pytest.fixture
def themed_window(tmp_path):
    app = QApplication.instance() or QApplication([])
    set_lang("zh")
    window = MainWindow(
        manager=ConfigManager(tmp_path / "settings"), start_workers=False
    )
    yield app, window
    window.request_quit()
    app.processEvents()


def test_existing_settings_default_to_dark_without_changing_execution_preferences(
    tmp_path,
):
    directory = tmp_path / "settings"
    directory.mkdir()
    saved = {"auto_resume": True, "buffer_seconds": 60, "queue_enabled": False}
    path = directory / "config.json"
    path.write_text(json.dumps(saved), encoding="utf-8")
    loaded = ConfigManager(directory).load()
    assert loaded["theme"] == "dark"
    assert all(loaded[key] == value for key, value in saved.items())
    assert json.loads(path.read_text(encoding="utf-8")) == saved


def test_unknown_theme_is_rejected():
    with pytest.raises(ValueError, match="theme"):
        ConfigManager.validate({**DEFAULT_CONFIG, "theme": "invalid"})


def test_toolbar_theme_persists_without_reloading_forms_or_monitoring(
    themed_window, monkeypatch
):
    app, window = themed_window
    window.switch_page(1)
    window.page_quota.txt_prompt.setPlainText("unsaved planned task")
    window.page_dashboard.txt_prompt.setPlainText("unsaved recovery prompt")
    window.page_settings.spin_poll.setValue(17)
    original = window.settings.copy()
    refreshes = []
    monkeypatch.setattr(
        window.monitor_worker, "refresh", lambda: refreshes.append(True)
    )
    window.theme_button.click()
    app.processEvents()
    assert window.property("effectiveTheme") == "light"
    assert ConfigManager(window.manager.config_dir).load()["theme"] == "light"
    assert {k: v for k, v in window.settings.items() if k != "theme"} == {
        k: v for k, v in original.items() if k != "theme"
    }
    assert not refreshes
    assert window.stacked.currentIndex() == 1
    assert window.page_quota.txt_prompt.toPlainText() == "unsaved planned task"
    assert window.page_dashboard.txt_prompt.toPlainText() == "unsaved recovery prompt"
    assert window.page_settings.spin_poll.value() == 17


def test_settings_theme_also_updates_dialogs_and_log_selection(themed_window):
    app, window = themed_window
    window.page_tasks.detail.setPlainText("selected execution log")
    cursor = window.page_tasks.detail.document().find("execution")
    window.page_tasks.detail.setTextCursor(cursor)
    window.page_settings.cmb_theme.setCurrentIndex(
        window.page_settings.cmb_theme.findData("light")
    )
    window.page_dashboard.btn_details.click()
    app.processEvents()
    dialog = window.page_dashboard.recovery_details
    assert dialog.isVisible()
    assert colors(dialog)["canvas"] == "#f6f6f6"
    assert (
        window.update_dialog.palette().color(QPalette.ColorRole.Base).name()
        == "#ffffff"
    )
    assert window.page_tasks.detail.textCursor().selectedText() == "execution"
    assert window.page_settings.cmb_theme.currentData() == "light"
    assert ConfigManager(window.manager.config_dir).load()["theme"] == "light"
    dialog.close()


def test_system_theme_follows_scheme_without_overwriting_saved_choice(
    themed_window, monkeypatch
):
    _, window = themed_window
    monkeypatch.setattr(
        "codex_sentinel.gui.theme.resolved_theme", lambda choice: "light"
    )
    window._set_theme("system")
    assert window.property("effectiveTheme") == "light"
    monkeypatch.setattr(
        "codex_sentinel.gui.theme.resolved_theme", lambda choice: "dark"
    )
    window._system_theme_changed(Qt.ColorScheme.Dark)
    assert window.property("effectiveTheme") == "dark"
    assert ConfigManager(window.manager.config_dir).load()["theme"] == "system"


def test_migrated_recovery_is_not_mislabelled_as_activation(themed_window):
    _, window = themed_window
    legacy = TaskItem("legacy", "旧版恢复任务", "continue", ".", "", "completed", 1800000000,
                      completed_at=1800000010, kind="resume")
    window.page_dashboard.render_recent([legacy])
    assert "上次恢复" in window.page_dashboard.lbl_recent.text()
    assert "上次激活" not in window.page_dashboard.lbl_recent.text()
    assert legacy.name in window.page_dashboard.lbl_recent.text()
