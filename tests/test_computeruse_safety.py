"""Computer-use abort path (A42): the stop verb must never be deniable.

Found by driving all five computer tools through the real ToolBus with a stub
desktop — `computer_input`, `computer_clipboard` and `computer_stop` had never been
executed by the suite (coverage 57%).
"""
from __future__ import annotations

import threading

from bee.config import load_config
from bee.computeruse import tools as cu
from bee.computeruse.desktop import MockDesktop
from bee.computeruse.session import active_sessions
from bee.security.capabilities import CapabilityGate, _TOOL_CAPS
from bee.security.risk import _TOOL_PROFILES


class _Ctx:
    """The smallest thing the tool handlers need: cfg + an injected desktop."""

    def __init__(self, task_id="cu-probe"):
        self.cfg = load_config()
        self.computeruse_desktop = MockDesktop()
        self.current_task_id = task_id
        self.cancel_event = threading.Event()
        self.guard_on = True


DENY = lambda tool, args, reason: False


def test_the_abort_verb_requires_no_capability():
    """The gate's answer when NOTHING is permitted: clicking is refused (correct),
    stopping must not be (A42a: it used to require `desktop.control`, the very
    capability the user is trying to abort)."""
    g = CapabilityGate()
    stop = g.check("computer_stop", {}, task_id="t", confirmer=DENY)
    control = g.check("computer_input", {}, task_id="t", confirmer=DENY)
    assert stop.allowed is True, f"stop was deniable: {stop.reason}"
    assert control.allowed is False, "control must still fail closed"


def test_both_authoritative_tables_agree_that_stop_needs_nothing():
    """`security/risk.py` and `security/capabilities.py` are two tables describing
    one rule; they disagreed (risk said no capability, the map said desktop.control)
    and the map won. Pin both so a future edit cannot silently re-gate the abort."""
    assert _TOOL_PROFILES["computer_stop"][1] == frozenset()
    assert _TOOL_CAPS["computer_stop"] == []


def test_stop_is_registered_capability_free_on_the_bus():
    """The ToolBus carries the FULL capability list per tool (N9), so the
    registration must match the map — otherwise the gate sees one thing and the
    audit another."""
    tool = {t.name: t for t in cu.computeruse_tools()}["computer_stop"]
    assert list(tool.capabilities) == []
    assert tool.risk == "low"


def test_a_denied_agent_can_still_stop_and_it_really_stops():
    """End to end through the handlers with a deny-everything posture: the session
    exists, input is refused, and the abort lands — proving the fix is functional,
    not just a changed constant."""
    ctx = _Ctx()
    obs = cu.computer_observe(ctx)
    assert "windows" in obs or "screenshot" in obs, obs
    before = active_sessions()
    assert before >= 1, "the observe call should have created the task session"

    stopped = cu.computer_stop(ctx)
    assert stopped["stopped_sessions"] >= 1

    again = cu.computer_input(ctx, action="key_press", keys=["ctrl", "s"])
    assert again.get("blocked") is True or again.get("error"), again

    # the next TASK gets a fresh session: an abort stops this one, it does not
    # brick desktop control for the process (that would be its own defect).
    ctx2 = _Ctx(task_id="cu-probe-next")
    obs2 = cu.computer_observe(ctx2)
    assert not obs2.get("blocked"), obs2


def test_a_string_chord_is_refused_instead_of_typing_its_characters():
    """A42b: `keys: "ctrl+s"` used to run — a string is iterable, so the desktop
    pressed c, t, r, l, +, s one at a time into whatever the user has focused, and
    the closed loop reported `executed: True, verified: True` because the screen
    did change. Refusing is correct: 'ctrl+s' could be a chord or a literal, and a
    wrong guess writes into the user's document."""
    ctx = _Ctx(task_id="a42b-keys")
    out = cu.computer_input(ctx, action="key_press", keys="ctrl+s")
    assert out.get("error") and "list" in out["error"], out
    assert not out.get("executed"), out
    assert not out.get("verified"), out


def test_the_rejection_names_the_shape_the_model_should_send():
    from bee.computeruse.action import ComputerAction
    import pytest
    with pytest.raises(ValueError) as e:
        ComputerAction(action="key_press", keys="ctrl+s")
    assert '["ctrl", "s"]' in str(e.value)


def test_a_numeric_string_coordinate_still_works_but_garbage_does_not():
    """The coercion accepts the harmless "12" and refuses "12px" — silently
    forwarding a non-number to the desktop is the same defect class."""
    ctx = _Ctx(task_id="a42b-coord")
    obs = cu.computer_observe(ctx)          # records rects for provenance
    good = cu.computer_input(ctx, action="click", x="10", y="12",
                             coordinate_source="model_raw")
    assert good.get("executed") or "confirm" in str(good).lower(), good
    bad = cu.computer_input(ctx, action="click", x="12px", y=12,
                            coordinate_source="model_raw")
    assert bad.get("error") and "integer" in bad["error"], bad


def test_expected_as_a_string_is_refused_not_misreported():
    """It used to fall through to 'click requires coordinates', sending the model
    off to add x/y when its real mistake was the argument type."""
    ctx = _Ctx(task_id="a42b-expected")
    out = cu.computer_input(ctx, action="key_press", keys=["ctrl", "s"],
                           expected="screen_changed")
    assert out.get("error") and "expected" in out["error"], out


def test_a_real_chord_still_works():
    ctx = _Ctx(task_id="a42b-ok")
    out = cu.computer_input(ctx, action="key_press", keys=["ctrl", "s"],
                            expected={"screen_changed": True})
    assert out.get("executed") is True and out.get("verified") is True, out


def test_emergency_stop_is_idempotent_and_never_raises():
    """A stop on a context with no session must not error, and a second stop is
    still safe — the hotkey thread and the REPL can both fire it at any moment."""
    ctx = _Ctx(task_id="cu-probe-none")
    first = cu.computer_stop(ctx)
    second = cu.computer_stop(ctx)
    assert isinstance(first["stopped_sessions"], int)
    assert isinstance(second["stopped_sessions"], int)
    assert active_sessions() >= 0
