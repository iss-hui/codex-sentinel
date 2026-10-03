"""Render all desktop pages with synthetic, offline data for visual QA."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QFontDatabase
from codex_sentinel.config import ConfigManager
from codex_sentinel.gui.app import DARK_STYLESHEET
from codex_sentinel.gui.main_window import MainWindow
from codex_sentinel.i18n import set_lang

output = Path(sys.argv[1] if len(sys.argv) > 1 else ".test-artifacts/screens")
output.mkdir(parents=True, exist_ok=True)
os.environ["CODEX_HOME"] = str(output / "codex")
os.environ["CODEX_SENTINEL_HOME"] = str(output / "sentinel")
app = QApplication([])
if os.name == "nt":
    for name in ("msyh.ttc", "msyhbd.ttc", "arial.ttf"):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name))
    app.setFont(QFont("Microsoft YaHei", 10))
app.setStyleSheet(DARK_STYLESHEET)
set_lang("zh")
window = MainWindow(manager=ConfigManager(output / "settings"), start_workers=False, dry_run=True)
now = time.time()
limits = {"limit_id": "codex", "plan_type": "plus", "observed_at": now - 70,
          "primary": {"used_percent": 76, "window_minutes": 300, "resets_at": now + 8520},
          "secondary": {"used_percent": 44, "window_minutes": 10080, "resets_at": now + 300000}}
session = {"session_id": "sample-local-conversation", "title": "示例：开发桌面应用", "model": "local-model",
           "cwd": str(output.resolve()), "task_status": "completed", "total_turns": 12,
           "updated_at": now, "tokens_used": 24350, "limits": limits}
window._on_snapshot({"scanned_at": now, "sessions": [session], "buckets": {"codex": limits},
                     "models": [{"slug": "local-model"}], "warnings": []})
window.page_dashboard.txt_prompt.setPlainText("配额已恢复，请继续完成刚才被中断的任务。")
window.page_quota.txt_name.setText("下午工作前启动窗口")
window.scheduler.add_task("示例：启动下一窗口", "请只回复已启动", str(output.resolve()), "local-model", scheduled_at=now + 8520, kind="kick")
window._refresh_queue()
window.show()
for i, name in enumerate(("overview", "planner", "queue", "sessions", "settings")):
    window.switch_page(i)
    app.processEvents()
    window.grab().save(str(output / f"{name}.png"))
window.request_quit()
app.processEvents()
print(str(output.resolve()))
