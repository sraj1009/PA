"""THE shared EventBus (audit item 9 — one implementation, project-wide).

Before this there were two buses with different subscribe signatures
(kernel: `subscribe(fn)`; automation: `subscribe(pattern, fn)`), bridged ad
hoc. Now there is exactly ONE bus implementation; the domain buses
(`bee.kernel.events.EventBus`, `bee.automation.events.EventBus`) are thin
compatibility facades over it, so existing call sites and tests keep their
exact API.

Semantics:
  * pattern pub/sub: pattern "*" matches every event; otherwise the pattern
    must equal the event's routing `name` (kernel: AgentEventKind.value;
    automation: BusEvent.kind)
  * synchronous, in-process; handlers run in subscription order
  * a handler exception is CONTAINED (logged at debug) — a broken
    subscriber never breaks the emitter or other handlers
  * the in-memory log is bounded (default 500 events)
  * thread-safe (RLock around subscription mutation + dispatch snapshot)
"""
from __future__ import annotations

import logging
import threading

log = logging.getLogger("bee.events")


class EventBus:
    def __init__(self, max_log: int = 500):
        self._subs: list[tuple[str, callable]] = []   # (pattern, handler) — order kept
        self._lock = threading.RLock()
        self.log: list = []                            # bounded event history
        self._max_log = max_log

    # ------------------------------------------------------ subscription
    def subscribe(self, pattern: str, handler: callable) -> callable:
        with self._lock:
            if all(p != pattern or h is not handler for p, h in self._subs):
                self._subs.append((pattern, handler))
        return handler

    def subscribe_all(self, handler: callable) -> callable:
        """Convenience: receive every event (the kernel facade uses this)."""
        return self.subscribe("*", handler)

    def unsubscribe(self, pattern: str, handler: callable) -> None:
        with self._lock:
            self._subs = [(p, h) for p, h in self._subs
                          if not (p == pattern and h is handler)]

    def unsubscribe_all(self, handler: callable) -> None:
        with self._lock:
            self._subs = [(p, h) for p, h in self._subs if h is not handler]

    # ------------------------------------------------------------- emit
    @staticmethod
    def event_name(event) -> str | None:
        """Routing key: explicit name attr (BusEvent) or kind.value (AgentEvent)."""
        n = getattr(event, "name", None)
        if isinstance(n, str):
            return n
        k = getattr(event, "kind", None)
        return getattr(k, "value", None)

    def emit(self, event, name: str | None = None) -> int:
        """Dispatch; returns the number of handlers INVOKED (a handler that
        raises is contained and still counted — the return value is the
        fan-out size, not a success metric)."""
        name = name if name is not None else self.event_name(event)
        with self._lock:
            self.log.append(event)
            if len(self.log) > self._max_log:
                del self.log[: len(self.log) - self._max_log]
            subs = [(p, h) for p, h in self._subs
                    if p == "*" or (name is not None and p == name)]
        n = 0
        for _p, h in subs:
            try:
                h(event)
            except Exception as e:  # contained — never kills the emitter
                log.debug("event subscriber failed: %s", e)
            n += 1
        return n

    def clear(self) -> None:
        with self._lock:
            self._subs.clear()
            self.log.clear()
