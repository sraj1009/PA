"""Internal EventBus + proactive policy (Phase 6).

An EventBus carries internal events (timer, calendar, email, file_change,
app_event, battery, network, device_state). PROACTIVE behavior is
default-deny: an event can only cause an action when a ProactiveRule
matches it — and rules are created ONLY by explicit user authorization
(REPL /auto commands or the automation_job tool through the kernel's
capability gate). No rule, no action. Rules are rate-limited
(max_per_hour) so a flapping event source cannot turn BEE into a spam
machine.

Event SOURCES are adapters that publish events and NEVER act. Implemented
end-to-end: timer, file-change, battery (Windows power API) and network
(connectivity probe) — started in production by `start_sources()`.
Email / app_event / device_state remain schema-only and report themselves as
"unavailable" through `available_sources()`.
"""
from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from ..events import EventBus as _SharedBus

log = logging.getLogger("bee.events")

# match-key shape for threshold rules: {"ram_free_mb<=": 1500}
_CMP_KEY = re.compile(r"^(.+?)(<=|>=|<|>)$")

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
    """Synchronous in-process bus — a thin facade over the project's ONE
    shared EventBus (bee/events.py, audit item 9). Handlers are called in
    subscription order; a handler exception is contained. Public API
    unchanged: subscribe(pattern, fn) / unsubscribe / publish -> int /
    .published / clear."""

    def __init__(self, max_log: int = 200):
        self._bus = _SharedBus(max_log)

    @property
    def published(self) -> list[BusEvent]:
        return self._bus.log

    def subscribe(self, kind: str, handler: Callable[[BusEvent], None]) -> None:
        self._bus.subscribe(kind, handler)

    def unsubscribe(self, kind: str, handler) -> None:
        self._bus.unsubscribe(kind, handler)

    def publish(self, ev: BusEvent) -> int:
        """Publish; returns the number of handlers that ran. The proactive
        policy gate is a handler like any other (registered by the worker)."""
        return self._bus.emit(ev, name=ev.kind)

    def clear(self) -> None:
        self._bus.clear()


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
    # Phase 11: EXTERNAL side effects (email/whatsapp/sms) additionally need
    # explicit authorization — matching is not enough. The policy denies any
    # external action on a rule that has not been authorized for it.
    external_authorized: bool = False

    def matches(self, ev: BusEvent) -> bool:
        """match supports three key shapes:
            {"name": "device.memory_low"}     the event name
            {"ram_free_mb": 900}              exact payload field
            {"ram_free_mb<=": 1500}           numeric comparison (<= >= < >)
        Exact-only matching made threshold events (memory/disk pressure, whose
        value differs every poll) practically unusable, so a rule could only
        fire on a coincidental value.
        """
        if ev.kind != self.kind:
            return False
        for k, v in self.match.items():
            if k == "name":
                if str(ev.name) != str(v):
                    return False
                continue
            m = _CMP_KEY.match(k)
            if m:
                key, op = m.group(1), m.group(2)
                raw = ev.payload.get(key)
                if raw is None:
                    return False
                try:
                    a, b = float(raw), float(v)
                except (TypeError, ValueError):
                    return False
                ok = {"<=": a <= b, ">=": a >= b, "<": a < b, ">": a > b}[op]
                if not ok:
                    return False
                continue
            if str(ev.payload.get(k, "")) != str(v):
                return False
        return True

    def to_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "match": self.match,
                "action": self.action, "description": self.description,
                "enabled": self.enabled, "max_per_hour": self.max_per_hour,
                "created_at": self.created_at, "created_by": self.created_by,
                "external_authorized": self.external_authorized}

    @classmethod
    def from_dict(cls, d: dict) -> "ProactiveRule":
        return cls(id=d.get("id") or f"rule_{uuid.uuid4().hex[:10]}",
                   kind=d.get("kind", "timer"), match=dict(d.get("match") or {}),
                   action=dict(d.get("action") or {}),
                   description=d.get("description", ""),
                   enabled=bool(d.get("enabled", True)),
                   max_per_hour=int(d.get("max_per_hour", 6)),
                   created_at=d.get("created_at", ""),
                   created_by=d.get("created_by", "user"),
                   external_authorized=bool(d.get("external_authorized", False)))


