"""Durable automation models (Phase 6).

Job / JobTrigger / JobExecution / Notification + ExecutionHistory. A Job
persists everything needed to survive an application restart: identity,
owner/session, task description, STRUCTURED action, trigger, timezone,
enabled flag, permissions, retry policy, max runtime, timestamps, and the
computed next_run.

Structured action types (no free code):
  {"type": "agent_task", "task": "..."}   -> AgentKernel.run() — the SAME
      AgentSession/Task/Permission/Tools/Verification/Receipt path as
      interactive requests (session id: the job's owner)
  {"type": "notify", "message": "..."}    -> notification only (no LLM)
  {"type": "function", "fn": "<dotted>"}  -> a REGISTERED real-work function
      (bee.automation.registry) — this is how nightly jobs (consolidation,
      vector rebuild) become durable jobs instead of no-op fallbacks
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

# ------------------------------------------------------------------- states
PENDING = "pending"
RUNNING = "running"
SUCCEEDED = "succeeded"
FAILED = "failed"
COMPLETED = "completed"      # one-time job consumed
DISABLED = "disabled"
CANCELLED = "cancelled"
MISSED = "missed"            # one-time job whose window passed without run

JOB_STATES = {PENDING, RUNNING, SUCCEEDED, FAILED, COMPLETED, DISABLED,
              CANCELLED, MISSED}
TERMINAL = {COMPLETED, CANCELLED, FAILED}   # FAILED ends unless retried

TRIGGER_KINDS = {"one_time", "daily", "weekly", "interval", "calendar"}

WEEKDAY_NAMES = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday",
                 4: "Friday", 5: "Saturday", 6: "Sunday"}


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ------------------------------------------------------------------- trigger
@dataclass
class JobTrigger:
    kind: str = "one_time"           # one_time|daily|weekly|interval|calendar
    at: str = ""                     # one_time: ISO datetime (naive = job tz)
    time: str = ""                   # daily/weekly: "HH:MM" (job tz)
    days: list = field(default_factory=list)   # weekly: 0=Mon..6=Sun
    every_seconds: int = 0           # interval
    calendar: str = ""               # calendar: "ics:<path>" (where supported)
    reminder_offset_minutes: int = 0 # calendar: fire N minutes BEFORE events

    def to_dict(self) -> dict:
        return {"kind": self.kind, "at": self.at, "time": self.time,
                "days": list(self.days), "every_seconds": self.every_seconds,
                "calendar": self.calendar,
                "reminder_offset_minutes": self.reminder_offset_minutes}

    @classmethod
    def from_dict(cls, d: dict) -> "JobTrigger":
        return cls(kind=d.get("kind", "one_time"), at=d.get("at", ""),
                   time=d.get("time", ""), days=list(d.get("days") or []),
                   every_seconds=int(d.get("every_seconds") or 0),
                   calendar=d.get("calendar", ""),
                   reminder_offset_minutes=int(d.get("reminder_offset_minutes") or 0))

    def describe(self) -> str:
        if self.kind == "one_time":
            return f"once at {self.at}"
        if self.kind == "daily":
            return f"daily at {self.time}"
        if self.kind == "weekly":
            ds = ", ".join(WEEKDAY_NAMES.get(int(d), str(d)) for d in self.days)
            return f"weekly on {ds} at {self.time}"
        if self.kind == "interval":
            s = self.every_seconds
            unit = "s" if s < 60 else ("min" if s < 3600 else "h")
            return f"every {int(s // (1 if s < 60 else 60 if s < 3600 else 3600))}{unit}"
        off = f" ({self.reminder_offset_minutes}m before)" if self.reminder_offset_minutes else ""
        return f"calendar {self.calendar or '(unset)'}{off}"


# ----------------------------------------------------------------------- job
@dataclass
class Job:
    id: str = field(default_factory=lambda: _new_id("job"))
    owner: str = "main"               # owner/session id (AgentSession for runs)
    description: str = ""
    action: dict = field(default_factory=dict)   # structured action (see module)
    trigger: JobTrigger = field(default_factory=JobTrigger)
    timezone: str = "Asia/Kolkata"
    enabled: bool = True
    permissions: dict = field(default_factory=lambda: {
        "guard_mode": "unattended",      # scheduled runs never block on input()
        "preapproved_capabilities": [],  # explicit grants for THIS job only
    })
    retry_policy: dict = field(default_factory=lambda: {
        "max_attempts": 2, "backoff_seconds": 60,
    })
    max_runtime: float = 600.0         # hard per-run timeout (seconds)
    created_at: str = field(default_factory=_now_iso)
    next_run: str = ""                 # ISO, tz-aware
    last_run: str = ""
    state: str = PENDING
    attempts: int = 0                  # lifetime attempts (retry budget)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "owner": self.owner, "description": self.description,
            "action": self.action, "trigger": self.trigger.to_dict(),
            "timezone": self.timezone, "enabled": self.enabled,
            "permissions": self.permissions, "retry_policy": self.retry_policy,
            "max_runtime": self.max_runtime, "created_at": self.created_at,
            "next_run": self.next_run, "last_run": self.last_run,
            "state": self.state, "attempts": self.attempts,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Job":
        return cls(id=d.get("id") or _new_id("job"), owner=d.get("owner", "main"),
                   description=d.get("description", ""),
                   action=dict(d.get("action") or {}),
                   trigger=JobTrigger.from_dict(d.get("trigger") or {}),
                   timezone=d.get("timezone", "Asia/Kolkata"),
                   enabled=bool(d.get("enabled", True)),
                   permissions=dict(d.get("permissions") or {
                       "guard_mode": "unattended", "preapproved_capabilities": []}),
                   retry_policy=dict(d.get("retry_policy") or {
                       "max_attempts": 2, "backoff_seconds": 60}),
                   max_runtime=float(d.get("max_runtime", 600.0)),
                   created_at=d.get("created_at", ""), last_run=d.get("last_run", ""),
                   next_run=d.get("next_run", ""),
                   state=d.get("state", PENDING),
                   attempts=int(d.get("attempts", 0)))

    @property
    def next_run_dt(self) -> Optional[datetime]:
        if not self.next_run:
            return None
        try:
            return datetime.fromisoformat(self.next_run)
        except ValueError:
            return None

    def summary(self) -> dict:
        return {"id": self.id, "description": self.description,
                "trigger": self.trigger.describe(), "state": self.state,
                "enabled": self.enabled, "next_run": self.next_run,
                "last_run": self.last_run, "owner": self.owner,
                "attempts": self.attempts}


# ------------------------------------------------------------------- execution
@dataclass
class JobExecution:
    id: str = field(default_factory=lambda: _new_id("exec"))
    job_id: str = ""
    attempt: int = 1
    started_at: str = field(default_factory=_now_iso)
    finished_at: str = ""
    status: str = "running"     # running|succeeded|failed|timeout|missed|interrupted
    task_id: str = ""           # kernel Task id (agent_task actions)
    error: str = ""
    output_preview: str = ""    # REDACTED preview (<=160 chars), never full output

    def to_dict(self) -> dict:
        return {"id": self.id, "job_id": self.job_id, "attempt": self.attempt,
                "started_at": self.started_at, "finished_at": self.finished_at,
                "status": self.status, "task_id": self.task_id,
                "error": self.error[:300], "output_preview": self.output_preview}

    @classmethod
    def from_dict(cls, d: dict) -> "JobExecution":
        return cls(id=d.get("id") or _new_id("exec"), job_id=d.get("job_id", ""),
                   attempt=int(d.get("attempt", 1)),
                   started_at=d.get("started_at", ""),
                   finished_at=d.get("finished_at", ""),
                   status=d.get("status", "running"),
                   task_id=d.get("task_id", ""), error=d.get("error", ""),
                   output_preview=d.get("output_preview", ""))


class ExecutionHistory:
    """Persisted per-job execution history (append-only JSONL in JobStore)."""

    def __init__(self, entries: list[JobExecution] | None = None):
        self.entries = list(entries or [])

    def append(self, ex: JobExecution) -> None:
        self.entries.append(ex)

    def for_job(self, job_id: str) -> list[JobExecution]:
        return [e for e in self.entries if e.job_id == job_id]

    def last(self, job_id: str, n: int = 5) -> list[JobExecution]:
        return self.for_job(job_id)[-n:]

    def count(self, job_id: str, status: str | None = None) -> int:
        return sum(1 for e in self.for_job(job_id)
                   if status is None or e.status == status)


# ----------------------------------------------------------------- notification
NOTIF_KINDS = {"success", "failure", "missed", "proactive", "job_event"}


@dataclass
class Notification:
    id: str = field(default_factory=lambda: _new_id("ntf"))
    kind: str = "job_event"
    message: str = ""
    job_id: str = ""
    created_at: str = field(default_factory=_now_iso)
    read: bool = False

    def to_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "message": self.message,
                "job_id": self.job_id, "created_at": self.created_at,
                "read": self.read}

    @classmethod
    def from_dict(cls, d: dict) -> "Notification":
        return cls(id=d.get("id") or _new_id("ntf"), kind=d.get("kind", "job_event"),
                   message=d.get("message", ""), job_id=d.get("job_id", ""),
                   created_at=d.get("created_at", ""),
                   read=bool(d.get("read", False)))


def parse_dt(s: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def iso(dt: Optional[datetime]) -> str:
    return dt.astimezone().isoformat(timespec="seconds") if dt else ""
