"""Durable automation + proactive agent (Phase 6).

Objects (per the Phase 6 spec):
    Job, JobTrigger, JobExecution, JobQueue, JobWorker,
    Notification, ExecutionHistory,
    JobStore (persistence), EventBus / BusEvent / ProactiveRule /
    ProactivePolicy (internal events + default-deny proactive policy),
    next_run / parse_ics (pure trigger math), automation_tools (the
    user-facing, capability-gated tool).

A job persists enough to survive a restart; the worker executes it through
the SAME AgentKernel as interactive requests. See bee/automation/worker.py
and docs/JARVIS_ARCHITECTURE.md §18.
"""
from .events import (EVENT_KINDS, AppEventSource, BatterySource, BusEvent, EventBus,
                     DeviceSource, FileChangeSource, NetworkSource, ProactivePolicy,
                     ProactiveRule, TimerSource, available_sources, start_sources)
from .models import (COMPLETED, CANCELLED, DISABLED, FAILED, MISSED, PENDING,
                     RUNNING, SUCCEEDED, TRIGGER_KINDS, WEEKDAY_NAMES,
                     ExecutionHistory, Job, JobExecution, JobTrigger,
                     Notification, iso, parse_dt)
from .queue import JobQueue
from .schedule import get_tz, next_run, parse_ics, worker_now
from .store import JobStore
from .worker import FUNCTIONS, JobWorker
from .tools import automation_job, automation_tools

__all__ = [
    "EVENT_KINDS", "AppEventSource", "BatterySource", "BusEvent", "EventBus",
    "DeviceSource", "FileChangeSource", "NetworkSource", "start_sources",
    "ProactivePolicy", "ProactiveRule", "TimerSource", "available_sources",
    "COMPLETED", "CANCELLED", "DISABLED", "FAILED", "MISSED", "PENDING",
    "RUNNING", "SUCCEEDED", "TRIGGER_KINDS", "WEEKDAY_NAMES",
    "ExecutionHistory", "Job", "JobExecution", "JobTrigger", "Notification",
    "iso", "parse_dt", "JobQueue", "get_tz", "next_run", "parse_ics",
    "JobStore", "FUNCTIONS", "JobWorker", "automation_job", "automation_tools",
]