class ProactivePolicy:
    """Default-deny gate between the event bus and any action (Phase 11).

    check(event) -> list of (rule, action) allowed to fire. Denial paths,
    all explicit and testable:
      * no matching rule                        (no rule, no action — ever)
      * rule disabled
      * EXTERNAL action without explicit authorization
        (email/whatsapp/sms/… need rule.external_authorized=True — the
        user must have authorized that specific side effect)
      * quiet hours: non-critical `notify` actions are suppressed
        (critical notifications and agent_tasks still fire)
      * per-rule rate limit  (max_per_hour)
      * GLOBAL rate limit    (global_max_per_hour — anti-spam across rules)

    The EXECUTOR is the worker — the policy only decides what is allowed,
    from explicitly user-authorized rules."""

    # action types that leave the machine (need explicit authorization)
    EXTERNAL_TYPES = {"send_email", "email", "whatsapp", "sms", "message",
                      "external"}

    def __init__(self, rules: list[ProactiveRule] | None = None,
                 quiet_hours: tuple[int, int] | None = None,
                 global_max_per_hour: int = 24):
        """quiet_hours=(start,end) local hours, wrap-aware ((22, 7) = 22:00
        to 07:00). Default OFF — enable per deployment."""
        self.rules = list(rules or [])
        self._fired: dict[str, list[float]] = {}
        self._global: list[float] = []
        self.quiet_hours = tuple(quiet_hours) if quiet_hours else None
        self.global_max_per_hour = int(global_max_per_hour)

    def add_rule(self, rule: ProactiveRule) -> None:
        self.rules.append(rule)

    def remove_rule(self, rule_id: str) -> bool:
        before = len(self.rules)
        self.rules = [r for r in self.rules if r.id != rule_id]
        return len(self.rules) < before

    def in_quiet_hours(self, now: float | None = None) -> bool:
        if not self.quiet_hours:
            return False
        start, end = self.quiet_hours
        if start == end:
            return False
        h = datetime.fromtimestamp(now if now is not None else time.time()).hour
        return (start <= h < end) if start < end else (h >= start or h < end)

    def check(self, ev: BusEvent, now: float | None = None) -> list[tuple[ProactiveRule, dict]]:
        now = now if now is not None else time.time()
        quiet = self.in_quiet_hours(now)
        gf = [t for t in self._global if now - t < 3600]
        out: list[tuple[ProactiveRule, dict]] = []
        for r in self.rules:
            if not r.enabled or not r.action or not r.matches(ev):
                continue
            atype = str(r.action.get("type") or "")
            is_external = (atype in self.EXTERNAL_TYPES
                           or bool(r.action.get("channel")))
            if is_external and not r.external_authorized:
                continue      # never external without explicit authorization
            if quiet and atype == "notify" and not r.action.get("critical"):
                continue      # quiet hours suppress non-critical pings
            fired = [t for t in self._fired.get(r.id, []) if now - t < 3600]
            if len(fired) >= r.max_per_hour:
                continue      # per-rule rate limit
            if len(gf) >= self.global_max_per_hour:
                continue      # global anti-spam cap
            fired.append(now)
            self._fired[r.id] = fired
            gf.append(now)
            out.append((r, r.action))
        self._global = gf
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
    import sys
    win = sys.platform == "win32"
    return {
        "timer": "built-in (thread)",
        "file_change": "built-in (polling, no dependency)",
        "calendar": "built-in (ICS files via JobTrigger kind=calendar)",
        "battery": ("built-in (GetSystemPowerStatus via tools.systemctl)" if win
                    else "unavailable (no power API on this platform)"),
        "network": "built-in (TCP connectivity probe, no DNS)",
        "app_event": ("built-in (foreground window + launch/close, via the "
                      "computer-use desktop backend)" if win
                      else "unavailable (no window enumeration on this platform)"),
        "email": "unavailable (no mail source wired)",
        "device_state": "built-in (memory + disk pressure via the native telemetry daemon)",
    }


class _PollSource(EventSource):
    """Shared poll loop: run `scan()` on an interval, never crash the loop."""
    kind = "poll"

    def __init__(self, interval_seconds: float, name: str = "BeePollSrc",
                 sleep_fn: Callable[[float], None] = time.sleep):
        self.interval = max(1.0, float(interval_seconds))
        self._name = name
        self._sleep = sleep_fn
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def scan(self, bus: EventBus) -> None:      # subclasses implement
        raise NotImplementedError

    def start(self, bus: EventBus) -> None:
        if self._thread is not None:
            return

        def _run():
            while not self._stop.is_set():
                try:
                    self.scan(bus)
                except Exception as e:                 # a broken probe must not kill it
                    log.debug("%s scan failed: %s", self.kind, e)
                self._stop.wait(self.interval)
        self._thread = threading.Thread(target=_run, daemon=True, name=self._name)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()


