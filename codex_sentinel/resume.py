"""
Resumption executor: invokes the official Codex CLI `codex exec resume`.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


from codex_sentinel.i18n import t


import re


def _get_codex_version(path: Path) -> tuple[int, int, int]:
    """Extract (major, minor, patch) version from codex executable."""
    try:
        out = subprocess.check_output(
            [str(path), "--version"],
            stderr=subprocess.STDOUT,
            text=True,
            timeout=3,
        )
        match = re.search(r"(\d+)\.(\d+)\.(\d+)", out)
        if match:
            return tuple(map(int, match.groups()))
    except Exception:
        pass
    return (0, 0, 0)


def find_codex_binary() -> str:
    """
    Search for all candidate `codex` executables and select the HIGHEST available version.
    This guarantees that older CLI versions in PATH do not reject newer models (such as gpt-6-astra).
    """
    home = Path.home()
    candidate_paths: List[Path] = []

    # 1. System PATH
    found = shutil.which("codex")
    if found:
        candidate_paths.append(Path(found))

    # 2. Platform-specific locations
    if sys.platform == "win32":
        candidate_paths.extend([
            home / "AppData" / "Local" / "Programs" / "OpenAI" / "Codex" / "bin" / "codex.exe",
            home / ".codex" / "packages" / "standalone" / "current" / "bin" / "codex.exe",
        ])
        bin_dir = home / "AppData" / "Local" / "OpenAI" / "Codex" / "bin"
        if bin_dir.exists():
            for p in bin_dir.glob("**/codex.exe"):
                candidate_paths.append(p)
        standalone_dir = home / ".codex" / "packages" / "standalone"
        if standalone_dir.exists():
            for p in standalone_dir.glob("**/codex.exe"):
                candidate_paths.append(p)
    else:
        candidate_paths.extend([
            home / ".codex" / "packages" / "standalone" / "current" / "bin" / "codex",
            Path("/usr/local/bin/codex"),
            Path("/opt/homebrew/bin/codex"),
            home / ".local" / "bin" / "codex",
        ])

    # Deduplicate existing candidates
    valid_candidates = [p for p in set(candidate_paths) if p.exists()]
    if not valid_candidates:
        return "codex"

    # Sort by version descending (highest version first)
    valid_candidates.sort(key=_get_codex_version, reverse=True)
    return str(valid_candidates[0])


def resume_session_task(
    session_id: Optional[str],
    cwd: Optional[str] = None,
    prompt: str = "配额已恢复，请继续完成刚才被中断的任务。",
) -> int:
    """
    Execute `codex exec resume` to seamlessly continue the interrupted session.
    Streams execution logs directly to stdout.
    
    Returns the process exit code (0 for success).
    """
    codex_bin = find_codex_binary()
    cmd: List[str] = [codex_bin, "exec", "resume"]
    if session_id:
        cmd.extend([session_id, prompt])
    else:
        cmd.extend(["--last", prompt])

    print(t("cli_invoking"))
    print(t("cli_command", cmd=" ".join(cmd)))
    print(t("cli_cwd", cwd=cwd or "current directory"))
    print("-" * 60)

    try:
        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        if process.stdout:
            for line in process.stdout:
                sys.stdout.write(line)
                sys.stdout.flush()

        process.wait()
        print("-" * 60)
        print(t("cli_finished", code=process.returncode))
        return process.returncode

    except FileNotFoundError:
        print(t("cli_not_found"))
        return 127
    except Exception as e:
        print(t("cli_error", e=e))
        return 1
