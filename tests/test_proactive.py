"""Phase 11 — PROACTIVE JARVIS + EVENT INTELLIGENCE (2026-10-08).

The proactive layer is default-deny: an event can only cause an action when
an explicitly user-authorized ProactiveRule matches it. This file proves
each denial path and each supported behavior:

  * no rule            -> no action (never arbitrary proactivity)
  * matching rule      -> action fires (timer + file_change sources)
  * per-rule rate limit (max_per_hour)
  * GLOBAL anti-spam cap
  * quiet hours        (non-critical notify suppressed; critical + tasks fire)
  * EXTERNAL side effects (email/whatsapp/sms) denied without explicit
                         authorization, allowed with it
  * traceability       (rules persist created_by/created_at/authorization)
  * rule round-trip    (store from_dict/to_dict keeps the new fields)

No real clock dependence: check(now=...) is injected; sources use a fake
sleep. No network, no mail, no display.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta, timezone

from bee.automation.events import (BusEvent, EventBus, FileChangeSource,
                                   ProactivePolicy, ProactiveRule,
                                   TimerSource)

T0 = 1_760_000_000.0          # fixed epoch for deterministic 'now'


def _ev(name="tick", kind="timer", **payload):
    return BusEvent(name=name, kind=kind, payload=payload)


def test_default_deny_no_rule_no_action():
    p = ProactivePolicy(rules=[])
    assert p.check(_ev()) == []
    # an event that matches nothing:
    p.add_rule(ProactiveRule(kind="email", match={"subject": "x"},
                             action={"type": "notify", "text": "hi"}))
    assert p.check(_ev(kind="timer")) == []


def test_matching_rule_fires_and_traces_authorization():
    # rules match on PAYLOAD fields (kind must also match)
    r = ProactiveRule(kind="timer", match={"what": "tick"},
                      action={"type": "notify", "text": "hello"},
                      description="weekday schedule", created_by="user")
    p = ProactivePolicy(rules=[r])
    out = p.check(_ev(what="tick"), now=T0)
    assert len(out) == 1 and out[0][1]["text"] == "hello"
    assert p.check(_ev(what="other"), now=T0) == []
    d = r.to_dict()
    assert d["created_by"] == "user" and d["created_at"]
    assert d["external_authorized"] is False


def test_per_rule_rate_limit():
    r = ProactiveRule(kind="timer", action={"type": "notify", "text": "x"},
                      max_per_hour=3)
    p = ProactivePolicy(rules=[r])
    fires = sum(len(p.check(_ev(), now=T0 + i)) for i in range(10))
    assert fires == 3, "the rule's hourly cap must hold"


def test_global_anti_spam_cap():
    rules = [ProactiveRule(kind="timer", match={"n": str(i)},
                           action={"type": "notify", "text": f"n{i}"})
             for i in range(5)]
    p = ProactivePolicy(rules=rules, global_max_per_hour=2)
    total = sum(len(p.check(_ev(n=str(i)), now=T0)) for i in range(5))
    assert total == 2, "the GLOBAL cap must bound all rules together"


def test_quiet_hours_suppress_noncritical_notify_only():
    # in_quiet_hours uses LOCAL wall time — build the fixed instants from
    # local time so the test is deterministic whenever it runs
    night = datetime.now().replace(hour=23, minute=30, second=0,
                                   microsecond=0).timestamp()
    noon = datetime.now().replace(hour=12, minute=0, second=0,
                                  microsecond=0).timestamp()
    p = ProactivePolicy(rules=[], quiet_hours=(22, 7))
    assert p.in_quiet_hours(night) is True
    assert p.in_quiet_hours(noon) is False

    rn = ProactiveRule(kind="timer", action={"type": "notify", "text": "chime"})
    rc = ProactiveRule(kind="timer",
                       action={"type": "notify", "text": "urgent", "critical": True})
    rt = ProactiveRule(kind="timer",
                       action={"type": "agent_task", "task": "summarize day"})
    p2 = ProactivePolicy(rules=[rn, rc, rt], quiet_hours=(22, 7))
    out_night = {a.get("text") or a.get("task") for _r, a in p2.check(_ev(), now=night)}
    out_noon = {a.get("text") or a.get("task") for _r, a in p2.check(_ev(), now=noon)}
    assert "chime" not in out_night, "non-critical notify must be quiet at night"
    assert "urgent" in out_night, "critical notify still fires at night"
    assert "summarize day" in out_night, "agent tasks are not pings"
    assert out_noon == {"chime", "urgent", "summarize day"}


def test_external_actions_never_fire_without_authorization():
    for atype in ("send_email", "whatsapp", "sms", "message"):
        r = ProactiveRule(kind="email", action={"type": atype, "to": "x"},
                          external_authorized=False)
        p = ProactivePolicy(rules=[r])
        assert p.check(_ev(kind="email"), now=T0) == [], atype
    # a plain channel on a notify action also counts as external
    r2 = ProactiveRule(kind="email", action={"type": "notify", "channel": "whatsapp"},
                       external_authorized=False)
    assert ProactivePolicy(rules=[r2]).check(_ev(kind="email"), now=T0) == []


def test_external_action_fires_with_explicit_authorization():
    r = ProactiveRule(kind="email", action={"type": "send_email", "to": "me"},
                      external_authorized=True)
    out = ProactivePolicy(rules=[r]).check(_ev(kind="email"), now=T0)
    assert len(out) == 1


def test_rule_roundtrip_keeps_authorization():
    r = ProactiveRule(kind="battery", action={"type": "notify", "text": "low"},
                      external_authorized=True, max_per_hour=2)
    d = r.to_dict()
    r2 = ProactiveRule.from_dict(d)
    assert r2.external_authorized is True and r2.max_per_hour == 2
    assert ProactiveRule.from_dict({}).external_authorized is False


def test_timer_source_publishes_and_policy_consumes():
    fired = []
    bus = EventBus()
    p = ProactivePolicy(rules=[ProactiveRule(
        kind="timer", match={},      # any timer tick (payload fields optional)
        action={"type": "notify", "text": "fired"})])
    bus.subscribe("timer", lambda ev: fired.extend(p.check(ev)))
    src = TimerSource(interval_seconds=0.01, sleep_fn=lambda s: None)
    src.start(bus)
    t0 = time.time()
    while len(fired) < 2 and time.time() - t0 < 3.0:
        time.sleep(0.005)
    src.stop()
    assert len(fired) >= 2, "timer source must publish and the policy must fire"
    assert len(bus.published) >= 2


def test_file_change_source_end_to_end(tmp_path):
    """'When this file appears, tell me' — FileChangeSource -> bus -> policy
    -> notify, with the rate limit holding under repeated changes."""
    bus = EventBus()
    p = ProactivePolicy(rules=[ProactiveRule(
        kind="file_change", match={}, max_per_hour=4,
        action={"type": "notify", "text": "file ready"})])
    fired = []
    bus.subscribe("file_change", lambda ev: fired.extend(p.check(ev)))
    src = FileChangeSource(tmp_path, interval_seconds=0.01,
                           sleep_fn=lambda s: None)
    src.start(bus)
    time.sleep(0.05)
    for i in range(8):
        (tmp_path / f"dl_{i}.txt").write_text(f"part {i}")
        time.sleep(0.02)
    time.sleep(0.1)
    src.stop()
    assert fired, "file changes must reach the policy"
    assert len(fired) <= 4, "the rule's rate limit must bound notification spam"


# ------------------------- real event sources (2026-10-08 fix pass) ----------
# Battery / network were schema-only, and NOTHING started any source in
# production — so the proactive layer could only ever fire from events
# published inside tests.

from bee.automation.events import (BatterySource, NetworkSource,  # noqa: E402
                                   available_sources, start_sources)


class CollectBus:
    def __init__(self):
        self.events = []

    def publish(self, ev):
        self.events.append(ev)

    def names(self):
        return [e.name for e in self.events]


def test_battery_reports_only_transitions():
    bus = CollectBus()
    seq = [(70, 1), (40, 0), (18, 0), (15, 0), (15, 1), (90, 1)]
    src = BatterySource(interval_seconds=1.0, low_percent=20,
                        read_fn=lambda: seq.pop(0) if seq else None)
    for _ in range(6):
        src.scan(bus)
    # unplugged at 40 -> transition; crossing 20 -> battery.low exactly once;
    # repeated 15% must NOT re-fire; plugging in -> battery.charged
    transitions = [n for n in bus.names() if n != "battery.level"]
    assert transitions == ["battery.unplugged", "battery.low",
                           "battery.charged"], bus.names()
    assert bus.names().count("battery.low") == 1,         "18% then 15% is one crossing, not two alerts"


def test_battery_absent_is_silent():
    bus = CollectBus()
    BatterySource(read_fn=lambda: None).scan(bus)
    assert bus.names() == []


def test_network_fires_only_on_change():
    bus = CollectBus()
    seq = [True, True, False, False, True]
    src = NetworkSource(interval_seconds=1.0, probe_fn=lambda: seq.pop(0))
    for _ in range(5):
        src.scan(bus)
    # the first sample only establishes state — no false "restored" event
    assert bus.names() == ["network.down", "network.restored"], bus.names()


def test_sources_honor_config_and_the_disable_switch(monkeypatch):
    from bee.config import load_config
    monkeypatch.setattr(BatterySource, "start", lambda self, bus: None)
    monkeypatch.setattr(NetworkSource, "start", lambda self, bus: None)
    monkeypatch.setattr(TimerSource, "start", lambda self, bus: None)
    cfg = load_config()
    cfg.automation.events_enabled = False
    assert start_sources(CollectBus(), cfg) == [], "events_enabled=false starts nothing"
    cfg.automation.events_enabled = True
    cfg.automation.file_watch_dir = ""
    started = start_sources(CollectBus(), cfg)
    kinds = {s.kind for s in started}
    expected = {"timer", "network"}
    if sys.platform == "win32":
        expected.add("battery")           # the power API exists on Windows only
    assert expected <= kinds, kinds
    if "battery" in kinds:
        bat = [s for s in started if s.kind == "battery"][0]
        assert bat.interval == cfg.automation.battery_poll_seconds
        assert bat.low_percent == cfg.automation.battery_low_percent
    net = [s for s in started if s.kind == "network"][0]
    assert net.interval == cfg.automation.network_poll_seconds


def test_capability_report_is_honest_on_this_machine():
    """The report must not overclaim — and must not underclaim either: whatever
    start_sources() can actually run has to be reported as built-in."""
    from bee.automation import events as ev
    from bee.config import load_config
    rep = available_sources()
    assert rep["battery"].startswith("built-in") or "unavailable" in rep["battery"]
    assert rep["network"].startswith("built-in")
    assert rep["email"].startswith("unavailable"), "email is still schema-only"
    assert rep["app_event"].startswith("unavailable") or rep["app_event"].startswith("built-in")
    started = ev.start_sources(CollectBus(), load_config())
    for src in started:
        msg = f"started a {src.kind} source but the report says: {rep[src.kind]}"
        assert rep[src.kind].startswith("built-in"), msg
    for kind, note in rep.items():
        if note.startswith("unavailable"):
            assert kind not in {s.kind for s in started}, f"{kind} claims unavailable but runs"


def test_worker_stop_stops_its_attached_event_sources(tmp_path):
    """A poller that outlives the worker is an orphan thread that keeps
    publishing into a dead bus."""
    from bee.automation import EventBus, JobStore, JobWorker
    from bee.config import load_config
    from types import SimpleNamespace

    class FakeSrc:
        kind = "fake"
        def __init__(self): self.stopped = False
        def start(self, bus): pass
        def stop(self): self.stopped = True

    cfg = load_config()
    ctx = SimpleNamespace(cfg=cfg, workspace=tmp_path, kernel=None,
                          current_task_id="", cancel_event=None)
    w = JobWorker(ctx, SimpleNamespace(run=lambda *a, **k: None),
                  JobStore(tmp_path / "automation"), bus=EventBus(),
                  tick_seconds=5.0)
    src = FakeSrc()
    w.event_sources = [src]
    w.stop()
    assert src.stopped, "worker.stop() must stop attached sources"
    assert w.event_sources == []


def test_app_event_source_emits_transitions_only():
    """A foreground poll must not become an event storm: baseline first, then
    only real changes."""
    from bee.automation.events import AppEventSource
    from bee.computeruse import MockDesktop
    md = MockDesktop()
    md.add_window("Program Manager", "Progman", (0, 0, 100, 100))
    src = AppEventSource(desktop=md, interval_seconds=1.0)
    bus = CollectBus()
    src.scan(bus)                                  # prime
    assert bus.names() == [], bus.names()
    src.scan(bus)                                  # nothing changed
    assert bus.names() == []
    md.map_app("notepad", "Notepad - todo.txt")
    md.add_window("Notepad - todo.txt", "Notepad", (10, 10, 500, 500))
    src.scan(bus)
    names = bus.names()
    assert "app.launched" in names, names
    src.scan(bus)
    assert bus.names() == names, "a steady state must emit nothing new"


def test_start_sources_honors_app_events_switch(monkeypatch):
    from bee.config import load_config
    from bee.automation import events as ev
    monkeypatch.setattr(ev.BatterySource, "start", lambda self, bus: None)
    monkeypatch.setattr(ev.NetworkSource, "start", lambda self, bus: None)
    monkeypatch.setattr(ev.TimerSource, "start", lambda self, bus: None)
    monkeypatch.setattr(ev.AppEventSource, "scan", lambda self, bus: None)
    monkeypatch.setattr(ev.AppEventSource, "start", lambda self, bus: None)
    cfg = load_config()
    kinds_on = {s.kind for s in ev.start_sources(CollectBus(), cfg)}
    assert "app_event" in kinds_on, kinds_on
    cfg.automation.app_events = False
    kinds_off = {s.kind for s in ev.start_sources(CollectBus(), cfg)}
    assert "app_event" not in kinds_off, kinds_off
    cfg.automation.app_events = True
    cfg.automation.app_poll_seconds = 3.0
    src = [s for s in ev.start_sources(CollectBus(), cfg) if s.kind == "app_event"][0]
    assert src.interval == 3.0


# ------------------------------ device pressure source (A22) ----------------
def test_device_source_is_edge_triggered_with_hysteresis():
    """A value oscillating on the threshold must not become a ping storm, and a
    recovery must be unambiguous before re-arming."""
    from bee.automation.events import DeviceSource
    bus = CollectBus()
    src = DeviceSource(mem_low_mb=1500, disk_low_gb=4.0,
                       read_fn=lambda: {"ram_free_mb": 1400, "disk_free_gb": 15})
    src.scan(bus); src.scan(bus)
    assert bus.names() == ["device.memory_low"], bus.names()
    src._read = lambda: {"ram_free_mb": 1600, "disk_free_gb": 15}
    src.scan(bus)                                   # +100 MB: not a recovery yet
    assert bus.names() == ["device.memory_low"]
    src._read = lambda: {"ram_free_mb": 2000, "disk_free_gb": 3.0}
    src.scan(bus)
    assert bus.names() == ["device.memory_low", "device.memory_ok",
                           "device.disk_low"], bus.names()


def test_device_source_survives_a_missing_reader():
    from bee.automation.events import DeviceSource
    bus = CollectBus()
    DeviceSource(read_fn=lambda: None).scan(bus)     # desktop / no stats
    DeviceSource(read_fn=lambda: {"ram_free_mb": None, "disk_free_gb": None}).scan(bus)
    assert bus.names() == []
    # The real reader must never raise into the poll loop: Windows telemetry
    # yields stats; platforms without a native backend return None — exactly
    # the "nothing to report" case pinned by the two scans above.
    got = DeviceSource()._default_read()
    if sys.platform == "win32":
        assert got is not None
    else:
        assert got is None


def test_start_sources_runs_and_can_stop_the_device_source(monkeypatch):
    from bee.config import load_config
    from bee.automation import events as ev
    for cls in (ev.TimerSource, ev.BatterySource, ev.NetworkSource,
                ev.AppEventSource, ev.DeviceSource):
        monkeypatch.setattr(cls, "start", lambda self, bus: None)
    monkeypatch.setattr(ev.AppEventSource, "scan", lambda self, bus: None)
    cfg = load_config()
    kinds = {s.kind for s in ev.start_sources(CollectBus(), cfg)}
    assert "device_state" in kinds, kinds
    dev = [s for s in ev.start_sources(CollectBus(), cfg) if s.kind == "device_state"][0]
    assert dev.mem_low_mb == cfg.automation.memory_low_mb
    assert dev.disk_low_gb == cfg.automation.disk_low_gb
    assert dev.interval == cfg.automation.device_poll_seconds
    cfg.automation.device_events = False
    assert "device_state" not in {s.kind for s in ev.start_sources(CollectBus(), cfg)}


def test_device_events_can_drive_a_user_authorized_rule_only():
    """The event is information; only an explicitly authorized proactive rule
    may turn it into an action (default-deny stays default-deny)."""
    from bee.automation.events import BusEvent, ProactivePolicy, ProactiveRule
    ev = BusEvent(name="device.memory_low", kind="device_state",
                  payload={"ram_free_mb": 900})
    assert ProactivePolicy(rules=[]).check(ev) == []
    by_name = ProactiveRule(kind="device_state", match={"name": "device.memory_low"},
                            action={"type": "notify", "message": "RAM is low"},
                            created_by="user")
    got = ProactivePolicy(rules=[by_name]).check(ev, now=1_760_000_000.0)
    assert [r.id for r, _a in got] == [by_name.id], "name matching must work"


def test_threshold_rules_match_the_way_real_events_vary():
    """RAM free is a different number every poll, so exact-value matching made
    device rules unusable. Comparisons are now supported."""
    from bee.automation.events import (BusEvent, ProactivePolicy, ProactiveRule)
    low = BusEvent(name="device.memory_low", kind="device_state",
                   payload={"ram_free_mb": 900, "threshold_mb": 1500})
    fine = BusEvent(name="device.memory_low", kind="device_state",
                    payload={"ram_free_mb": 9000, "threshold_mb": 1500})
    rule = ProactiveRule(kind="device_state", match={"ram_free_mb<=": 1500},
                         action={"type": "notify", "message": "low"},
                         created_by="user")
    pol = ProactivePolicy(rules=[rule])
    assert pol.check(low, now=1_760_000_000.0), "900 MB free must match <=1500"
    assert ProactivePolicy(rules=[rule]).check(fine, now=1_760_000_000.0) == []
    # a key with no operator is still exact
    exact = ProactiveRule(kind="device_state", match={"threshold_mb": 1500},
                          action={"type": "notify"}, created_by="user")
    assert ProactivePolicy(rules=[exact]).check(low, now=1_760_000_000.0)
    assert ProactivePolicy(rules=[exact]).check(
        BusEvent(name="device.memory_low", kind="device_state",
                 payload={"threshold_mb": 2000}), now=1_760_000_000.0) == []
