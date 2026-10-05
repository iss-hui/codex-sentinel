# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
