# Codex Sentinel 2.0

A local-first desktop quota dashboard, scheduled turn launcher, and conversation resumer for Codex.

[中文说明](README_zh.md) · [Implementation notes](docs/desktop-completion.md)

![Desktop overview with sample data](docs/assets/desktop_dashboard.png)

## Run

On Windows, extract `CodexSentinel-windows-x64.zip` and open `CodexSentinel.exe`. Keep its `_internal` folder alongside it. Install and sign in to the official Codex CLI first; Sentinel detects it locally or accepts a path in Settings.

From source (Python 3.10+):

```sh
pip install -e '.[dev]'
python run_desktop.py
```

Installed commands:

```sh
codex-sentinel                     # Desktop by default
codex-sentinel-gui                 # Windowed entry point
codex-sentinel --gui --lang en
codex-sentinel --gui --dry-run      # Simulate without sending messages
codex-sentinel --daemon            # Legacy headless daemon
codex-sentinel --status            # Legacy one-time status check
```

Use `--buffer 30` / `--buffer 60` and `--prompt` to override desktop settings. GUI startup errors never silently fall back to a daemon that sends messages. `--no-relaunch` only affects the legacy daemon.

## Desktop features

- **Overview:** Local quota groups, primary and weekly windows, usage percentages, reset dates, countdown, plan, and observation time. Missing values stay unknown; expired records are marked stale.
- **Resume controls:** Opt-in automatic recovery of quota-interrupted conversations, configurable prompt, and a 30-second buffer (60-second shortcut). Read-only by default; opt into workspace edits when needed. Save prompt, permission, and buffer changes explicitly. The auto-resume checkbox takes effect immediately.
- **Window planner:** Choose a cached or manually entered model, existing/new conversation, working directory, message/task, and full date/time. Schedule at the next locally recorded five-hour reset, or send 2–3 hours before your planned work start.
- **Task queue:** Persist, edit, reorder, cancel, reschedule, pause, stop, and inspect execution logs. Runs one task at a time. Exhausted weekly quota also delays execution. By default, a busy target triggers closing Codex Desktop (interrupting its active tasks), waiting for the writer lock, running the task, cleaning up the CLI process group, then reopening the desktop. Disable this option in Settings to wait for the desktop instead.
- **Local conversations:** Read the full local index of unarchived interactive chats, use Codex display titles, and group them by saved project. Internal review/subagent logs are excluded from the picker. Search titles, models, directories, recorded token totals, and turn states.
- **Tray:** Closing hides the app when a system tray is available. Quit cancels the active child process and exits cleanly. Only one desktop instance runs per Sentinel data directory.

A scheduled message **does not guarantee a new five-hour window**. The server controls quota resets; Sentinel cannot reset an active window or skip a limit. It sends the chosen prompt after the recorded deadline plus a buffer and waits for new local records.

The computer must be awake and the app running. Missed schedules have a configurable five-minute grace period, after which they need explicit rescheduling. Failed or interrupted tasks never automatically replay; inspect their logs first, since partial work may have occurred. Lightweight messages time out after 120 seconds; tasks after one hour.

## Data and network

Monitoring reads only local `sessions/**/*.jsonl`, `state_5.sqlite` (read-only), `.codex-global-state.json` (project membership/order), and `models_cache.json` beneath `CODEX_HOME` (default `~/.codex`). The latest 100 rollouts are scanned incrementally for quota and turn state, every five seconds by default; the conversation picker is not limited to those 100 files. Older unscanned turn states remain unknown. Sentinel makes no account/rate-limit polling requests and does not inspect credentials.

Only scheduled turns and resumes invoke the official CLI, which may make its normal authentication/model/network requests. Local snapshots may be stale, particularly after account/model changes. Without a reliable model-to-quota mapping, scheduling conservatively waits for all known exhausted windows.

Settings, schedules, and logs live in `~/.codex-sentinel` (`CODEX_SENTINEL_HOME` overrides it). Existing scheduled tasks retain their saved buffer; pending automatic resumes follow updated resume settings. Corrupt files are reported, not silently overwritten.

The legacy `--daemon` retains its prior desktop takeover/relaunch behavior. Use the desktop mode for the new scheduler, durable execution records, and lock waiting.

## Test and build

```sh
pytest -q
python scripts/render_gui.py
```

Tests use isolated fixtures and fake executors; no real model requests. The renderer writes all five pages using synthetic data.

Windows build:

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
.\.venv\Scripts\python.exe scripts/build_windows.py
```

Outputs: `dist/desktop/CodexSentinel/` and `dist/CodexSentinel-windows-x64.zip`. Packaging smoke check: `CodexSentinel.exe --smoke-test` (opens then closes without monitoring or execution).

[MIT License](LICENSE).
