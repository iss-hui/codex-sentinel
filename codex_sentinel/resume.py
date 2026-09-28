"""
Resumption executor: invokes the official Codex CLI `codex exec resume`.
"""

from __future__ import annotations

import subprocess
import sys
from typing import List, Optional


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
    cmd: List[str] = ["codex", "exec", "resume"]
    if session_id:
        cmd.extend([session_id, prompt])
    else:
        cmd.extend(["--last", prompt])

    print(f"\n[🚀 CLI 执行] 正在调用官方 Codex CLI 接管会话...")
    print(f"  -> 命令: {' '.join(cmd)}")
    print(f"  -> 目录: {cwd or '当前工作目录'}\n")
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
        print(f"\n[任务执行完成] 退出码: {process.returncode}")
        return process.returncode

    except FileNotFoundError:
        print("\n[错误] 未找到 'codex' 命令！请确保官方 Codex CLI 已安装并添加到系统 PATH 中。")
        return 127
    except Exception as e:
        print(f"\n[错误] 执行中断会话失败: {e}")
        return 1
