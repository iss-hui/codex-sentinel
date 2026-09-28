"""
Core daemon orchestration loop for Codex Sentinel.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from typing import Optional

from codex_sentinel.detector import find_active_rate_limit
from codex_sentinel.i18n import t
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

    print(t("lock_conflict", session_id=session_id))
    if not auto_release:
        print(t("lock_auto_release_off"))
        return False

    print(t("lock_cleaning_tree"))
    kill_codex_desktop_tree()

    print(t("lock_verifying"))
    if wait_for_lock_release(session_id, timeout=timeout):
        print(t("lock_released_success"))
        return True

    print(t("lock_timeout_warning"))
    return False


def run_daemon(
    buffer_seconds: int = 30,
    prompt: Optional[str] = None,
    auto_relaunch: bool = True,
    dry_run: bool = False,
    poll_interval: float = 5.0,
) -> None:
    """
    Main daemon loop for continuously monitoring Codex sessions and resuming interrupted tasks.
    """
    if prompt is None:
        prompt = t("default_resume_prompt")

    print("=" * 65)
    print(f"      {t('banner_title')}")
    print("=" * 65)
    print(t("banner_log_dir"))
    print(t("banner_features"))

    last_session_id: Optional[str] = None

    while True:
        limit_info = find_active_rate_limit()

        if limit_info:
            session_id = limit_info["session_id"]
            resets_at = limit_info["resets_at"]
            reset_dt = datetime.fromtimestamp(resets_at)
            cwd = limit_info["cwd"]

            if last_session_id != session_id:
                print(t("status_detected"))
                print(t("label_session_id", val=session_id))
                print(t("label_model", val=limit_info.get("model", "Default")))
                print(t("label_cwd", val=cwd))
                print(t("label_reason", val=limit_info["error_msg"]))
                print(t("label_reset_time", val=reset_dt.strftime("%Y-%m-%d %H:%M:%S")))
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
                    t("countdown_msg", h=h, m=m, s=s, time=reset_dt.strftime("%H:%M:%S"))
                )
                sys.stdout.flush()
                time.sleep(1)

            # Reached quota reset timestamp
            print(t("reached_reset_time"))
            print(t("buffer_waiting_intro", sec=buffer_seconds))
            for b in range(buffer_seconds, 0, -1):
                sys.stdout.write(t("buffer_waiting", b=b))
                sys.stdout.flush()
                time.sleep(1)
            print(t("buffer_done"))

            play_sound_alert()

            if dry_run:
                print(t("dry_run_msg"))
            else:
                # 1. 确保锁可用
                ensure_lock_released(session_id, auto_release=True)

                # 2. 执行 CLI 恢复
                resume_session_task(session_id=session_id, cwd=cwd, prompt=prompt)

                # 3. 自动重新拉起桌面客户端
                if auto_relaunch:
                    print(t("app_relaunching"))
                    relaunch_desktop_app()

            print(t("resuming_monitor"))
            time.sleep(30)
            last_session_id = None

        else:
            now_str = datetime.now().strftime("%H:%M:%S")
            sys.stdout.write(f"\r[{now_str}] {t('status_normal')}")
            sys.stdout.flush()
            time.sleep(poll_interval)
