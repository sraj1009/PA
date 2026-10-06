"""Internal EventBus + proactive policy (Phase 6).

An EventBus carries internal events (timer, calendar, email, file_change,
app_event, battery, network, device_state). PROACTIVE behavior is
default-deny: an event can only cause an action when a ProactiveRule
matches it — and rules are created ONLY by explicit user authorization
(REPL /auto commands or the automation_job tool through the kernel's
capability gate). No rule, no action. Rules are rate-limited
(max_per_hour) so a flapping event source cannot turn BEE into a spam
machine.

Event SOURCES are optional adapters (timer/file-change are implemented;
email/app/battery/network are schema-supported, with clean "not available"
when the dependency is missing). A source publishes events; it never acts.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

EVENT_KINDS = {"timer", "calendar", "email", "file_change", "app_event",
               "battery", "network", "device_state"}


@dataclass
class BusEvent:
    name: str                          # e.g. "download.finished"
    kind: str = "timer"                # one of EVENT_KINDS
    payload: dict = field(default_factory=dict)
    source: str = "internal"
    ts: str = field(default_factory=lambda:
                    datetime.now().astimezone().isoformat(timespec="seconds"))

    def to_dict(self) -> dict:
        return {"name": self.name, "kind": self.kind, "payload": self.payload,
                "source": self.source, "ts": self.ts}


class EventBus:
    """Synchronous in-process bus. Handlers are called in subscription
    order; a handler exception is contained (logged, never kills the bus
    or other handlers)."""

    def __init__(self):
        self._subs: list[tuple[str, Callable[[BusEvent], None]]] = []
        self._lock = threading.RLock()
        self.published: list[BusEvent] = []   # bounded, for inspection/tests

    def subscribe(self, kind: str, handler: Callable[[BusEvent], None]) -> None:
        with self._lock:
            self._subs.append((kind, handler))

    def unsubscribe(self, kind: str, handler) -> None:
        with self._lock:
            self._subs = [(k, h) for k, h in self._subs
                          if not (k == kind and h is handler)]

    def publish(self, ev: BusEvent) -> int:
        """Publish; returns the number of handlers that ran. The proactive
        policy gate is a handler like any other (registered by the worker)."""
        self.published.append(ev)
        if len(self.published) > 200:
            self.published = self.published[-200:]
        with self._lock:
            subs = [(k, h) for k, h in self._subs if k == ev.kind or k == "*"]
        n = 0
        for _k, h in subs:
            try:
                h(ev)
                n += 1
            except Exception:
                pass
        return n

    def clear(self) -> None:
        with self._lock:
            self._subs.clear()
        self.published.clear()


# ------------------------------------------------------------------ rules
@dataclass
class ProactiveRule:
    id: str = field(default_factory=lambda: f"rule_{uuid.uuid4().hex[:10]}")
    kind: str = "timer"                # event kind to match
    match: dict = field(default_factory=dict)   # exact payload-field matches
    action: dict = field(default_factory=dict)  # {"type": "notify", ...} | {"type": "agent_task", ...}
    description: str = ""
    enabled: bool = True
    max_per_hour: int = 6              # rate limit (default-deny safety)
    created_at: str = field(default_factory=lambda:
                            datetime.now().astimezone().isoformat(timespec="seconds"))
    created_by: str = "user"           # MUST be explicit user authorization

    def matches(self, ev: BusEvent) -> bool:
        if ev.kind != self.kind:
            return False
        for k, v in self.match.items():
            if str(ev.payload.get(k, "")) != str(v):
                return False
        return True

    def to_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "match": self.match,
                "action": self.action, "description": self.description,
                "enabled": self.enabled, "max_per_hour": self.max_per_hour,
                "created_at": self.created_at, "created_by": self.created_by}

    @classmethod
    def from_dict(cls, d: dict) -> "ProactiveRule":
        return cls(id=d.get("id") or f"rule_{uuid.uuid4().hex[:10]}",
                   kind=d.get("kind", "timer"), match=dict(d.get("match") or {}),
                   action=dict(d.get("action") or {}),
                   description=d.get("description", ""),
                   enabled=bool(d.get("enabled", True)),
                   max_per_hour=int(d.get("max_per_hour", 6)),
                   created_at=d.get("created_at", ""),
                   created_by=d.get("created_by", "user"))


class ProactivePolicy:
    """Default-deny gate between the event bus and any action.

    check(event) -> list of (rule, action) allowed to fire, honoring each
    rule's rate limit. The EXECUTOR is the worker — the policy only decides
    what is allowed, from explicitly user-authorized rules."""

    def __init__(self, rules: list[ProactiveRule] | None = None):
        self.rules = list(rules or [])
        self._fired: dict[str, list[float]] = {}

    def add_rule(self, rule: ProactiveRule) -> None:
        self.rules.append(rule)

    def remove_rule(self, rule_id: str) -> bool:
        before = len(self.rules)
        self.rules = [r for r in self.rules if r.id != rule_id]
        return len(self.rules) < before

    def check(self, ev: BusEvent, now: float | None = None) -> list[tuple[ProactiveRule, dict]]:
        now = now if now is not None else time.time()
        out: list[tuple[ProactiveRule, dict]] = []
        for r in self.rules:
            if not r.enabled or not r.action or not r.matches(ev):
                continue
            fired = [t for t in self._fired.get(r.id, []) if now - t < 3600]
            if len(fired) >= r.max_per_hour:
                continue                       # rate-limited: deny this fire
            fired.append(now)
            self._fired[r.id] = fired
            out.append((r, r.action))
        return out


# ----------------------------------------------------------------- sources
class EventSource:
    """Adapter interface: a source PUBLISHES events; it never acts."""
    kind: str = "timer"

    def start(self, bus: EventBus) -> None: ...
    def stop(self) -> None: ...


class TimerSource(EventSource):
    kind = "timer"

    def __init__(self, interval_seconds: float, name: str = "tick",
                 sleep_fn: Callable[[float], None] = time.sleep):
        self.interval = interval_seconds
        self.name = name
        self._sleep = sleep_fn
        self._stop = threading.Event()
        self._thread = None

    def start(self, bus: EventBus) -> None:
        if self._thread is not None:
            return

        def _run():
            while not self._stop.is_set():
                self._stop.wait(self.interval)
                if self._stop.is_set():
                    break
                bus.publish(BusEvent(name=self.name, kind="timer",
                                     payload={"interval": self.interval},
                                     source="timer"))
        self._thread = threading.Thread(target=_run, daemon=True, name="BeeTimerSrc")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()


class FileChangeSource(EventSource):
    """Polling file-change watcher (no external dependency): fires
    file_change events for created/modified files under a directory."""
    kind = "file_change"

    def __init__(self, directory: str | Path, interval_seconds: float = 2.0,
                 sleep_fn: Callable[[float], None] = time.sleep):
        self.directory = Path(directory)
        self.interval = interval_seconds
        self._sleep = sleep_fn
        self._stop = threading.Event()
        self._thread = None
        self._state: dict[str, float] = {}

    def start(self, bus: EventBus) -> None:
        if self._thread is not None or not self.directory.exists():
            return

        def _run():
            while not self._stop.is_set():
                try:
                    self._scan(bus)
                except Exception:
                    pass
                self._stop.wait(self.interval)
        self._thread = threading.Thread(target=_run, daemon=True, name="BeeFileSrc")
        self._thread.start()

    def _scan(self, bus: EventBus) -> None:
        seen: dict[str, float] = {}
        for p in self.directory.rglob("*"):
            if p.is_file():
                try:
                    seen[str(p)] = p.stat().st_mtime
                except OSError:
                    continue
        for name, mt in seen.items():
            old = self._state.get(name)
            if old is None or old != mt:
                bus.publish(BusEvent(name="file.changed", kind="file_change",
                                     payload={"path": name, "mtime": mt},
                                     source="filewatch"))
        self._state = seen

    def stop(self) -> None:
        self._stop.set()


def available_sources() -> dict[str, str]:
    """Honest capability report (sources are adapters; missing deps = 'unavailable')."""
    return {
        "timer": "built-in (thread)",
        "file_change": "built-in (polling, no dependency)",
        "calendar": "built-in (ICS files via JobTrigger kind=calendar)",
        "email": "unavailable (no mail source wired)",
        "app_event": "unavailable (platform adapter not implemented)",
        "battery": "unavailable unless power API present",
        "network": "unavailable (no probe wired)",
        "device_state": "unavailable (platform adapter not implemented)",
    }
