"""Activate each locally recorded window once, always in a fresh conversation."""

from __future__ import annotations

import copy
import json
import time
import uuid
from dataclasses import asdict
from pathlib import Path

from codex_sentinel.config import write_json
from codex_sentinel.quota_scheduler import TaskItem
from codex_sentinel.session_scanner import blocking_reset

ACTIVATION_PROMPT = "Reply only: Started. Do not use tools or modify files."


class ActivationMonitor:
    def __init__(self, directory):
        self.path = Path(directory) / "activation_state.json"
        self.state = {"handled": {}, "target": None, "history": []}
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Activation state must be an object")
            self.state.update(data)
        if self.target and self.target["status"] == "running":
            state = copy.deepcopy(self.state)
            state["target"].update(
                status="interrupted",
                last_error="Previous activation was interrupted; inspect its log.",
            )
            state["history"].append(state["target"].copy())
            self._save(state)

    @property
    def target(self):
        return self.state["target"]

    def _save(self, state):
        state["history"] = state["history"][-200:]
        write_json(self.path, state)
        self.state = state

    def plan(self, snapshot, settings, now=None):
        now = time.time() if now is None else now
        if not settings["auto_activate"] or (
            self.target and self.target["status"] == "running"
        ):
            return None
        bucket = settings["activation_bucket"]
        limits = snapshot.get("buckets", {}).get(bucket, {})
        windows = [
            w
            for w in (limits.get("primary"), limits.get("secondary"))
            if isinstance(w, dict)
            and w.get("window_minutes") == 300
            and w.get("resets_at")
        ]
        reset = min((w["resets_at"] for w in windows), default=0)
        scope = json.dumps([bucket])
        initial = settings["activation_start_at"] > self.state["handled"].get(
            "initial", 0
        )
        cycle_at = settings["activation_start_at"] if initial else reset
        if not cycle_at or (
            not initial
            and cycle_at
            <= max(
                self.state["handled"].get(scope, 0),
                self.state["handled"].get("initial_sent_at", 0),
            )
        ):
            return None
        due = (
            max(cycle_at, blocking_reset(limits, now - settings["buffer_seconds"]))
            + settings["buffer_seconds"]
        )
        return {"scope": scope, "cycle_at": cycle_at, "initial": initial, "due": due}

    def due_task(self, snapshot, settings, now=None):
        now = time.time() if now is None else now
        plan = self.plan(snapshot, settings, now)
        if (
            not plan
            or now < plan["due"]
            or not settings["activation_cwd"]
            or not Path(settings["activation_cwd"]).is_dir()
        ):
            return None
        return TaskItem(
            id=str(uuid.uuid4()),
            name="Five-hour window activation",
            prompt=ACTIVATION_PROMPT,
            cwd=settings["activation_cwd"],
            model=settings["activation_model"],
            status="pending",
            created_at=now,
            scheduled_at=plan["cycle_at"],
            kind="activation",
            auto_key=json.dumps(plan),
            buffer_seconds=settings["buffer_seconds"],
            sandbox="read-only",
            session_id="",
        )

    def start(self, task, log_path, now):
        plan = json.loads(task.auto_key)
        state = copy.deepcopy(self.state)
        # Record the attempt before invoking Codex. A crash must not replay a message.
        if plan["initial"]:
            state["handled"]["initial"] = plan["cycle_at"]
            state["handled"]["initial_sent_at"] = now
            state["handled"][plan["scope"]] = max(
                now, state["handled"].get(plan["scope"], 0)
            )
        else:
            state["handled"][plan["scope"]] = plan["cycle_at"]
        record = asdict(task)
        record.update(status="running", started_at=now, log_file=str(log_path))
        state["target"] = record
        self._save(state)
        task.status, task.started_at, task.log_file = "running", now, str(log_path)

    def complete(self, task, result, now):
        record = asdict(task)
        code = result["code"]
        record.update(
            status="simulated"
            if result.get("simulated")
            else "completed"
            if code == 0
            else "interrupted"
            if code == 130
            else "failed",
            completed_at=now,
            last_error=result.get("error")
            or ("" if code == 0 else f"Exit code {code}"),
            session_id=result.get("session_id") or "",
        )
        state = copy.deepcopy(self.state)
        state["target"] = record
        state["history"].append(record.copy())
        self._save(state)
        task.status = record["status"]

    def history_tasks(self):
        return [TaskItem(**record) for record in self.state["history"]]
