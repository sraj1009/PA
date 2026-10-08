"""Shared EventBus tests (audit item 9 — ONE bus implementation).

Run:  python -m pytest tests/test_events.py -q
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from bee.events import EventBus as SharedBus


@dataclass
class _Ev:
    name: str
    payload: dict = field(default_factory=dict)


def test_one_implementation_two_facades():
    """kernel and automation buses must be thin facades over bee.events."""
    from bee.kernel.events import EventBus as KernelBus
    from bee.automation.events import EventBus as AutoBus, BusEvent
    kb, ab = KernelBus(), AutoBus()
    assert isinstance(kb._bus, SharedBus) and isinstance(ab._bus, SharedBus)

    # kernel API: subscribe(fn), emit -> event, .log, ._kind routing
    from bee.kernel.models import AgentEvent, AgentEventKind
    got = []
    kb.subscribe(lambda e: got.append(e))
    ev = AgentEvent(kind=AgentEventKind.TASK_CREATED, session_id="s", task_id="t")
    kb.emit(ev)
    assert got == [ev] and kb.log == [ev]
    assert kb.by_kind(AgentEventKind.TASK_CREATED) == [ev]
    kb.unsubscribe(lambda e: None)          # non-subscriber: no error

    # automation API: subscribe(pattern, fn), publish -> int, .published
    hits = {"file_change": 0, "star": 0}
    ab.subscribe("file_change", lambda e: hits.__setitem__("file_change", hits["file_change"] + 1))
    ab.subscribe("*", lambda e: hits.__setitem__("star", hits["star"] + 1))
    n = ab.publish(BusEvent(name="file.changed", kind="file_change"))
    assert n == 2 and hits == {"file_change": 1, "star": 1}
    n = ab.publish(BusEvent(name="other", kind="battery"))
    assert n == 1                            # only the "*" handler
    assert len(ab.published) == 2

    # pattern unsubscribe
    ab.unsubscribe("file_change", None)     # no-op for wrong handler
    assert hits["file_change"] == 1


def test_handler_exception_is_contained():
    bus = SharedBus()
    out = []
    bus.subscribe("*", lambda e: (_ for _ in ()).throw(RuntimeError("boom")))
    bus.subscribe("*", lambda e: out.append(e))
    n = bus.emit(_Ev(name="x"))
    assert n == 2 and len(out) == 1          # the good handler still ran


def test_bounded_log_and_clear():
    bus = SharedBus(max_log=5)
    for i in range(12):
        bus.emit(_Ev(name=f"e{i}"))
    assert len(bus.log) == 5 and bus.log[0].name == "e7"
    bus.clear()
    assert bus.log == []
    assert bus.emit(_Ev(name="after")) == 0  # subscribers cleared too


def test_subscription_order_and_dedupe():
    bus = SharedBus()
    order = []
    h1, h2 = (lambda e: order.append(1)), (lambda e: order.append(2))
    bus.subscribe("*", h1)
    bus.subscribe("*", h2)
    bus.subscribe("*", h1)                 # same (pattern, fn) object: deduped
    bus.emit(_Ev(name="x"))
    assert order == [1, 2]                 # first-in-first-out, h1 once
    bus.unsubscribe("*", h1)
    bus.emit(_Ev(name="y"))
    assert order == [1, 2, 2]
