"""Typed event bus (Phase 2).

The kernel emits AgentEvent objects; subscribers (REPL printer, web SSE,
future realtime-voice / proactive automation) subscribe. Subscribers are
best-effort: one broken subscriber never breaks the agent.
"""
from __future__ import annotations

import logging

from .models import AgentEvent, AgentEventKind

log = logging.getLogger("bee.kernel.events")


class EventBus:
    def __init__(self, max_log: int = 500):
        self._subs: list[callable] = []
        self.log: list[AgentEvent] = []
        self._max_log = max_log

    def subscribe(self, fn: callable):
        if fn not in self._subs:
            self._subs.append(fn)
        return fn

    def unsubscribe(self, fn: callable):
        try:
            self._subs.remove(fn)
        except ValueError:
            pass

    def emit(self, event: AgentEvent) -> AgentEvent:
        self.log.append(event)
        if len(self.log) > self._max_log:
            del self.log[: len(self.log) - self._max_log]
        for fn in list(self._subs):
            try:
                fn(event)
            except Exception as e:  # subscriber errors never break the kernel
                log.debug("event subscriber failed: %s", e)
        return event

    def by_kind(self, kind: AgentEventKind) -> list[AgentEvent]:
        return [e for e in self.log if e.kind == kind]
