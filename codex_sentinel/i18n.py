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
}


def t(key: str, **kwargs) -> str:
    """
    Retrieve localized message by key and format with kwargs.
    Falls back to English if the key is not translated for active language.
    """
    entry = MESSAGES.get(key, {})
    text = entry.get(_CURRENT_LANG) or entry.get("en") or key
    if kwargs:
        return text.format(**kwargs)
    return text
