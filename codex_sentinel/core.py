"""
Core daemon orchestration loop for Codex Sentinel.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from typing import Optional

from codex_sentinel.detector import find_active_rate_limit
from codex_sentinel.lock_manager import is_thread_locked, wait_for_lock_release
from codex_sentinel.process import kill_codex_desktop_tree, relaunch_desktop_app
from codex_sentinel.resume import resume_session_task


def play_sound_alert() -> None:
    """Play audio beep upon quota reset (cross-platform)."""
    try:
        if sys.platform == "win32":
            import winsound

            winsound.Beep(1000, 600)
        else:
            print("\a", end="", flush=True)
    except Exception:
        print("\a", end="", flush=True)


def ensure_lock_released(session_id: str, auto_release: bool = True, timeout: float = 10.0) -> bool:
    """
    Ensure the target thread lock is available for CLI writing.
    If occupied, automatically cleans up the desktop process tree to prevent Electron auto-respawn.
    """
    if not session_id or not is_thread_locked(session_id):
        return True

    print(f"\n[⚠️ 写入锁冲突] 检测到会话 {session_id} 正被 Codex 桌面客户端或后台服务占用！")
    if not auto_release:
        print("提示: auto-release 已关闭。请手动关闭桌面客户端以释放锁。")
        return False

    print("[🔄 自动抢占释放] 正在终止 Codex 桌面端及后台进程树，防止后台自动重启抢锁...")
    kill_codex_desktop_tree()

    print("[⏳ 等待锁释放] 正在校验锁状态...")
    if wait_for_lock_release(session_id, timeout=timeout):
        print("[✅ 会话锁已成功释放] 锁状态校验通过，守护进程接管任务！")
        return True

    print("[⚠️ 警告] 超时时间内未能完全释放文件锁，尝试继续执行 CLI...")
    return False


def run_daemon(
    buffer_seconds: int = 30,
    prompt: str = "配额已恢复，请继续完成刚才被中断的任务。",
    auto_relaunch: bool = True,
    dry_run: bool = False,
    poll_interval: float = 5.0,
) -> None:
    """
    Main daemon loop for continuously monitoring Codex sessions and resuming interrupted tasks.
    """
    print("=" * 65)
    print("      🛡️ Codex Sentinel - 智能无人值守守护守护进程已就绪")
    print("=" * 65)
    print("监控目录 : ~/.codex/sessions/**/*.jsonl")
    print("运行特性 : 零网络轮询、自适应跨平台锁抢占、到期无缝恢复会话\n")

    last_session_id: Optional[str] = None

    while True:
        limit_info = find_active_rate_limit()

        if limit_info:
            session_id = limit_info["session_id"]
            resets_at = limit_info["resets_at"]
            reset_dt = datetime.fromtimestamp(resets_at)
            cwd = limit_info["cwd"]

            if last_session_id != session_id:
                print(f"\n[⚠️ 检测到 5 小时限额生效中]")
                print(f"  📌 会话 ID   : {session_id}")
                print(f"  🤖 绑定模型 : {limit_info.get('model', '自动继承')}")
                print(f"  📂 工作目录 : {cwd}")
                print(f"  💬 限制原因 : {limit_info['error_msg']}")
                print(f"  🕒 解封时间 : {reset_dt.strftime('%Y-%m-%d %H:%M:%S')}")
                last_session_id = session_id

            # Countdown loop
            while True:
                now = time.time()
                remaining = int(resets_at - now)

                if remaining <= 0:
                    break

                h, rem = divmod(remaining, 3600)
                m, s = divmod(rem, 60)
                sys.stdout.write(
                    f"\r⏳ [限额倒计时] 距离解封还剩: {h:02d}小时 {m:02d}分钟 {s:02d}秒 (预定 {reset_dt.strftime('%H:%M:%S')})   "
                )
                sys.stdout.flush()
                time.sleep(1)

            # Reached quota reset timestamp
            print("\n\n[🔔 达到解封时间]")
            print(f"正在等待 {buffer_seconds} 秒网络缓冲，以确保服务端配额状态完全刷新...")
            for b in range(buffer_seconds, 0, -1):
                sys.stdout.write(f"\r缓冲等待中: {b:02d} 秒...   ")
                sys.stdout.flush()
                time.sleep(1)
            print("\n缓冲结束！")

            play_sound_alert()

            if dry_run:
                print("\n[Dry Run] 模拟运行模式已开启，跳过进程清理与 CLI 调用。")
            else:
                # 1. 确保锁可用
                ensure_lock_released(session_id, auto_release=True)

                # 2. 执行 CLI 恢复
                resume_session_task(session_id=session_id, cwd=cwd, prompt=prompt)

                # 3. 自动重新拉起桌面客户端
                if auto_relaunch:
                    print("\n[🖥️ 自动唤醒] 正在重新启动 Codex 桌面应用...")
                    relaunch_desktop_app()

            print("\n等待 30 秒后恢复监控...")
            time.sleep(30)
            last_session_id = None

        else:
            now_str = datetime.now().strftime("%H:%M:%S")
            sys.stdout.write(f"\r[{now_str}] 🟢 当前状态正常（未受限），正在实时监控会话...   ")
            sys.stdout.flush()
            time.sleep(poll_interval)
