# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.2] - 2026-10-06

### Changed
- **Independent Automatic Recovery**: Monitor the latest quota-interrupted user conversation without adding tasks to the manual queue. Wait for locally recorded exhausted windows plus the configured buffer, resume once, and continue watching for the next interruption and reset.
- **Recovery Overview and History**: Show the selected project/chat, recovery status, countdown, next known reset, and a separate read-only history. Migrate old recovery queue entries without replaying finished work.
- **Execution Permissions**: Automatic recovery uses workspace write access with Codex automatic approval reviews (`--approve-for-me`). Scheduled tasks keep individually configured permissions. Unsupported CLIs fail before desktop takeover, and logs record requested permissions.

### Fixed
- Preserve quota interruptions when a terminal completion event follows the error; prioritize visible conversations and keep tracking the recovery target when internal review logs crowd the scan window.
- Avoid duplicate recovery after restarts, user continuation, cancellation, or successful completion. Network errors retry at most twice after 30/60 seconds; renewed quota errors wait for new local reset records.
- Keep automatic recovery independent of queue pause and missed-schedule grace periods. Handle executor startup failures without leaving a task stuck as running, and pause execution if process cleanup fails.

## [2.0.1] - 2026-10-06

### Fixed
- **Windows Standalone App Windowing**: Rebuilt `codex-sentinel-windows-x64.exe` with `--windowed` to prevent opening an unintended black CMD console window alongside the GUI application.
- **Console Attachment**: Supported `AttachConsole(-1)` on Windows so running CLI commands (`--status`, `--daemon`) from an existing terminal still outputs directly to that terminal.
- **macOS Process Cleanup Stability**: Handled `PermissionError` (EPERM) during `os.killpg` on macOS when process leaders exit, resolving CI failures across all Python environments.
- **Cross-Platform CI Hardening**: Added Linux Qt runtime packages and failure log diagnostics.

## [2.0.0] - 2026-10-05

### Added
- **Desktop Graphical Interface**: Full PySide6 desktop GUI with Dashboard, Quota Timer, Sessions, Task Queue, and Settings pages.
- **System Tray Integration**: System tray icon with quick actions (resume now, pause, settings, quit).
- **Quota & Schedule Planner**: Intelligent rate limit monitoring, queue scheduling, and automatic process handoff.

## [0.1.0] - 2026-09-28

### Added
- **Zero-Polling Rate Limit Detection**: Passive inspection of local `~/.codex/sessions/**/*.jsonl` rollout logs.
- **Cross-Platform Writer-Lock Management**: Solves the `thread already has an active writer (code -32600)` conflict across Windows (`msvcrt`) and Linux/macOS (`fcntl`).
- **Process Supervisor Handling**: Prevents Electron (`ChatGPT.exe`) process supervisor auto-respawn loops from blocking CLI session resumption.
- **Official CLI Resumption**: Hands over execution cleanly via `codex exec resume <session_id>` once official `resets_at` is reached.
- **Auto Desktop App Relaunch**: Automatically reopens Codex Desktop App upon task completion.
- **CI/CD & Releases**: Automated multi-platform CI (Windows, Linux, macOS) and tag-driven GitHub Releases.
