"""
Command-line interface (CLI) entrypoint for Codex Sentinel.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

from codex_sentinel import __version__
from codex_sentinel.core import run_daemon
from codex_sentinel.detector import find_active_rate_limit


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="codex-sentinel",
        description="Codex Sentinel: Intelligent unattended auto-resumer & writer-lock manager for OpenAI Codex.",
        epilog="Empowers long-running unattended Codex sessions across Windows, Linux, and macOS.",
    )
    parser.add_argument(
        "-v", "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--buffer",
        type=int,
        default=30,
        help="Buffer wait seconds after resets_at timestamp before waking up CLI (default: 30s).",
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default="配额已恢复，请继续完成刚才被中断的任务。",
        help="Custom prompt string to pass when resuming session.",
    )
    parser.add_argument(
        "--no-relaunch",
        action="store_true",
        help="Do not automatically relaunch the Desktop App after session execution finishes.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without terminating processes or executing the resume CLI.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Check and display current rate limit status once and exit.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.status:
        limit_info = find_active_rate_limit()
        if limit_info:
            reset_dt = datetime.fromtimestamp(limit_info["resets_at"])
            print(f"[⚠️ 限额生效中]")
            print(f"会话 ID   : {limit_info['session_id']}")
            print(f"模型      : {limit_info['model']}")
            print(f"解封时间  : {reset_dt.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"剩余时间  : {int(limit_info['remaining_seconds'])} 秒")
            print(f"工作目录  : {limit_info['cwd']}")
            print(f"日志文件  : {limit_info['file']}")
            sys.exit(1)
        else:
            print("🟢 当前状态正常：未检测到生效中的 5 小时限额。")
            sys.exit(0)

    try:
        run_daemon(
            buffer_seconds=args.buffer,
            prompt=args.prompt,
            auto_relaunch=not args.no_relaunch,
            dry_run=args.dry_run,
        )
    except KeyboardInterrupt:
        print("\n\n[退出] Codex Sentinel 守护已由用户手动中止。")
        sys.exit(0)


if __name__ == "__main__":
    main()
