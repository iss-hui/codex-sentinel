"""Generate documentation screenshots from the real UI and synthetic local data.

No monitor, executor, account data or network request is started. Fixtures live
under .test-artifacts; only the generated PNGs are written to docs/assets.
"""

import argparse
import json
import os
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QDateTime
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from codex_sentinel.config import ConfigManager
from codex_sentinel.gui.main_window import MainWindow
from codex_sentinel.gui.tray_icon import SentinelTrayIcon
from codex_sentinel.i18n import set_lang
from codex_sentinel.quota_scheduler import TaskItem


def fixture(window, directory, language, now):
    zh = language == "zh"
    titles = (
        [
            "修复桌面更新后的进程清理",
            "补齐桌面更新回归测试",
            "整理软件更新说明",
            "检查安装包签名脚本",
            "同步中英文帮助文档",
            "优化报告导出时的表格分页",
            "梳理导出文件命名规则",
        ]
        if zh
        else [
            "Fix desktop update process cleanup",
            "Add update regression tests",
            "Prepare release notes",
            "Inspect package signing scripts",
            "Sync bilingual help pages",
            "Improve exported table pagination",
            "Review export naming conventions",
        ]
    )
    limits = {
        "limit_id": "codex",
        "plan_type": "plus",
        "observed_at": now - 20,
        "primary": {
            "used_percent": 100,
            "window_minutes": 300,
            "resets_at": now + 2490,
        },
        "secondary": {
            "used_percent": 44,
            "window_minutes": 10080,
            "resets_at": now + 242000,
        },
    }
    sessions = []
    for index, title in enumerate(titles):
        sessions.append(
            {
                "session_id": f"019dc89{index}-4a20-7db2-95d8-26b6c47fa890",
                "title": title,
                "project_name": "codex-sentinel" if index < 5 else "report-tool",
                "cwd": str(ROOT) if index < 5 else "D:/WorkSpace/report-tool",
                "model": "gpt-5.4" if index in (1, 3) else "",
                "task_status": "rate_limited"
                if index == 0
                else "failed"
                if index == 3
                else "unknown"
                if index == 6
                else "completed",
                "total_turns": [12, 8, 5, 9, 4, 16, None][index],
                "tokens_used": [24350, 18524, 9240, 14886, 6628, 31250, None][index],
                "limited_at": now - 20 if index == 0 else 0,
                "limits_at": now - 20,
                "updated_at": now - index * 1500,
                "limits": limits if index == 0 else {},
            }
        )
    window._on_snapshot(
        {
            "scanned_at": now,
            "sessions": sessions,
            "buckets": {"codex": limits},
            "models": [{"slug": "gpt-5.4"}],
            "warnings": [],
        }
    )
    prompt = (
        "配额已恢复，请继续完成刚才被中断的任务。"
        if zh
        else "Quota is available again. Continue the interrupted task."
    )
    window._save_settings(
        {
            "auto_resume": True,
            "resume_prompt": prompt,
            "queue_enabled": True,
            "check_updates": False,
            "activation_cwd": str(ROOT),
            "activation_bucket": "codex",
        }
    )
    log = directory / "resume.log"
    log.write_text(
        "\n".join(
            (
                json.dumps(
                    {"type": "thread.started", "thread_id": sessions[2]["session_id"]}
                ),
                "11:05:30  Waiting for the reset buffer to finish",
                "11:05:31  Writer lock released; starting workspace-write recovery",
                "11:06:10  turn.completed",
                "11:06:12  Owned processes cleaned up; desktop reopened",
            )
        ),
        encoding="utf-8",
    )
    recovery = TaskItem(
        "docs-recovery",
        "校验更新包 SHA-256" if zh else "Verify the update package SHA-256",
        prompt,
        str(ROOT),
        "",
        "completed",
        now - 9900,
        completed_at=now - 9738,
        session_id=sessions[2]["session_id"],
        kind="auto_resume",
        sandbox="workspace-write",
        log_file=str(log),
    )
    cancelled = TaskItem(
        "docs-cancelled",
        titles[2],
        prompt,
        str(ROOT),
        "",
        "cancelled",
        now - 14500,
        completed_at=now - 12950,
        session_id=sessions[2]["session_id"],
        kind="auto_resume",
        sandbox="workspace-write",
        last_error="用户已继续目标对话"
        if zh
        else "The user continued the target conversation",
    )
    activation = TaskItem(
        "docs-activation",
        "轻量消息 · 新建只读对话" if zh else "Lightweight turn · fresh read-only chat",
        "Reply only: Started. Do not use tools or modify files.",
        str(ROOT),
        "",
        "completed",
        now - 17300,
        completed_at=now - 17278,
        kind="activation",
        sandbox="read-only",
    )
    window.recovery.state["history"] = [asdict(cancelled), asdict(recovery)]
    window.activation.state["history"] = [asdict(activation)]
    window.activation.state["target"] = asdict(activation)
    entries = [
        (
            "下午工作前启动窗口" if zh else "Start a window before afternoon work",
            "kick",
            "pending",
            now + 2490,
            "",
            "",
        ),
        (
            titles[1],
            "task",
            "pending",
            now + 4290,
            "gpt-5.4",
            sessions[1]["session_id"],
        ),
        (titles[2], "task", "completed", now - 5280, "", sessions[2]["session_id"]),
        (titles[3], "task", "failed", now - 8280, "gpt-5.4", sessions[3]["session_id"]),
        (titles[4], "task", "missed", now - 13680, "", sessions[4]["session_id"]),
    ]
    for title, kind, status, when, model, session in entries:
        if kind == "kick":
            message = (
                "请只回复：已启动。不要调用工具或修改文件。"
                if zh
                else "Reply only: Started. Do not use tools or modify files."
            )
        else:
            message = (
                f"请继续完成“{title}”，保留现有接口与业务逻辑，并运行相关验证。"
                if zh
                else f"Continue: {title}. Preserve existing interfaces and behavior, and run the relevant checks."
            )
        task = window.scheduler.add_task(
            title,
            message,
            str(ROOT),
            model,
            kind=kind,
            session_id=session,
            scheduled_at=when,
            sandbox="read-only" if kind == "kick" else "workspace-write",
        )
        changes = {"status": status}
        if status not in ("pending", "waiting"):
            changes["completed_at"] = when + 120
        if status == "completed":
            changes["log_file"] = str(log)
        if status == "failed":
            changes["last_error"] = (
                "CLI 退出码 1；请检查原始日志"
                if zh
                else "CLI exited with code 1; inspect the original log"
            )
        if status == "missed":
            changes["last_error"] = (
                "唤醒时已超过 5 分钟宽限"
                if zh
                else "Wake-up exceeded the five-minute grace period"
            )
        window.scheduler.update(task, **changes)
    window._refresh_queue()
    window._refresh_recovery()
    page = window.page_quota
    page.txt_name.setText(entries[0][0])
    page.txt_cwd.setText(str(ROOT))
    page.txt_prompt.setPlainText(
        "请只回复：已启动。不要调用工具或修改文件。"
        if zh
        else "Reply only: Started. Do not use tools or modify files."
    )
    page.cmb_schedule.setCurrentIndex(page.cmb_schedule.findData("next"))
    page.date_edit.setDateTime(QDateTime.fromSecsSinceEpoch(int(now + 2490)))
    page.use_time.setDateTime(QDateTime.fromSecsSinceEpoch(int(now + 9690)))
    return sessions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/assets/readme")
    args = parser.parse_args()
    app = QApplication([])
    app.setStyle("Fusion")
    if os.name == "nt":
        for name in ("msyh.ttc", "msyhbd.ttc", "arial.ttf"):
            QFontDatabase.addApplicationFont(
                str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name)
            )
        app.setFont(QFont("Microsoft YaHei", 10))
    now = datetime.fromisoformat("2026-10-19T13:48:30+08:00").timestamp()
    checks = []
    for language in ("en", "zh"):
        set_lang(language)
        work = ROOT / ".test-artifacts/readme-fixtures" / language
        work.mkdir(parents=True, exist_ok=True)
        os.environ["CODEX_HOME"] = str(work / "codex")
        os.environ["CODEX_SENTINEL_HOME"] = str(work / "sentinel")
        output = args.output / language
        output.mkdir(parents=True, exist_ok=True)
        # Fresh isolated in-memory history/queue for every reproducible render.
        manager = ConfigManager(work / ("settings-" + str(os.getpid())))
        with (
            patch("time.time", return_value=now),
            patch(
                "codex_sentinel.gui.update_dialog.installation_kind",
                return_value="folder",
            ),
        ):
            window = MainWindow(manager=manager, start_workers=False, dry_run=True)
            fixture(window, work, language, now)
            tray = SentinelTrayIcon(window)
            window.resize(1160, 820)
            window.show()

            def capture(widget, name, theme, output=output, language=language):
                app.processEvents()
                app.processEvents()
                path = output / f"{name}-{theme}.png"
                assert widget.grab().save(str(path))
                checks.append(
                    {
                        "language": language,
                        "theme": theme,
                        "view": name,
                        "size": [widget.width(), widget.height()],
                    }
                )

            for theme in ("dark", "light"):
                window._set_theme(theme)
                window._save_settings({"auto_resume": True, "auto_activate": False})
                for index, name in enumerate(
                    ("overview", "planner", "queue", "sessions", "settings")
                ):
                    window.switch_page(index)
                    capture(window, name, theme)
                    assert (
                        window.stacked.widget(index).horizontalScrollBar().maximum()
                        == 0
                    )
                window.switch_page(0)
                window._save_settings({"auto_activate": True})
                capture(window, "activation", theme)
                window._save_settings({"auto_resume": True})
                window.page_dashboard.recovery_details.open()
                capture(
                    window.page_dashboard.recovery_details, "recovery-settings", theme
                )
                window.page_dashboard.recovery_details.close()
                window.show_recovery_history()
                window.recovery_dialog.resize(1000, 780)
                window.recovery_history.table.selectRow(0)
                capture(window.recovery_dialog, "history", theme)
                window.recovery_dialog.hide()
                window.update_dialog.show()
                capture(window.update_dialog, "updates", theme)
                window.update_dialog.hide()
                tray.refresh_theme()
                tray.menu.ensurePolished()
                tray.menu.adjustSize()
                tray.menu.show()
                capture(tray.menu, "tray", theme)
                tray.menu.hide()
            window.request_quit()
            app.processEvents()
    (ROOT / ".test-artifacts/readme-screenshot-checks.json").write_text(
        json.dumps(checks, indent=2), encoding="utf-8"
    )
    print(json.dumps({"screenshots": len(checks), "output": str(args.output)}))


if __name__ == "__main__":
    main()
