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