class BatterySource(_PollSource):
    """Edge-triggered power events: battery.low / battery.unplugged /
    battery.charged / ac.restored.

    Only transitions are published (a level poll every 60 s must not become a
    notification storm). Reads via tools.systemctl.get_battery — the same
    native path the fast paths use — with the reader injectable for tests.
    """
    kind = "battery"

    def __init__(self, interval_seconds: float = 60.0, low_percent: int = 20,
                 read_fn: Callable[[], tuple[int, int] | None] | None = None,
                 **kw):
        super().__init__(interval_seconds, name="BeeBatterySrc", **kw)
        self.low_percent = int(low_percent)
        self._read = read_fn
        self._was_low = False
        self._was_on_battery: bool | None = None

    def _default_read(self):
        from ..tools.systemctl import get_battery
        return get_battery()

    def scan(self, bus: EventBus) -> None:
        read = self._read or self._default_read
        got = read()
        if not got:
            return                       # desktop / no battery: nothing to report
        pct, ac = int(got[0]), int(got[1])
        on_battery = (ac == 0)
        if self._was_on_battery is not None and on_battery != self._was_on_battery:
            bus.publish(BusEvent(name=("battery.unplugged" if on_battery
                                        else "battery.charged"),
                                 kind="battery", payload={"percent": pct, "ac": ac},
                                 source="battery"))
        self._was_on_battery = on_battery
        low = on_battery and pct <= self.low_percent
        # hysteresis: re-arm only after climbing 5 points above the threshold
        if low and not self._was_low:
            bus.publish(BusEvent(name="battery.low", kind="battery",
                                 payload={"percent": pct, "ac": ac,
                                          "threshold": self.low_percent},
                                 source="battery"))
            self._was_low = True
        elif not low and pct > self.low_percent + 5:
            self._was_low = False
        bus.publish(BusEvent(name="battery.level", kind="battery",
                             payload={"percent": pct, "ac": ac},
                             source="battery"))


class NetworkSource(_PollSource):
    """Edge-triggered connectivity events: network.down / network.restored.

    Probes by TCP-connecting to public resolvers on port 53 — no DNS lookup, so
    a DNS outage is correctly reported as down, and nothing is fetched.
    """
    kind = "network"
    DEFAULT_TARGETS = (("1.1.1.1", 53), ("8.8.8.8", 53), ("223.5.5.5", 53))

    def __init__(self, interval_seconds: float = 30.0, targets=None,
                 probe_fn: Callable[[], bool] | None = None, **kw):
        super().__init__(interval_seconds, name="BeeNetworkSrc", **kw)
        self.targets = tuple(targets or self.DEFAULT_TARGETS)
        self._probe = probe_fn
        self._up: bool | None = None

    def _default_probe(self) -> bool:
        import socket
        for host, port in self.targets:
            try:
                with socket.create_connection((host, port), timeout=2.0):
                    return True
            except OSError:
                continue
        return False

    def scan(self, bus: EventBus) -> None:
        up = (self._probe or self._default_probe)()
        if self._up is not None and up != self._up:
            bus.publish(BusEvent(name=("network.restored" if up else "network.down"),
                                 kind="network", payload={"up": up},
                                 source="network"))
        self._up = up


class AppEventSource(_PollSource):
    """Foreground-window and running-app transitions.

    Reads through the SAME desktop abstraction computer use uses, so the
    platform boundary is `make_desktop()` (Windows today, mocked in tests) and
    no new dependency appears. Emits app.focused / app.launched / app.closed —
    events only: turning one into an action still requires a user-authorized
    proactive rule that passes the default-deny policy.
    """
    kind = "app_event"

    def __init__(self, desktop=None, interval_seconds: float = 10.0,
                 cfg=None, **kw):
        super().__init__(interval_seconds, name="BeeAppSrc", **kw)
        self._desktop = desktop
        self._cfg = cfg
        self._seen: set[str] = set()
        self._active: str | None = None
        self._primed = False

    def _read(self):
        d = self._desktop
        if d is None:
            from ..computeruse.desktop import make_desktop
            d = make_desktop(self._cfg)
            self._desktop = d
        wins = d.list_windows()
        aw = d.active_window()
        return wins, (aw.title if aw else "")

    def scan(self, bus: EventBus) -> None:
        wins, active = self._read()
        titles = {w.title for w in wins if w.title}
        if not self._primed:
            # first sample only establishes the baseline — no launch storm
            self._seen, self._active, self._primed = titles, active, True
            return
        if active and active != self._active:
            bus.publish(BusEvent(name="app.focused", kind="app_event",
                                 payload={"title": active[:200]}, source="app_event"))
            self._active = active
        for t in sorted(titles - self._seen):
            bus.publish(BusEvent(name="app.launched", kind="app_event",
                                 payload={"title": t[:200]}, source="app_event"))
        for t in sorted(self._seen - titles):
            bus.publish(BusEvent(name="app.closed", kind="app_event",
                                 payload={"title": t[:200]}, source="app_event"))
        self._seen = titles


