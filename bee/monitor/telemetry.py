"""Structured agent telemetry (audit 2026-10-06).

Subscribes to the kernel's typed event bus and records structured rows into
the existing metrics stream (monitor/metrics.record — which redacts every
string value before writing). What this adds on top of the loop-level
records (task/tool/route/guard/verify/llm):

  agent_task   terminal row per kernel task: ok, state, verification verdict,
               retry count, total task latency (TASK_CREATED -> terminal event)
  permission   every permission REQUEST / GRANT / DENY at both layers:
               capability asks (capability=automation.manage, risk=R3, ...)
               and tool-level guard asks (tool=shell, risk_level=HIGH, ...)

Privacy contract: this module never receives free-form content — only event
ids, enums, tool/capability names and durations. The metrics sink adds
redaction as the last line of defense anyway. Nothing here can ever log a
password, API key, token, or user content.

Best-effort by construction: any exception inside the subscriber is swallowed
(telemetry must never break the agent), and it is attached in
AgentKernel.__init__ with a lazy import so a monitor regression can never
take down the kernel.
"""
from __future__ import annotations

import time

from ..kernel.models import AgentEventKind
from .metrics import record

_TERMINAL = (AgentEventKind.TASK_COMPLETED, AgentEventKind.TASK_FAILED,
             AgentEventKind.TASK_CANCELLED)
_PERM = {AgentEventKind.PERMISSION_REQUESTED: "requested",
         AgentEventKind.PERMISSION_GRANTED: "granted",
         AgentEventKind.PERMISSION_DENIED: "denied"}


class KernelTelemetry:
    def __init__(self, sink=None):
        self._sink = sink or record
        self._started: dict[str, float] = {}

    def attach(self, bus) -> None:
        try:
            bus.subscribe(self._on)       # kernel EventBus: every event
        except TypeError:
            bus.subscribe("*", self._on)  # pattern buses (automation-style)

    def _on(self, ev) -> None:
        try:
            kind = ev.kind
            if kind == AgentEventKind.TASK_CREATED:
                self._started[ev.task_id] = time.time()
            elif kind in _TERMINAL:
                t0 = self._started.pop(ev.task_id, None)
                self._sink(
                    "agent_task",
                    task_id=ev.task_id,
                    session_id=ev.session_id,
                    ok=(kind == AgentEventKind.TASK_COMPLETED),
                    state=ev.data.get("state"),
                    verification=ev.data.get("verification"),
                    retried=ev.data.get("retried", 0),
                    seconds=round(time.time() - t0, 2) if t0 else None,
                )
            elif kind in _PERM:
                self._sink(
                    "permission",
                    task_id=ev.task_id,
                    decision=_PERM[kind],
                    capability=ev.data.get("capability"),
                    tool=ev.data.get("tool"),
                    risk_level=ev.data.get("risk_level") or ev.data.get("risk"),
                )
        except Exception:
            pass
