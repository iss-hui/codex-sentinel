# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.8] - 2026-10-19

### Added
- Show a clickable NEW badge next to the top-left logo for GitHub Release updates, with release notes, download progress, cancellation, and restart-to-update.
- Bundle an independent updater for Windows x64 folder and single-file builds. Verify downloads, wait for the current task, preserve settings and unrelated files, and restore old files if replacement or the launch request fails.
- Check for updates on startup and every six hours, with a Settings opt-out and manual check. Publish SHA-256 checksums with release assets.

## [2.0.7] - 2026-10-15

### Fixed
- Allow 30 seconds for the activation MCP configuration check and retry that read-only query once on timeout, so transient CLI startup delays do not immediately fail activation. Repeated timeouts stop before sending a message and provide a clear error in the execution log.

## [2.0.6] - 2026-10-13

### Fixed
- Avoid mutually exclusive `--sandbox` and `--approve-for-me` options when starting or resuming writable tasks; the automatic-review preset already selects workspace write access.

## [2.0.5] - 2026-10-12

### Fixed
- Dynamically detect Codex CLI executables without stale in-memory caching across background updates.
- Ensure task execution logs are initialized even if preflight checks fail.
- Display a friendly hint in task history when a log file is absent instead of a raw filesystem error.
- Disable unused MCP servers, connectors, and plugins only for five-hour window activation commands, keeping user configuration intact.
- Show execution status and completion time above raw logs, so auxiliary service errors do not obscure a completed activation.

## [2.0.4] - 2026-10-09

### Added
- Resume Loop logo for the desktop application, system tray, and Windows executable, with status badges preserved in the tray.

### Fixed
- Include application logo resources in packaged builds and embed the selected icon in Windows EXE downloads.

### Changed
- Remove the automatic Python test CI workflow.

## [2.0.3] - 2026-10-08

### Changed
- Include the release tag in GitHub Release titles, CI artifact names, and Windows, Linux, and macOS standalone download filenames.
- Document versioned release downloads in the English and Chinese READMEs.

### Fixed
- Reject releases when the Git tag, Python package version, and runtime version do not match.
- Fail artifact uploads when no build output is found.

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
