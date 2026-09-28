# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-09-28

### Added
- **Zero-Polling Rate Limit Detection**: Passive inspection of local `~/.codex/sessions/**/*.jsonl` rollout logs.
- **Cross-Platform Writer-Lock Management**: Solves the `thread already has an active writer (code -32600)` conflict across Windows (`msvcrt`) and Linux/macOS (`fcntl`).
- **Process Supervisor Handling**: Prevents Electron (`ChatGPT.exe`) process supervisor auto-respawn loops from blocking CLI session resumption.
- **Official CLI Resumption**: Hands over execution cleanly via `codex exec resume <session_id>` once official `resets_at` is reached.
- **Auto Desktop App Relaunch**: Automatically reopens Codex Desktop App upon task completion.
- **CI/CD & Releases**: Automated multi-platform CI (Windows, Linux, macOS) and tag-driven GitHub Releases.
