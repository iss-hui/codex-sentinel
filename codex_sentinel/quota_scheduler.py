"""Durable one-shot scheduling. Never claim that a message resets server quota."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from codex_sentinel.config import data_dir, write_json
from codex_sentinel.session_scanner import blocking_reset


@dataclass
class TaskItem:
    id: str
    name: str
    prompt: str
    cwd: str
    model: str
    status: str
    created_at: float
    completed_at: float | None = None
    scheduled_at: float | None = None
    session_id: str = ""
    kind: str = "task"
    auto_key: str = ""
    started_at: float | None = None
    last_error: str = ""
    log_file: str = ""
    deferred_until: float = 0
    buffer_seconds: int = 30
    sandbox: str = "read-only"


class QuotaScheduler:
    def __init__(self, directory: Path | None = None):
        self.data_dir = directory or data_dir()
        self.queue_file = self.data_dir / "task_queue.json"
        self.task_queue = []
        self.load()

    def load(self):
        if not self.queue_file.exists():
            return
        data = json.loads(self.queue_file.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("Task queue must be a JSON array")
        names = {f.name for f in fields(TaskItem)}
        self.task_queue = [
            TaskItem(**{k: v for k, v in item.items() if k in names}) for item in data
        ]
        changed = False
        for task in self.task_queue:
            if task.status == "running":
                task.status = "interrupted"
                task.last_error = "Previous execution was interrupted; inspect the log before retrying."
                changed = True
        if changed:
            self.save()

    def save(self):
        write_json(self.queue_file, [asdict(t) for t in self.task_queue])

    def add_task(self, name, prompt, cwd, model="", **kwargs):
        if not prompt.strip():
            raise ValueError("Prompt cannot be empty")
        if not Path(cwd).is_dir():
            raise ValueError("Working directory does not exist")
        if kwargs.get("sandbox", "read-only") not in ("read-only", "workspace-write"):
            raise ValueError("Invalid sandbox")
        task = TaskItem(
            str(uuid.uuid4()),
            name.strip() or prompt[:32],
            prompt,
            cwd,
            model,
            "pending",
            time.time(),
            **kwargs,
        )
        self.task_queue.append(task)
        try:
            self.save()
        except Exception:
            self.task_queue.remove(task)
            raise
        return task

    def remove_task(self, task_id):
        task = self.get(task_id)
        if task.status == "running":
            raise ValueError("Cannot delete a running task")
        # Keep cancelled records for auto-resume deduplication and audit.
        self.update(task, status="cancelled")

    def get(self, task_id):
        task = next((t for t in self.task_queue if t.id == task_id), None)
        if task is None:
            raise KeyError(f"Task not found: {task_id}")
        return task

    def update(self, task, **changes):
        old = {key: getattr(task, key) for key in changes}
        for key, value in changes.items():
            setattr(task, key, value)
        try:
            self.save()
        except Exception:
            for key, value in old.items():
                setattr(task, key, value)
            raise

    def retry(self, task_id, now=None):
        task = self.get(task_id)
        if task.status == "running":
            raise ValueError("Task is running")
        self.update(
            task,
            status="pending",
            scheduled_at=now or time.time(),
            deferred_until=0,
            completed_at=None,
            last_error="",
        )

    def reorder_tasks(self, ids):
        ordered = list(dict.fromkeys(ids))
        self.task_queue.sort(
            key=lambda t: ordered.index(t.id) if t.id in ordered else len(ordered)
        )
        self.save()

    def sync_auto_resume(self, snapshot, settings, now):
        sessions = {s["session_id"]: s for s in snapshot.get("sessions", [])}
        for task in self.task_queue:
            if task.kind != "resume" or task.status not in (
                "pending",
                "waiting",
                "paused",
            ):
                continue
            session = sessions.get(task.session_id)
            if session and session["task_status"] != "rate_limited":
                self.update(
                    task,
                    status="cancelled",
                    last_error="Session has continued.",
                )
            elif not settings["auto_resume"]:
                if task.status != "paused":
                    self.update(task, status="paused")
            else:
                from codex_sentinel.i18n import t

                desired = {
                    "buffer_seconds": settings["buffer_seconds"],
                    "prompt": settings["resume_prompt"] or t("default_resume_prompt"),
                    "sandbox": settings["resume_sandbox"],
                }
                if task.status == "paused":
                    desired["status"] = "pending"
                changes = {k: v for k, v in desired.items() if getattr(task, k) != v}
                if changes:
                    self.update(task, **changes)
        if not settings["auto_resume"]:
            return
        known = {t.auto_key for t in self.task_queue if t.auto_key}
        for session in sessions.values():
            if session["task_status"] != "rate_limited":
                continue
            if not session.get("cwd") or not Path(session["cwd"]).is_dir():
                continue
            limits = session.get("limits", {})
            # At least one known exhausted window is required. Unknown reset times are not guessed.
            windows = [
                w
                for w in (limits.get("primary"), limits.get("secondary"))
                if isinstance(w, dict)
                and (w.get("used_percent") or 0) >= 100
                and w.get("resets_at")
            ]
            if not windows:
                continue
            reset = max(w["resets_at"] for w in windows)
            key = f"{session['session_id']}:{session.get('limited_at', 0)}:{reset}"
            if (
                key in known
                or reset + settings["buffer_seconds"] + settings["missed_grace_seconds"]
                < now
            ):
                continue
            from codex_sentinel.i18n import get_lang, t

            self.add_task(
                "到期恢复" if get_lang() == "zh" else "Auto resume",
                settings["resume_prompt"] or t("default_resume_prompt"),
                session["cwd"],
                session["model"],
                scheduled_at=reset,
                session_id=session["session_id"],
                kind="resume",
                auto_key=key,
                buffer_seconds=settings["buffer_seconds"],
                sandbox=settings["resume_sandbox"],
            )
            known.add(key)

    def due_task(self, snapshot, settings, now=None):
        now = time.time() if now is None else now
        if not settings["queue_enabled"] or any(
            t.status == "running" for t in self.task_queue
        ):
            return None
        sessions = {s["session_id"]: s for s in snapshot.get("sessions", [])}
        for task in self.task_queue:
            if task.status not in ("pending", "waiting") or task.scheduled_at is None:
                continue
            if task.kind == "resume" and not settings["auto_resume"]:
                continue
            # Resolve quota conservatively: known session bucket, otherwise all local buckets.
            session = sessions.get(task.session_id, {})
            key = session.get("limits", {}).get("limit_id")
            buckets = snapshot.get("buckets", {})
            limits = (
                [buckets[key]]
                if key and key in buckets and task.model == session.get("model")
                else list(buckets.values())
            )
            block = max(
                (blocking_reset(b, now - task.buffer_seconds) for b in limits),
                default=0,
            )
            if block > task.deferred_until:
                self.update(task, deferred_until=block, status="waiting")
            due = max(task.scheduled_at, task.deferred_until) + task.buffer_seconds
            if now < due:
                continue
            if now - due > settings["missed_grace_seconds"]:
                self.update(
                    task,
                    status="missed",
                    last_error="Scheduled time was missed; reschedule explicitly.",
                )
                continue
            return task
        return None
