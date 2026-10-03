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
        default=None,
        help="Display language: 'auto' (detect from system), 'zh' (Chinese), or 'en' (English).",
    )
    parser.add_argument(
        "--buffer",
        type=int,
        default=None,
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
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Launch the desktop GUI application (default when PySide6 is available).",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run in headless CLI daemon mode (original behavior).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    set_lang(args.lang or "auto")
    if args.buffer is not None and not 0 <= args.buffer <= 600:
        raise SystemExit("--buffer must be between 0 and 600 seconds")
    if args.gui and args.daemon:
        raise SystemExit("Choose either --gui or --daemon")

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

    # Determine launch mode: GUI (default) or CLI daemon
    use_gui = not args.daemon  # GUI is default unless --daemon is specified

    if args.gui:
        use_gui = True  # Explicit --gui overrides

    if use_gui:
        try:
            from codex_sentinel.gui.app import main as gui_main
        except ImportError as exc:
            raise SystemExit(f"GUI dependency unavailable: {exc}. Install PySide6 or use --daemon.") from exc
        overrides = {}
        if args.lang is not None:
            overrides["language"] = args.lang
        if args.buffer is not None:
            overrides["buffer_seconds"] = args.buffer
        if args.prompt is not None:
            overrides["resume_prompt"] = args.prompt
        raise SystemExit(gui_main(overrides=overrides, dry_run=args.dry_run))
    else:
        _run_daemon(args, prompt)


def _run_daemon(args, prompt: str) -> None:
    """Run the legacy CLI daemon mode."""
    try:
        run_daemon(
            buffer_seconds=args.buffer if args.buffer is not None else 30,
            prompt=prompt,
            auto_relaunch=not args.no_relaunch,
            dry_run=args.dry_run,
        )
    except KeyboardInterrupt:
        print(t("user_exit"))
        sys.exit(0)


if __name__ == "__main__":
    main()
