"""
Internationalization (i18n) module for Codex Sentinel.
Automatically detects system locale (Chinese vs English default), with manual override support.
"""

from __future__ import annotations

import locale
import os
import sys
from typing import Dict


def detect_system_lang() -> str:
    """
    Detect whether the host OS language is Chinese.
    Returns 'zh' for Chinese environments, otherwise defaults to 'en'.
    """
    # 1. Check environment variables
    for env in ["LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"]:
        val = os.environ.get(env, "").lower()
        if "zh" in val:
            return "zh"
        if val.startswith("en"):
            return "en"

    # 2. Check Python's default locale
    try:
        loc = locale.getdefaultlocale()[0]
        if loc and loc.lower().startswith("zh"):
            return "zh"
    except Exception:
        pass

    # 3. Windows-specific API detection (handles Simplified and Traditional Chinese)
    if sys.platform == "win32":
        try:
            import ctypes
            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            primary_lang = lang_id & 0xFF
            if primary_lang == 0x04:  # LANG_CHINESE
                return "zh"
        except Exception:
            pass

    return "en"


_CURRENT_LANG: str = detect_system_lang()


def set_lang(lang: str) -> None:
    """Explicitly set active display language ('auto', 'zh', or 'en')."""
    global _CURRENT_LANG
    if lang == "auto":
        _CURRENT_LANG = detect_system_lang()
    elif lang in ("zh", "en"):
        _CURRENT_LANG = lang


def get_lang() -> str:
    """Return the currently active language code."""
    return _CURRENT_LANG


