# README screenshots

These images are captures of the real Codex Sentinel PySide6 widgets, rendered
with synthetic data. They are not browser mockups or captures of private chats.
The original design rounds and earlier documentation images remain unchanged.

## Inventory

Each view has four variants: English / Chinese and dark / light. Files use
`<language>/<view>-<theme>.png`, for example `zh/overview-dark.png`.

| View | Contents |
| --- | --- |
| `overview` | Conversation recovery, reset countdown, and quota groups |
| `activation` | Continuous activation with directory, model, and first-run controls |
| `planner` | Task configuration and scheduling |
| `queue` | Populated manual queue and task details |
| `sessions` | Local conversations, project groups, and full conversation metadata |
| `settings` | Execution, paths, language, appearance, and update preferences |
| `recovery-settings` | Continuation prompt, buffer, and execution permissions |
| `history` | Recovery / activation history and execution logs |
| `updates` | Installed version and default update dialog |
| `tray` | Native system tray menu |

The two project READMEs reference all 40 PNGs. They use GitHub's documented
[`picture` markup](https://docs.github.com/en/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/quickstart-for-writing-on-github)
to select the appropriate theme, with an accessible light-theme fallback.

## Reproduce

Run from the repository root using an environment with the project's existing
dependencies installed:

```powershell
.\.venv\Scripts\python.exe -B scripts/render_readme.py
```

Linux / macOS:

```sh
.venv/bin/python -B scripts/render_readme.py
```

Use `--output <directory>` to write images elsewhere. No extra rendering
dependencies are required. Font rendering, native timezone labels, and paths can
vary with the operating system. The checked-in set was captured on Windows at
1160 × 820 for the main pages; dialogs use their own sizes.

The script runs Qt offscreen, disables background workers, enables dry-run mode,
and supplies a fixed clock and synthetic chats, quotas, queue items, and logs.
`CODEX_HOME`, `CODEX_SENTINEL_HOME`, and settings are isolated under the ignored
`.test-artifacts/readme-fixtures/` directory. It does not start monitoring,
query GitHub, invoke the CLI, or read the user's actual conversations. The update
dialog is rendered in its packaged-build presentation without inventing an
available release.

Render metadata is written to `.test-artifacts/readme-screenshot-checks.json`.
The script also checks that the main pages have no outer horizontal overflow
at the capture size.