class DeviceSource(_PollSource):
    """Memory / disk pressure transitions — this machine's documented failure
    mode (a killed Ollama session hoarding ~4 GB, or a disk down to a few GB,
    stalls everything while BEE looks healthy).

    Edge-triggered with hysteresis: one event per crossing, re-arming only after
    a clear recovery (25% headroom), so a value oscillating on the threshold
    cannot become a notification storm. Reads through tools.systemctl, i.e. the
    native telemetry daemon first and one CIM round-trip as fallback.
    """
    kind = "device_state"

    def __init__(self, interval_seconds: float = 60.0, mem_low_mb: int = 1500,
                 disk_low_gb: float = 4.0, read_fn: Callable[[], dict | None] | None = None,
                 **kw):
        super().__init__(interval_seconds, name="BeeDeviceSrc", **kw)
        self.mem_low_mb = int(mem_low_mb)
        self.disk_low_gb = float(disk_low_gb)
        self._read = read_fn
        self._low_mem = False
        self._low_disk = False

    def _default_read(self):
        from ..tools.systemctl import get_system_stats
        return get_system_stats()

    def _pub(self, bus: EventBus, name: str, **payload) -> None:
        bus.publish(BusEvent(name=name, kind="device_state", payload=payload,
                             source="device_state"))

    def scan(self, bus: EventBus) -> None:
        st = (self._read or self._default_read)()
        if not st:
            return
        free = st.get("ram_free_mb")
        if free is not None:
            free = int(free)
            if not self._low_mem and free <= self.mem_low_mb:
                self._low_mem = True
                self._pub(bus, "device.memory_low", ram_free_mb=free,
                          threshold_mb=self.mem_low_mb)
            elif self._low_mem and free >= int(self.mem_low_mb * 1.25):
                self._low_mem = False
                self._pub(bus, "device.memory_ok", ram_free_mb=free)
        disk = st.get("disk_free_gb")
        if disk is not None:
            disk = float(disk)
            if not self._low_disk and disk <= self.disk_low_gb:
                self._low_disk = True
                self._pub(bus, "device.disk_low", disk_free_gb=disk,
                          threshold_gb=self.disk_low_gb)
            elif self._low_disk and disk >= self.disk_low_gb * 1.25:
                self._low_disk = False
                self._pub(bus, "device.disk_ok", disk_free_gb=disk)


def start_sources(bus: EventBus, cfg=None) -> list[EventSource]:
    """Start the event sources that actually work on this machine.

    This is the production entry point — before it existed, Timer/FileChange
    sources were implemented and tested but NOTHING ever started them, so the
    proactive layer could only fire from events published inside tests.
    """
    auto = getattr(cfg, "automation", None) if cfg is not None else None
    started: list[EventSource] = []
    if not (getattr(auto, "events_enabled", True) if auto is not None else True):
        log.info("event sources disabled (automation.events_enabled=false)")
        return started
    tick = TimerSource(interval_seconds=float(getattr(auto, "event_tick_seconds", 60.0)
                                              if auto is not None else 60.0),
                       name="bee-tick")
    tick.start(bus)
    started.append(tick)
    # The capability report is the contract — never start a source it declares
    # unavailable on this platform (report/started-list consistency is pinned
    # by test_capability_report_is_honest_on_this_machine).
    if not available_sources()["battery"].startswith("unavailable"):
        battery = BatterySource(
            interval_seconds=float(getattr(auto, "battery_poll_seconds", 60.0)
                                   if auto is not None else 60.0),
            low_percent=int(getattr(auto, "battery_low_percent", 20)
                            if auto is not None else 20))
        try:
            battery.start(bus)
            started.append(battery)
        except Exception as e:
            log.info("battery source unavailable: %s", e)
    network = NetworkSource(
        interval_seconds=float(getattr(auto, "network_poll_seconds", 30.0)
                               if auto is not None else 30.0))
    network.start(bus)
    started.append(network)
    watch = str(getattr(auto, "file_watch_dir", "") or "") if auto is not None else ""
    if watch and Path(watch).exists():
        fs = FileChangeSource(watch)
        fs.start(bus)
        started.append(fs)
    if bool(getattr(auto, "app_events", True)) if auto is not None else True:
        try:
            app = AppEventSource(
                interval_seconds=float(getattr(auto, "app_poll_seconds", 10.0)
                                       if auto is not None else 10.0),
                cfg=cfg)
            app.scan(bus)                      # prime the baseline before starting
            app.start(bus)
            started.append(app)
        except Exception as e:
            log.info("app_event source unavailable on this platform: %s", str(e)[:120])
    if bool(getattr(auto, "device_events", True)) if auto is not None else True:
        dev = DeviceSource(
            interval_seconds=float(getattr(auto, "device_poll_seconds", 60.0)
                                   if auto is not None else 60.0),
            mem_low_mb=int(getattr(auto, "memory_low_mb", 1500)
                           if auto is not None else 1500),
            disk_low_gb=float(getattr(auto, "disk_low_gb", 4.0)
                              if auto is not None else 4.0))
        dev.start(bus)
        started.append(dev)
    log.info("event sources started: %s",
             ", ".join(sorted({s.kind for s in started})))
    return started
