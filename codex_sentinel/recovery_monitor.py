"""Persistent latest-interruption recovery, independent of the user's task queue."""

from __future__ import annotations

import copy
import json
import time
from dataclasses import asdict, fields
from pathlib import Path

from codex_sentinel.config import write_json
from codex_sentinel.i18n import t
from codex_sentinel.quota_scheduler import TaskItem
from codex_sentinel.session_catalog import is_visible_thread
from codex_sentinel.session_scanner import is_usage_error


class RecoveryMonitor:
    def __init__(self, directory):
        self.path = Path(directory) / "recovery_state.json"
        self.state = {"latest_at": 0, "target": None, "history": [], "migrated_ids": []}
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Recovery state must be an object")
            self.state.update(data)
        if self.target and self.target["status"] == "running":
            state = copy.deepcopy(self.state)
            state["target"].update(status="interrupted", error="Previous recovery was interrupted; inspect its log.")
            task = TaskItem(**state["target"]["run"])
            task.status = "interrupted"
            task.last_error = state["target"]["error"]
            state["history"].append(asdict(task))
            self._save(state)

    @property
    def target(self):
        return self.state["target"]

    def _save(self, state):
        if state != self.state:
            state["history"] = state["history"][-200:]
            write_json(self.path, state)
            self.state = state

    def migrate_legacy(self, scheduler):
        legacy = [task for task in scheduler.task_queue if task.kind == "resume"]
        if not legacy:
            return
        state = copy.deepcopy(self.state)
        for task in legacy:
            if task.id in state["migrated_ids"]:
                continue
            state["migrated_ids"].append(task.id)
            record = asdict(task)
            if task.status in ("pending", "waiting", "paused"):
                record.update(status="migrated", last_error="Transferred to latest-interruption monitoring.")
            else:
                try:
                    state["latest_at"] = max(state["latest_at"], float(task.auto_key.split(":")[1]))
                except (IndexError, ValueError):
                    pass
            state["history"].append(record)
        # Save the history first. Repeating after a crash does not duplicate it.
        self._save(state)
        previous = scheduler.task_queue
        scheduler.task_queue = [task for task in previous if task.kind != "resume"]
        try:
            scheduler.save()
        except Exception:
            scheduler.task_queue = previous
            raise

    @staticmethod
    def _limits(session, snapshot):
        original = session.get("limits") or {}
        key = original.get("limit_id") or "codex"
        latest = snapshot.get("buckets", {}).get(key)
        return latest if latest and latest.get("observed_at", 0) >= session.get("limits_at", 0) else original

    def observe(self, snapshot, now=None):
        now = time.time() if now is None else now
        if self.target and self.target["status"] == "running":
            return
        sessions = [s for s in snapshot.get("sessions", [])
                    if is_visible_thread(s) and s.get("limited_at", 0) > 0]
        state = copy.deepcopy(self.state)
        latest = max(sessions, key=lambda s: (s["limited_at"], s["session_id"]), default=None)
        if latest and latest["limited_at"] > state["latest_at"]:
            state["latest_at"] = latest["limited_at"]
            state["target"] = None
            if latest.get("task_status") == "rate_limited":
                state["target"] = {
                    "key": f"{latest['session_id']}:{latest['limited_at']}",
                    "session_id": latest["session_id"], "limited_at": latest["limited_at"],
                    "status": "waiting", "attempts": 0, "not_before": 0,
                    "reset_at": None, "next_reset_at": None, "error": "",
                }
        target = state["target"]
        if target:
            session = next((s for s in sessions if s["session_id"] == target["session_id"]), None)
            target["available"] = session is not None
            if session:
                target.update(title=session.get("title") or session["session_id"],
                              project=session.get("project_name") or "",
                              cwd=session.get("cwd") or "", model=session.get("model") or "")
                limits = self._limits(session, snapshot)
                windows = [w for w in (limits.get("primary"), limits.get("secondary")) if isinstance(w, dict)]
                exhausted = [w for w in windows if (w.get("used_percent") or 0) >= 100]
                # Unknown or already-stale reset times must never produce a retry loop.
                known = [w.get("resets_at") for w in exhausted]
                reset = max(known) if known and all(at and at > target["limited_at"] for at in known) else None
                future = [w["resets_at"] for w in windows if (w.get("resets_at") or 0) > now]
                target["next_reset_at"] = max(
                    (w["resets_at"] for w in exhausted if (w.get("resets_at") or 0) > now),
                    default=min(future) if future else None,
                )
                if reset is not None:
                    if target["status"] == "awaiting_limit" and reset > (target.get("reset_at") or 0):
                        target.update(status="waiting", attempts=0, not_before=0)
                    target["reset_at"] = reset
                elif target["status"] in ("waiting", "awaiting_limit"):
                    # A newer observation with spare quota confirms the old block cleared.
                    if not exhausted and limits and limits.get("observed_at", session.get("limits_at", 0)) > target["limited_at"]:
                        target["reset_at"] = target.get("reset_at") or now
                    else:
                        target["reset_at"] = None
                status = session.get("task_status")
                retrying_own_error = (
                    target["status"] == "retry" and status == "error"
                    and session.get("status_at", 0) <= target.get("finished_at", 0)
                )
                if target["status"] in ("waiting", "retry", "awaiting_limit") and status != "rate_limited" and not retrying_own_error:
                    target.update(status="cancelled", error="Conversation has continued or was stopped.")
        self._save(state)

    def due_task(self, settings, now=None):
        now = time.time() if now is None else now
        target = self.target
        if (not settings["auto_resume"] or not target or not target.get("available")
                or target["status"] not in ("waiting", "retry") or target["reset_at"] is None
                or not target["cwd"] or not Path(target["cwd"]).is_dir()):
            return None
        due = max(target["reset_at"] + settings["buffer_seconds"], target["not_before"])
        if now < due:
            return None
        return TaskItem(
            id=f"recovery-{target['session_id']}-{target['limited_at']}-{target['attempts'] + 1}",
            name=target["title"], prompt=settings["resume_prompt"] or t("default_resume_prompt"),
            cwd=target["cwd"], model=target["model"], status="pending", created_at=now,
            scheduled_at=target["reset_at"], session_id=target["session_id"], kind="auto_resume",
            auto_key=target["key"], buffer_seconds=settings["buffer_seconds"], sandbox="workspace-write",
        )

    def start(self, task, log_path, now):
        state = copy.deepcopy(self.state)
        task.status, task.started_at, task.log_file = "running", now, str(log_path)
        state["target"].update(status="running", attempts=state["target"]["attempts"] + 1,
                               run=asdict(task), error="")
        self._save(state)

    def complete(self, task, result, now):
        state = copy.deepcopy(self.state)
        target = state["target"]
        code, error = result["code"], result.get("error", "")
        status = "completed" if code == 0 else "interrupted" if code == 130 else "failed"
        if result.get("simulated"):
            status = "simulated"
        elif result.get("cleanup_ok", True):
            if code == 75:
                status = "waiting"
                target["attempts"] -= 1
                target["not_before"] = now + 5
            elif code != 0 and is_usage_error(error):
                status = "awaiting_limit"
            elif code not in (0, 130) and target["attempts"] < 3 and any(
                word in error.lower() for word in ("network", "connection", "temporar", "stream disconnected", "timed out")
            ):
                status = "retry"
                target["not_before"] = now + 30 * 2 ** (target["attempts"] - 1)
        target.update(status=status, error=error, finished_at=now)
        task.status, task.last_error, task.completed_at = status, error, now
        if code != 75:
            state["history"].append(asdict(task))
        self._save(state)

    def history_tasks(self):
        names = {field.name for field in fields(TaskItem)}
        return [TaskItem(**{k: v for k, v in record.items() if k in names}) for record in self.state["history"]]
