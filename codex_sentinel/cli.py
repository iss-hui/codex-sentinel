"""
Command-line interface (CLI) entrypoint for Codex Sentinel.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

# Ensure utf-8 encoding for stdout/stderr across all platforms and Windows code pages
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from codex_sentinel import __version__
from codex_sentinel.core import run_daemon
from codex_sentinel.detector import find_active_rate_limit
from codex_sentinel.i18n import set_lang, t


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
        "--lang",
        type=str,
        choices=["auto", "zh", "en"],
        default="auto",
        help="Display language: 'auto' (detect from system), 'zh' (Chinese), or 'en' (English).",
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
        default=None,
        help="Custom prompt string to pass when resuming session (defaults to localized system prompt).",
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
    set_lang(args.lang)

    prompt = args.prompt if args.prompt is not None else t("default_resume_prompt")

    if args.status:
        limit_info = find_active_rate_limit()
        if limit_info:
            reset_dt = datetime.fromtimestamp(limit_info["resets_at"])
            print(t("status_detected_title"))
            print(t("label_session_id", val=limit_info["session_id"]))
            print(t("label_model", val=limit_info["model"]))
            print(t("label_reset_time", val=reset_dt.strftime("%Y-%m-%d %H:%M:%S")))
            print(t("label_remaining", val=int(limit_info["remaining_seconds"])))
            print(t("label_cwd", val=limit_info["cwd"]))
            print(t("label_file", val=limit_info["file"]))
            sys.exit(1)
        else:
            print(t("status_normal_exit"))
            sys.exit(0)

    try:
        run_daemon(
            buffer_seconds=args.buffer,
            prompt=prompt,
            auto_relaunch=not args.no_relaunch,
            dry_run=args.dry_run,
        )
    except KeyboardInterrupt:
        print(t("user_exit"))
        sys.exit(0)


if __name__ == "__main__":
    main()
