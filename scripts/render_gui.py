"""Render all desktop pages with synthetic, offline data for visual QA."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from codex_sentinel.config import ConfigManager
from codex_sentinel.gui.app import DARK_STYLESHEET
from codex_sentinel.gui.main_window import MainWindow
from codex_sentinel.i18n import set_lang

output = Path(sys.argv[1] if len(sys.argv) > 1 else ".test-artifacts/screens")
output.mkdir(parents=True, exist_ok=True)
os.environ["CODEX_HOME"] = str(output / "codex")
os.environ["CODEX_SENTINEL_HOME"] = str(output / "sentinel")
app = QApplication([])
app.setStyle("Fusion")
if os.name == "nt":
    for name in ("msyh.ttc", "msyhbd.ttc", "arial.ttf"):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name))
    app.setFont(QFont("Microsoft YaHei", 10))
app.setStyleSheet(DARK_STYLESHEET)
set_lang("zh")
window = MainWindow(manager=ConfigManager(output / "settings"), start_workers=False, dry_run=True)
now = time.time()
limits = {"limit_id": "codex", "plan_type": "plus", "observed_at": now - 70,
          "primary": {"used_percent": 100, "window_minutes": 300, "resets_at": now + 8520},
          "secondary": {"used_percent": 44, "window_minutes": 10080, "resets_at": now + 300000}}
session = {"session_id": "sample-local-conversation", "title": "示例：开发桌面应用", "model": "local-model",
           "cwd": str(output.resolve()), "task_status": "rate_limited", "total_turns": 12,
           "project_name": "示例项目", "limited_at": now - 70, "limits_at": now - 70,
           "updated_at": now, "tokens_used": 24350, "limits": limits}
window._save_settings({"auto_resume": True})
window._on_snapshot({"scanned_at": now, "sessions": [session], "buckets": {"codex": limits},
                     "models": [{"slug": "local-model"}], "warnings": []})
window.page_dashboard.txt_prompt.setPlainText("配额已恢复，请继续完成刚才被中断的任务。")
window.page_quota.txt_name.setText("下午工作前启动窗口")
window.scheduler.add_task("示例：启动下一窗口", "请只回复已启动", str(output.resolve()), "local-model", scheduled_at=now + 8520, kind="kick")
window.scheduler.add_task("补齐桌面更新回归测试", "补齐更新回滚与进程清理的回归测试。", str(output.resolve()), "local-model", scheduled_at=now + 10000, sandbox="workspace-write")
finished = window.scheduler.add_task("整理软件更新说明", "整理中英文更新说明。", str(output.resolve()), scheduled_at=now - 600, sandbox="workspace-write")
window.scheduler.update(finished, status="completed", completed_at=now - 300)
window._refresh_queue()
window._tick()
window.show()
for i, name in enumerate(("overview", "planner", "queue", "sessions", "settings")):
    window.switch_page(i)
    app.processEvents()
    window.grab().save(str(output / f"{name}.png"))
window.switch_page(0)
window._save_settings({"auto_activate": True, "activation_cwd": str(output.resolve()),
                       "activation_model": "local-model", "activation_bucket": "codex"})
app.processEvents()
window.grab().save(str(output / "overview-activation.png"))
window.resize(940, 700)
app.processEvents()
window.grab().save(str(output / "overview-activation-compact.png"))
window.page_dashboard.set_mode(0)
app.processEvents()
window.grab().save(str(output / "overview-recovery-compact.png"))
window.show_recovery_history()
app.processEvents()
window.recovery_dialog.grab().save(str(output / "recovery-history.png"))
# Verify empty records and translated controls with the same production widgets.
empty = MainWindow(manager=ConfigManager(output / "empty-settings"), start_workers=False)
empty._on_snapshot({"scanned_at": now, "sessions": [], "buckets": {}, "models": [], "warnings": []})
empty.show()
app.processEvents()
empty.grab().save(str(output / "overview-empty.png"))
empty.page_dashboard.set_mode(1)
app.processEvents()
empty.grab().save(str(output / "overview-activation-empty.png"))
empty.request_quit()
set_lang("en")
english = MainWindow(manager=ConfigManager(output / "english-settings"), start_workers=False)
english._save_settings({"auto_activate": True, "activation_cwd": str(output.resolve()), "activation_bucket": "codex"})
english._on_snapshot({"scanned_at": now, "sessions": [session], "buckets": {"codex": limits}, "models": [{"slug": "local-model"}], "warnings": []})
english.show()
app.processEvents()
english.grab().save(str(output / "overview-activation-en.png"))
english.resize(940, 700)
app.processEvents()
english.grab().save(str(output / "overview-activation-en-compact.png"))

# Native QWidget screenshots of the implemented themes. Never write into the approved design folders.
checks = []
set_lang("zh")
window.recovery_dialog.hide()
window._save_settings({"auto_activate": False, "auto_resume": True})
for theme in ("dark", "light"):
    window._set_theme(theme)
    for width, height in ((1160, 820), (940, 700)):
        window.resize(width, height)
        for index, name in enumerate(("overview", "planner", "queue", "sessions", "settings")):
            window.switch_page(index)
            app.processEvents()
            app.processEvents()
            suffix = "-compact" if width == 940 else ""
            window.grab().save(str(output / f"{name}-{theme}{suffix}.png"))
            scroll = window.stacked.widget(index)
            checks.append({"page": name, "theme": theme, "size": [width, height],
                           "horizontalOverflow": scroll.horizontalScrollBar().maximum()})
        window.switch_page(0)
        window.page_dashboard.set_mode(1)
        app.processEvents()
        window.grab().save(str(output / f"activation-{theme}{suffix}.png"))
        window.page_dashboard.set_mode(0)
    window.resize(1160, 820)
    window.page_dashboard.recovery_details.open()
    app.processEvents()
    window.page_dashboard.recovery_details.grab().save(str(output / f"recovery-settings-{theme}.png"))
    window.page_dashboard.recovery_details.close()
    window.show_recovery_history()
    app.processEvents()
    window.recovery_dialog.grab().save(str(output / f"history-{theme}.png"))
    window.recovery_dialog.hide()
    window.update_dialog.show()
    app.processEvents()
    window.update_dialog.grab().save(str(output / f"updates-{theme}.png"))
    window.update_dialog.hide()

set_lang("en")
for theme in ("dark", "light"):
    english._set_theme(theme)
    for index, name in enumerate(("overview", "planner", "queue", "sessions", "settings")):
        english.switch_page(index)
        app.processEvents()
        app.processEvents()
        english.grab().save(str(output / f"{name}-{theme}-en-compact.png"))
        scroll = english.stacked.widget(index)
        checks.append({"page": name, "theme": theme, "language": "en", "size": [940, 700],
                       "horizontalOverflow": scroll.horizontalScrollBar().maximum()})
(output / "layout-checks.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8")
entries = (("overview", "总览"), ("planner", "窗口启动与预约"), ("queue", "执行队列"),
           ("sessions", "本地对话"), ("settings", "设置"), ("activation", "持续激活"),
           ("recovery-settings", "恢复设置"), ("history", "自动化记录与日志"), ("updates", "软件更新"))
gallery = ''.join(
    f'<section><h2>{title}</h2><div class="pair">' + ''.join(
        f'<a href="{name}-{theme}.png" target="_blank"><span>{theme}</span><img src="{name}-{theme}.png" alt="{title} {theme}"></a>'
        for theme in ("dark", "light")) + '</div></section>' for name, title in entries)
(output / "index.html").write_text('''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Sentinel 原生界面实现截图</title><style>
body{margin:0;background:#141414;color:#eee;font:14px/1.7 'Segoe UI','Microsoft YaHei',sans-serif}main{max-width:1500px;margin:auto;padding:30px}h1{font-size:28px}p{color:#aaa}h2{font-size:18px;font-weight:500;margin:25px 0 12px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px}a{color:#aaa;text-decoration:none;min-width:0;border:1px solid #363636;border-radius:6px;overflow:hidden}a span{display:block;padding:7px 12px;font-size:12px}img{display:block;width:100%;height:auto;background:#1f1f1f}@media(max-width:800px){.pair{grid-template-columns:1fr}main{padding:20px}}
</style><main><h1>Sentinel · 原生 Qt 界面实现</h1><p>左暗黑，右白色。全部截图来自实际 Python / PySide6 页面，使用隔离示例数据，未发送真实任务。点击图片查看原图。</p>''' + gallery + '</main></html>', encoding="utf-8")
english.request_quit()
window.request_quit()
app.processEvents()
print(str(output.resolve()))
