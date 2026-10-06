"""Local settings. Saving failures are surfaced to the caller."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

DEFAULT_CONFIG = {
    "language": "auto",
    "poll_interval": 5,
    "buffer_seconds": 30,
    "auto_resume": False,
    "resume_prompt": "",
    "minimize_to_tray": True,
    "show_notifications": True,
    "play_sound": False,
    "sessions_dir": "",
    "cli_path": "",
    "take_over_desktop": True,
    "queue_enabled": True,
    "missed_grace_seconds": 300,
}


def data_dir() -> Path:
    return Path(
        os.environ.get("CODEX_SENTINEL_HOME", str(Path.home() / ".codex-sentinel"))
    )


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


class ConfigManager:
    def __init__(self, directory: Path | None = None):
        self.config_dir = directory or data_dir()
        self.config_file = self.config_dir / "config.json"
        self._config = {}

    def load(self) -> dict:
        config = DEFAULT_CONFIG.copy()
        if self.config_file.exists():
            data = json.loads(self.config_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Settings must be a JSON object")
            config.update({k: v for k, v in data.items() if k in DEFAULT_CONFIG})
        self._config = self.validate(config)
        return self._config.copy()

    @staticmethod
    def validate(config: dict) -> dict:
        for key, default in DEFAULT_CONFIG.items():
            if not isinstance(config.get(key), type(default)):
                raise ValueError(f"Invalid setting: {key}")
        if config["language"] not in ("auto", "zh", "en"):
            raise ValueError("Invalid language")
        if not 1 <= config["poll_interval"] <= 300:
            raise ValueError("Poll interval must be between 1 and 300 seconds")
        if not 0 <= config["buffer_seconds"] <= 600:
            raise ValueError("Buffer must be between 0 and 600 seconds")
        if not 0 <= config["missed_grace_seconds"] <= 86400:
            raise ValueError("Invalid missed-task grace period")
        return config

    def save(self, updates: dict) -> None:
        config = {**(self._config or DEFAULT_CONFIG), **updates}
        self.validate(config)
        write_json(self.config_file, config)
        self._config = config

    def get(self, key, default=None):
        if not self._config:
            self.load()
        return self._config.get(key, default)

    def set(self, key, value):
        self.save({key: value})

    def reset_to_defaults(self):
        self.save(DEFAULT_CONFIG.copy())