MESSAGES: Dict[str, Dict[str, str]] = {
    # Default Prompt
    "default_resume_prompt": {
        "zh": "配额已恢复，请继续完成刚才被中断的任务。",
        "en": "Quota has been restored. Please resume and complete the previously interrupted task.",
    },
    # Daemon Banner
    "banner_title": {
        "zh": "🛡️ Codex Sentinel - 智能无人值守守护进程已就绪",
        "en": "🛡️ Codex Sentinel - Intelligent Unattended Resilience Daemon Ready",
    },
    "banner_log_dir": {
        "zh": "监控目录 : ~/.codex/sessions/**/*.jsonl",
        "en": "Log directory : ~/.codex/sessions/**/*.jsonl",
    },
    "banner_features": {
        "zh": "运行特性 : 零网络轮询、自适应跨平台锁抢占、到期无缝恢复会话\n",
        "en": "Features : Zero network polling, auto lock management, official CLI handover\n",
    },
    # Monitoring Status
    "status_normal": {
        "zh": "🟢 当前状态正常（未受限），正在实时监控会话...   ",
        "en": "🟢 Status normal (no active rate limits), monitoring sessions...   ",
    },
    "status_normal_exit": {
        "zh": "🟢 当前状态正常：未检测到生效中的 5 小时限额。",
        "en": "🟢 Status normal: No active 5-hour rate limit detected.",
    },
    "status_detected": {
        "zh": "\n[⚠️ 检测到 5 小时限额生效中]",
        "en": "\n[⚠️ Active 5-Hour Rate Limit Detected]",
    },
    "status_detected_title": {
        "zh": "[⚠️ 限额生效中]",
        "en": "[⚠️ Rate Limit Active]",
    },
    # Field Labels
    "label_session_id": {
        "zh": "  📌 会话 ID   : {val}",
        "en": "  📌 Session ID : {val}",
    },
    "label_model": {
        "zh": "  🤖 绑定模型 : {val}",
        "en": "  🤖 Bound Model: {val}",
    },
    "label_cwd": {
        "zh": "  📂 工作目录 : {val}",
        "en": "  📂 Working Dir: {val}",
    },
    "label_reason": {
        "zh": "  💬 限制原因 : {val}",
        "en": "  💬 Error Msg  : {val}",
    },
    "label_reset_time": {
        "zh": "  🕒 解封时间 : {val}",
        "en": "  🕒 Reset Time : {val}",
    },
    "label_remaining": {
        "zh": "剩余时间  : {val} 秒",
        "en": "Remaining : {val} seconds",
    },
    "label_file": {
        "zh": "日志文件  : {val}",
        "en": "Log File  : {val}",
    },
    # Countdown & Buffer
    "countdown_msg": {
        "zh": "\r⏳ [限额倒计时] 距离解封还剩: {h:02d}小时 {m:02d}分钟 {s:02d}秒 (预定 {time})   ",
        "en": "\r⏳ [Cooldown Countdown] Time remaining: {h:02d}h {m:02d}m {s:02d}s (Scheduled {time})   ",
    },
    "reached_reset_time": {
        "zh": "\n\n[🔔 达到解封时间]",
        "en": "\n\n[🔔 Quota Reset Time Reached]",
    },
    "buffer_waiting_intro": {
        "zh": "正在等待 {sec} 秒网络缓冲，以确保服务端配额状态完全刷新...",
        "en": "Waiting {sec}s network buffer to ensure server-side quota state is refreshed...",
    },
    "buffer_waiting": {
        "zh": "\r缓冲等待中: {b:02d} 秒...   ",
        "en": "\rBuffering: {b:02d} seconds remaining...   ",
    },
    "buffer_done": {
        "zh": "\n缓冲结束！",
        "en": "\nBuffer completed!",
    },
    "dry_run_msg": {
        "zh": "\n[Dry Run] 模拟运行模式已开启，跳过进程清理与 CLI 调用。",
        "en": "\n[Dry Run] Simulation mode enabled. Skipping process termination and CLI call.",
    },
    "resuming_monitor": {
        "zh": "\n等待 30 秒后恢复监控...",
        "en": "\nWaiting 30 seconds before resuming monitor...",
    },
    # Lock Manager
    "lock_conflict": {
        "zh": "\n[⚠️ 写入锁冲突] 检测到会话 {session_id} 正被 Codex 桌面客户端或后台服务占用！",
        "en": "\n[⚠️ Writer Lock Conflict] Session {session_id} is currently held by Codex Desktop App or backend server!",
    },
    "lock_auto_release_off": {
        "zh": "提示: auto-release 已关闭。请手动关闭桌面客户端以释放锁。",
        "en": "Notice: auto-release is disabled. Please close the desktop app to release the lock.",
    },
    "lock_cleaning_tree": {
        "zh": "[🔄 自动抢占释放] 正在终止 Codex 桌面端及后台进程树，防止后台自动重启抢锁...",
        "en": "[🔄 Auto-Release] Terminating Codex desktop app and process tree to avoid auto-respawn locks...",
    },
    "lock_verifying": {
        "zh": "[⏳ 等待锁释放] 正在校验锁状态...",
        "en": "[⏳ Waiting For Lock Release] Verifying lock availability...",
    },
    "lock_released_success": {
        "zh": "[✅ 会话锁已成功释放] 锁状态校验通过，守护进程接管任务！",
        "en": "[✅ Session Lock Released] Lock check passed! Sentinel is taking over the task!",
    },
    "lock_timeout_warning": {
        "zh": "[⚠️ 警告] 超时时间内未能完全释放文件锁，尝试继续执行 CLI...",
        "en": "[⚠️ Warning] File lock was not released within timeout. Attempting CLI resumption anyway...",
    },
    # Resume & CLI Execution
    "cli_invoking": {
        "zh": "\n[🚀 CLI 执行] 正在调用官方 Codex CLI 接管会话...",
        "en": "\n[🚀 CLI Resumption] Invoking official Codex CLI to resume session...",
    },
    "cli_command": {
        "zh": "  -> 命令: {cmd}",
        "en": "  -> Command: {cmd}",
    },
    "cli_cwd": {
        "zh": "  -> 目录: {cwd}",
        "en": "  -> Working Directory: {cwd}",
    },
    "cli_finished": {
        "zh": "\n[任务执行完成] 退出码: {code}",
        "en": "\n[Task Completed] Exit code: {code}",
    },
    "cli_not_found": {
        "zh": "\n[错误] 未找到 'codex' 命令！请确保官方 Codex CLI 已安装并添加到系统 PATH 中。",
        "en": "\n[Error] 'codex' executable not found! Please ensure Codex CLI is installed.",
    },
    "cli_error": {
        "zh": "\n[错误] 执行中断会话失败: {e}",
        "en": "\n[Error] Failed to resume session: {e}",
    },
    # Desktop Relaunch
    "app_relaunching": {
        "zh": "\n[🖥️ 自动唤醒] 正在重新启动 Codex 桌面应用...",
        "en": "\n[🖥️ Auto-Relaunch] Re-opening Codex Desktop App...",
    },
    "user_exit": {
        "zh": "\n\n[退出] Codex Sentinel 守护已由用户手动中止。",
        "en": "\n\n[Exit] Codex Sentinel daemon stopped by user.",
    },
    # === GUI Window ===
    "app_title": {"zh": "Codex Sentinel 🛡️ 智能限额管理", "en": "Codex Sentinel 🛡️ Intelligent Quota Manager"},
    "nav_dashboard": {"zh": "仪表盘", "en": "Dashboard"},
    "nav_quota_timer": {"zh": "限额启动器", "en": "Quota Timer"},
    "nav_task_queue": {"zh": "任务预排", "en": "Task Queue"},
    "nav_sessions": {"zh": "会话历史", "en": "Sessions"},
    "nav_settings": {"zh": "设置", "en": "Settings"},

    # === Dashboard Page ===
    "dash_status_normal": {"zh": "🟢 正常监控中 — 无活跃限额", "en": "🟢 Monitoring — No Active Rate Limit"},
    "dash_status_limited": {"zh": "🟡 限额冷却中", "en": "🟡 Rate Limited — Cooling Down"},
    "dash_status_resuming": {"zh": "🔵 正在恢复会话...", "en": "🔵 Resuming Session..."},
    "dash_status_error": {"zh": "🔴 错误", "en": "🔴 Error"},
    "dash_countdown_title": {"zh": "限额倒计时", "en": "Rate Limit Countdown"},
    "dash_reset_time": {"zh": "解封时间", "en": "Reset Time"},
    "dash_session_info": {"zh": "会话信息", "en": "Session Info"},
    "dash_session_id": {"zh": "会话 ID", "en": "Session ID"},
    "dash_model": {"zh": "模型", "en": "Model"},
    "dash_working_dir": {"zh": "工作目录", "en": "Working Directory"},
    "dash_error_reason": {"zh": "限制原因", "en": "Error Reason"},
    "dash_used_percent": {"zh": "使用量", "en": "Usage"},
    "dash_auto_resume": {"zh": "到期自动恢复对话", "en": "Auto-resume when quota resets"},
    "dash_buffer_delay": {"zh": "缓冲延迟 (秒)", "en": "Buffer Delay (seconds)"},
    "dash_resume_prompt": {"zh": "恢复语句", "en": "Resume Prompt"},
    "dash_btn_resume_now": {"zh": "▶ 立即恢复", "en": "▶ Resume Now"},
    "dash_btn_pause": {"zh": "⏸ 暂停监控", "en": "⏸ Pause Monitor"},
    "dash_btn_resume_monitor": {"zh": "▶ 恢复监控", "en": "▶ Resume Monitor"},
    "dash_monitoring_time": {"zh": "已监控: {val}", "en": "Monitored: {val}"},

    # === Quota Timer Page ===
    "quota_title": {"zh": "五小时限额启动器", "en": "5-Hour Quota Timer"},
    "quota_description": {"zh": "主动发起一次 Codex 对话来启动限额滚动窗口，精确控制限额开始计时的时间点。", "en": "Initiate a Codex conversation to start the quota rolling window, giving you precise control over when the timer begins."},
    "quota_select_model": {"zh": "选择模型", "en": "Select Model"},
    "quota_working_dir": {"zh": "工作目录", "en": "Working Directory"},
    "quota_kick_prompt": {"zh": "启动对话", "en": "Kick Prompt"},
    "quota_kick_prompt_default": {"zh": "请简要回复'已启动'", "en": "Please briefly reply 'started'"},
    "quota_schedule_time": {"zh": "计划时间", "en": "Schedule Time"},
    "quota_schedule_now": {"zh": "立即", "en": "Now"},
    "quota_schedule_timed": {"zh": "定时", "en": "Scheduled"},
    "quota_post_task": {"zh": "启动后任务 (可选)", "en": "Post-Kick Task (Optional)"},
    "quota_btn_kick": {"zh": "🚀 启动限额", "en": "🚀 Start Quota"},
    "quota_btn_schedule": {"zh": "📅 定时启动", "en": "📅 Schedule Start"},
    "quota_timeline_title": {"zh": "限额时间线", "en": "Quota Timeline"},
    "quota_kick_success": {"zh": "✅ 限额已成功启动！5小时窗口开始计时。", "en": "✅ Quota started! 5-hour window timer has begun."},
    "quota_kick_failed": {"zh": "❌ 启动失败: {error}", "en": "❌ Kick failed: {error}"},

    # === Task Queue Page ===
    "queue_title": {"zh": "下一轮任务预排", "en": "Next Quota Task Queue"},
    "queue_description": {"zh": "当限额恢复后，自动执行预排的任务。", "en": "Tasks to auto-execute when quota resets."},
    "queue_col_order": {"zh": "#", "en": "#"},
    "queue_col_name": {"zh": "任务名称", "en": "Task Name"},
    "queue_col_prompt": {"zh": "Prompt (摘要)", "en": "Prompt (Summary)"},
    "queue_col_cwd": {"zh": "工作目录", "en": "Working Dir"},
    "queue_col_model": {"zh": "模型", "en": "Model"},
    "queue_col_status": {"zh": "状态", "en": "Status"},
    "queue_col_actions": {"zh": "操作", "en": "Actions"},
    "queue_btn_add": {"zh": "➕ 添加任务", "en": "➕ Add Task"},
    "queue_auto_execute": {"zh": "限额恢复后自动执行第一个任务", "en": "Auto-execute first task when quota resets"},
    "queue_chain_execute": {"zh": "每个任务完成后自动执行下一个", "en": "Auto-execute next task after each completes"},
    "queue_buffer_label": {"zh": "缓冲延迟 (秒)", "en": "Buffer Delay (seconds)"},
    "queue_status_pending": {"zh": "待执行", "en": "Pending"},
    "queue_status_running": {"zh": "执行中", "en": "Running"},
    "queue_status_completed": {"zh": "已完成", "en": "Completed"},
    "queue_status_failed": {"zh": "失败", "en": "Failed"},
    "queue_dialog_title": {"zh": "添加任务", "en": "Add Task"},
    "queue_dialog_name": {"zh": "任务名称", "en": "Task Name"},
    "queue_dialog_prompt": {"zh": "Prompt", "en": "Prompt"},
    "queue_dialog_cwd": {"zh": "工作目录", "en": "Working Directory"},
    "queue_dialog_model": {"zh": "模型", "en": "Model"},
    "queue_empty": {"zh": "暂无预排任务", "en": "No queued tasks"},

    # === Sessions Page ===
    "sessions_title": {"zh": "本地会话历史", "en": "Local Session History"},
    "sessions_search": {"zh": "搜索...", "en": "Search..."},
    "sessions_col_id": {"zh": "会话 ID", "en": "Session ID"},
    "sessions_col_model": {"zh": "模型", "en": "Model"},
    "sessions_col_time": {"zh": "开始时间", "en": "Start Time"},
    "sessions_col_cwd": {"zh": "工作目录", "en": "Working Dir"},
    "sessions_col_limited": {"zh": "限速", "en": "Rate Limited"},
    "sessions_col_status": {"zh": "状态", "en": "Status"},
    "sessions_stats": {"zh": "过去{days}天触发限额 {count} 次 | 平均冷却 {avg}", "en": "Past {days} days: {count} rate limits | Avg cooldown {avg}"},

    # === Settings Page ===
    "settings_title": {"zh": "设置", "en": "Settings"},
    "settings_language": {"zh": "语言 / Language", "en": "Language"},
    "settings_poll_interval": {"zh": "轮询间隔 (秒)", "en": "Poll Interval (seconds)"},
    "settings_buffer_delay": {"zh": "恢复缓冲延迟 (秒)", "en": "Resume Buffer Delay (seconds)"},
    "settings_default_prompt": {"zh": "默认恢复 Prompt", "en": "Default Resume Prompt"},
    "settings_minimize_tray": {"zh": "关闭窗口时最小化到系统托盘", "en": "Minimize to system tray on close"},
    "settings_auto_resume": {"zh": "到期自动恢复对话", "en": "Auto-resume when quota resets"},
    "settings_auto_relaunch": {"zh": "恢复后自动重启桌面应用", "en": "Auto-relaunch Desktop App after resume"},
    "settings_auto_start": {"zh": "开机自动启动", "en": "Start on system boot"},
    "settings_notifications": {"zh": "限额触发时显示桌面通知", "en": "Show desktop notification on rate limit"},
    "settings_sound": {"zh": "限额恢复时播放提示音", "en": "Play sound on quota reset"},
    "settings_sessions_dir": {"zh": "Codex 会话目录", "en": "Codex Sessions Directory"},
    "settings_codex_path": {"zh": "Codex CLI 路径", "en": "Codex CLI Path"},
    "settings_auto_detected": {"zh": "(自动检测)", "en": "(Auto-detected)"},
    "settings_btn_save": {"zh": "💾 保存设置", "en": "💾 Save Settings"},
    "settings_btn_reset": {"zh": "↩️ 恢复默认", "en": "↩️ Reset Defaults"},
    "settings_saved": {"zh": "✅ 设置已保存", "en": "✅ Settings saved"},
    "settings_reset_done": {"zh": "✅ 已恢复默认设置", "en": "✅ Settings reset to defaults"},

    # === System Tray ===
    "tray_tooltip_normal": {"zh": "Codex Sentinel: 正常监控中", "en": "Codex Sentinel: Monitoring"},
    "tray_tooltip_limited": {"zh": "Codex Sentinel: {time} 后恢复", "en": "Codex Sentinel: Resets in {time}"},
    "tray_tooltip_resuming": {"zh": "Codex Sentinel: 正在恢复...", "en": "Codex Sentinel: Resuming..."},
    "tray_open": {"zh": "打开仪表盘", "en": "Open Dashboard"},
    "tray_status": {"zh": "状态: {status}", "en": "Status: {status}"},
    "tray_resume_now": {"zh": "立即恢复", "en": "Resume Now"},
    "tray_pause": {"zh": "暂停监控", "en": "Pause Monitor"},
    "tray_settings": {"zh": "设置", "en": "Settings"},
    "tray_quit": {"zh": "退出 Sentinel", "en": "Quit Sentinel"},
    "tray_minimized_msg": {"zh": "Sentinel 在后台运行，限额恢复时将自动唤醒。", "en": "Sentinel is running in background. Will auto-resume when quota resets."},

    # === Notifications ===
    "notify_rate_limit_detected": {"zh": "检测到 5 小时限额！将在 {time} 后自动恢复。", "en": "5-hour rate limit detected! Will auto-resume in {time}."},
    "notify_resume_success": {"zh": "会话已成功恢复！", "en": "Session resumed successfully!"},
    "notify_resume_failed": {"zh": "会话恢复失败 (退出码: {code})", "en": "Session resume failed (exit code: {code})"},
    "notify_quota_kicked": {"zh": "限额已启动！5小时窗口开始计时。", "en": "Quota started! 5-hour window timer begun."},

    # === Common ===
    "common_browse": {"zh": "浏览...", "en": "Browse..."},
    "common_confirm": {"zh": "确认", "en": "Confirm"},
    "common_cancel": {"zh": "取消", "en": "Cancel"},
    "common_hours": {"zh": "小时", "en": "hours"},
    "common_minutes": {"zh": "分钟", "en": "minutes"},
    "common_seconds": {"zh": "秒", "en": "seconds"},
    "common_yes": {"zh": "是", "en": "Yes"},
    "common_no": {"zh": "否", "en": "No"},
    "common_error": {"zh": "错误", "en": "Error"},
    "common_success": {"zh": "成功", "en": "Success"},
}


def t(key: str, fallback: str = "", **kwargs) -> str:
    """
    Retrieve localized message by key and format with kwargs.
    Falls back to English if the key is not translated for active language.

    Supports both underscore keys (e.g. 'app_title') and dot keys (e.g. 'app.title').
    An optional fallback string is returned if the key is not found.
    """
    # Try original key first, then dot-to-underscore conversion
    entry = MESSAGES.get(key)
    if entry is None:
        normalized = key.replace(".", "_")
        entry = MESSAGES.get(normalized, {})

    text = entry.get(_CURRENT_LANG) or entry.get("en") or fallback or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text
    return text
