"""Typed kernel event bus (Phase 2) — a thin facade over the project's ONE
shared EventBus (bee/events.py, audit item 9).

The kernel emits AgentEvent objects; subscribers (REPL printer, web SSE,
realtime voice, telemetry, proactive automation) subscribe. Subscribers are
best-effort: one broken subscriber never breaks the agent. The public API is
unchanged from Phase 2 (`subscribe(fn)`, `emit(event)`, `.log`, `.by_kind`).
"""
from __future__ import annotations

from ..events import EventBus as _SharedBus
from .models import AgentEvent, AgentEventKind


class EventBus:
    def __init__(self, max_log: int = 500):
        self._bus = _SharedBus(max_log)

    @property
    def log(self) -> list[AgentEvent]:
        return self._bus.log

    def subscribe(self, fn: callable) -> callable:
        return self._bus.subscribe_all(fn)

    def unsubscribe(self, fn: callable) -> None:
        self._bus.unsubscribe_all(fn)

    def emit(self, event: AgentEvent) -> AgentEvent:
        self._bus.emit(event, name=event.kind.value)
        return event

    def by_kind(self, kind: AgentEventKind) -> list[AgentEvent]:
        return [e for e in self.log if e.kind == kind]
