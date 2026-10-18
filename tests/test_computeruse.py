"""Computer-use tests (Phase 5) — SAFE desktop control against MOCKED UI
states. No test touches the real desktop: MockDesktop provides a window
registry, launcher hotspots, input log, clipboard, and deterministic
screenshot hashes.

Coverage:
  1.  observe returns a structured UI (no pixels in the payload)
  2.  flagship closed loop: "open chrome" (observe -> act -> verify)
  3.  click with coords from the last observe (proven) -> verified
  4.  click with UNPROVEN coords claiming window_rect -> blocked (never
      trust coordinates blindly)
  5.  explicit model_raw coords pass the session (confirmation is the
      risk/capability layer's job — tested directly)
  6.  type_text payload never logged (length only); credential targets
      refused outright
  7.  copy/paste verified structurally; clipboard content never logged
  8.  per-task action budget enforced
  9.  emergency stop: stop_event / global / kernel cancel_event / hotkey
  10. verification failure => never claims success; dispatch failure blocked
  11. screenshot retention (ring bound, purge, nothing on disk by default)
  12. end-to-end through the REAL kernel: capability gate ASK, task-scoped
      grant, execution on MockDesktop, verified effect, receipts.

Run:  python -m pytest tests/test_computeruse.py -q
"""
from __future__ import annotations

import json
import sys
import threading

import pytest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent))

from bee.computeruse import (ComputerAction, ComputerUseSession,
                             HotkeyStopper, MockDesktop, ScreenshotStore,
                             computeruse_emergency_stop)
from bee.config import load_config
from bee.security.risk import RiskLevel, classify_risk


def make_ctx(tmp_path=None, md: MockDesktop | None = None) -> SimpleNamespace:
    cfg = load_config()
    if tmp_path is not None:
        cfg.workspace = tmp_path
    return SimpleNamespace(cfg=cfg,
                           cancel_event=threading.Event(),
                           current_task_id="t1",
                           computeruse_desktop=md or MockDesktop())


# ------------------------------------------------------- Phase 10 (2026-10-08)
def test_13_structural_vision_locates_semantic_target():
    """The model names an element (no coordinates); the vision backend
    resolves it against the FRESH UI snapshot; the click is proven."""
    from bee.computeruse import StructuralVision
    md = MockDesktop()
    md.add_window("Notepad - todo.txt", "Notepad", (100, 100, 700, 500))
    v = StructuralVision()
    s = make_session(md, vision=v)
    s.observe()
    loc = v.locate(md, None, "Notepad")
    assert loc is not None
    x, y, conf = loc
    assert 100 <= x <= 700 and 100 <= y <= 500
    assert conf >= 0.8
    # semantic click (no coords on the action) -> vision resolves -> executes
    r = s.execute(ComputerAction(action="click", target="Notepad",
                                 coordinate_source="element",
                                 description="click the Notepad window"))
    assert r.get("executed") is True, r
    assert r.get("blocked") is not True


def test_14_semantic_target_unlocatable_is_blocked():
    """No coords AND vision cannot find the target -> blocked with a clear
    instruction (never a blind click)."""
    md = MockDesktop()
    md.add_window("Program Manager", "Progman", (0, 0, 1920, 1080))
    s = make_session(md)
    s.observe()
    r = s.execute(ComputerAction(action="click", target="NoSuchButton",
                                 coordinate_source="element"))
    assert r.get("blocked") is True
    assert "vision could not locate" in r["error"]


def test_15_vision_backend_is_swappable_and_degrades():
    """Vendor-neutrality: any object with the protocol plugs in; a BROKEN
    backend degrades the observe() (never crashes the session)."""
    from bee.computeruse import VisionBackend

    class CustomVision:
        name = "custom-test"

        def describe(self, desktop, frame):
            return "custom description"

        def detect_elements(self, desktop, frame):
            from bee.computeruse import Element
            return [Element(label="FakeButton", rect=(10, 10, 50, 50),
                            score=0.9, kind="button")]

        def locate(self, desktop, frame, target):
            return (30, 30, 0.9) if "Fake" in target else None

        def verify(self, desktop, frame, expected):
            return (None, "custom")

    assert isinstance(CustomVision(), VisionBackend)   # protocol-checkable
    md = MockDesktop()
    md.add_window("Program Manager", "Progman", (0, 0, 1920, 1080))
    s = make_session(md, vision=CustomVision())
    obs = s.observe()
    assert obs["vision"] == "custom-test"
    assert obs["elements"][0]["label"] == "FakeButton"
    assert obs["description"] == "custom description"

    class BrokenVision:
        name = "broken"
        def describe(self, *a): raise RuntimeError("model down")
        def detect_elements(self, *a): raise RuntimeError("model down")
        def locate(self, *a): raise RuntimeError("model down")
        def verify(self, *a): raise RuntimeError("model down")

    s2 = make_session(md, vision=BrokenVision())
    obs2 = s2.observe()          # must degrade, not raise
    assert obs2["vision"] == "unavailable"
    assert obs2["n_windows"] == 1    # structural data still present


def test_16_action_id_and_public_contract():
    a = ComputerAction(action="screenshot")
    assert a.action_id and a.action_id.startswith("cu_")
    b = ComputerAction(action="screenshot")
    assert a.action_id != b.action_id        # unique per action
    pub = a.public()
    assert pub["action_id"] == a.action_id
    # type_text payload still never appears in the public view
    t = ComputerAction(action="type_text", text="s3cret-value")
    tp = t.public()
    assert "s3cret-value" not in json.dumps(tp)
    assert tp["text_len"] == len("s3cret-value")


def make_session(md: MockDesktop | None = None, max_actions=10, **kw):
    return ComputerUseSession(md or MockDesktop(), max_actions=max_actions, **kw)


# ---------------------------------------------------------------- scenarios
def test_1_observe_structured_no_pixels():
    md = MockDesktop()
    md.add_window("Program Manager", "Progman", (0, 0, 1920, 1080))
    md.add_window("Notepad - hello.txt", "Notepad", (100, 100, 800, 600))
    s = make_session(md)
    obs = s.observe()
    assert obs["n_windows"] == 2
    assert obs["active"]["title"] == "Notepad - hello.txt"
    w0 = obs["windows"][0]
    assert w0["rect"] == [0, 0, 1920, 1080]
    payload = json.dumps(obs)
    assert len(payload) < 4000                       # structured, not pixels
    assert obs["screen_hash"]                        # hash present


def test_2_flagship_open_chrome_closed_loop():
    """User: 'Open Chrome.'  observe -> open -> observe -> verify window."""
    md = MockDesktop()
    md.add_window("Program Manager", "Progman", (0, 0, 1920, 1080))
    md.map_app("chrome", "Google Chrome")
    s = make_session(md)
    assert s.observe()["n_windows"] == 1             # step 1-2: identify desktop
    r = s.execute(ComputerAction(action="open_application", target="chrome",
                                 expected={"window_exists": "Chrome"},
                                 description="launch Chrome from the app list"))
    assert r["executed"] is True                     # step 3: act
    assert r["verified"] is True                     # step 4-5: observe + verify
    assert r["verification"] == "window_exists"
    assert any(w.title == "Google Chrome" for w in md.list_windows())
    assert md.active_window().title == "Google Chrome"
    assert r["actions_used"] == 1 and r["max_actions"] == 10


def test_3_click_with_proven_coordinates():
    md = MockDesktop()
    md.add_window("Program Manager", "Progman", (0, 0, 1920, 1080))
    md.set_launcher("Google Chrome", 100, 500, 140, 54)    # x, y, w, h
    s = make_session(md)
    s.observe()                                      # records rects (provenance)
    r = s.execute(ComputerAction(action="click", x=120, y=520,
                                 coordinate_source="window_rect",
                                 target="Chrome launcher",
                                 expected={"window_exists": "Chrome"}))
    assert r["executed"] is True
    assert r["verified"] is True                     # launcher opened Chrome
    assert ("click", 120, 520, "left") in md.input_log


def test_4_unproven_coordinates_blocked():
    """Coords claiming 'window_rect' that no observe supports are REFUSED —
    the session never trusts coordinates blindly."""
    md = MockDesktop()
    md.add_window("Program Manager", "Progman", (0, 0, 1920, 1080))
    s = make_session(md)
    # no observe ever happened -> nothing proven
    r = s.execute(ComputerAction(action="click", x=500, y=500,
                                 coordinate_source="window_rect",
                                 target="unknown spot"))
    assert r["blocked"] is True
    assert "observe" in r["error"]
    assert md.input_log == []                        # no input was sent
    # even AFTER an observe, coords outside every rect are unproven
    s.observe()
    md2 = MockDesktop()
    s2 = make_session(md2)
    s2.observe()
    r2 = s2.execute(ComputerAction(action="click", x=99999, y=99999,
                                   coordinate_source="window_rect"))
    assert r2["blocked"] is True


def test_5_model_raw_coords_and_risk_escalation():
    md = MockDesktop()
    md.add_window("Program Manager", "Progman", (0, 0, 1920, 1080))
    s = make_session(md)
    # explicit model_raw: session allows (the RISK layer makes the user
    # confirm it — asserted below); verification still runs
    r = s.execute(ComputerAction(action="click", x=500, y=500,
                                 coordinate_source="model_raw",
                                 expected={"screen_changed": True}))
    assert r["executed"] is True
    # risk layer: unproven coords + type_text escalate to HIGH/ask
    d_raw = classify_risk("computer_input", {"action": "click", "x": 5, "y": 5,
                                             "coordinate_source": "model_raw"})
    assert d_raw.level == RiskLevel.HIGH and d_raw.action == "ask"
    d_type = classify_risk("computer_input", {"action": "type_text", "text": "x"})
    assert d_type.level == RiskLevel.HIGH and d_type.action == "ask"
    d_proven = classify_risk("computer_input", {"action": "click", "x": 5, "y": 5,
                                                "coordinate_source": "window_rect"})
    assert d_proven.action == "allow"                 # base layer; gate policy adds ASK
    d_obs = classify_risk("computer_observe", {})
    assert d_obs.level == RiskLevel.LOW


def test_6_type_text_never_logged_and_credential_refused():
    md = MockDesktop()
    md.add_window("Google Chrome", "Chrome", (0, 0, 1600, 900))
    s = make_session(md)
    secret = "hunter2-super-secret"
    r = s.execute(ComputerAction(action="type_text", text=secret,
                                 target="address bar",
                                 expected={"screen_changed": True}))
    assert r["executed"] is True and r["verified"] is True
    blob = json.dumps(s.log)
    assert secret not in blob                          # payload never logged
    entry = [e for e in s.log if e["action"] == "type_text"][0]
    assert entry["text_len"] == len(secret)
    # credential entry: refused regardless of any grant
    r2 = s.execute(ComputerAction(action="type_text", text="x",
                                  target="password field"))
    assert r2["blocked"] is True
    assert "credential" in r2["error"].lower()
    assert not any(i[0] == "type_text" and i[1] == 1 for i in md.input_log)


def test_7_clipboard_verified_content_never_logged():
    md = MockDesktop()
    md.add_window("Notepad", "Notepad", (0, 0, 800, 600))
    md.type_buffer = "confidential-selection"
    s = make_session(md)
    r = s.execute(ComputerAction(action="copy"))
    assert r["verified"] is True and r["verification"] == "clipboard_changed"
    r2 = s.execute(ComputerAction(action="paste"))
    assert r2["verified"] is True
    blob = json.dumps(s.log)
    assert "confidential-selection" not in blob        # content never logged
    assert md.clipboard == "confidential-selection"


def test_8_action_budget_enforced():
    md = MockDesktop()
    md.add_window("Program Manager", "Progman", (0, 0, 1920, 1080))
    s = make_session(md, max_actions=2)
    s.execute(ComputerAction(action="screenshot"))
    s.execute(ComputerAction(action="screenshot"))
    r = s.execute(ComputerAction(action="screenshot"))
    assert r["blocked"] is True
    assert "budget" in r["error"]
    assert s.actions_taken == 2


def test_9_emergency_stop_all_mechanisms():
    md = MockDesktop()
    md.add_window("Program Manager", "Progman", (0, 0, 1920, 1080))

    # (a) explicit stop event
    stopper = threading.Event()
    s = make_session(md, stop_event=stopper)
    stopper.set()
    r = s.execute(ComputerAction(action="screenshot"))
    assert r["blocked"] is True and "stopped" in r["error"]

    # (b) kernel cancellation (REPL 'stop' / voice barge-in / web cancel)
    cev = threading.Event()
    s2 = make_session(md, cancel_event=cev)
    assert s2.execute(ComputerAction(action="screenshot"))["executed"]
    cev.set()
    assert s2.stopped is True
    assert s2.execute(ComputerAction(action="screenshot"))["blocked"]

    # (c) global emergency stop hits EVERY active session
    md2, md3 = MockDesktop(), MockDesktop()
    s3, s4 = make_session(md2), make_session(md3)
    n = computeruse_emergency_stop()
    assert n >= 2
    assert s3.stopped and s4.stopped and s2.stopped
    assert s3.execute(ComputerAction(action="screenshot"))["blocked"]

    # (d) hotkey (injectable key state — no real keyboard in tests)
    md4 = MockDesktop()
    s5 = make_session(md4)
    held: set = set()
    hs = HotkeyStopper(lambda k: k in held, combo=("ctrl", "alt", "q"))
    assert hs.poll() is False                          # nothing held
    held.update(["ctrl", "alt", "q"])
    assert hs.poll() is True                           # combo held -> fires
    assert s5.stopped is True
    assert s5.execute(ComputerAction(action="screenshot"))["blocked"]


def test_10_verification_failure_never_success():
    md = MockDesktop()
    md.add_window("Notepad", "Notepad", (0, 0, 800, 600))
    s = make_session(md)
    # dispatch failure (no such window) -> blocked, nothing executed
    r = s.execute(ComputerAction(action="focus_window", target="DoesNotExist"))
    assert r["blocked"] is True
    # executed but the expected effect did NOT happen -> verified False + error
    s.observe()
    r2 = s.execute(ComputerAction(action="click", x=400, y=300,
                                  coordinate_source="window_rect",
                                  target="Notepad body",
                                  expected={"window_exists": "Chrome"}))
    assert r2["executed"] is True
    assert r2["verified"] is False
    assert "error" in r2 and "verification FAILED" in r2["error"]


def test_11_screenshot_retention():
    # default: in-memory hash ring, bounded, nothing on disk
    store = ScreenshotStore(max_frames=3)
    for i in range(5):
        store.push(bytes([i]) * 16)
    assert len(store) == 3
    assert store.purge() == 0 and len(store) == 0
    # optional save dir: files are created and purged
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        store2 = ScreenshotStore(max_frames=5, save_dir=Path(td) / "shots")
        store2.push(b"px" * 32)
        files = list((Path(td) / "shots").glob("frame_*.bin"))
        assert len(files) == 1
        assert store2.purge() == 1
        assert list((Path(td) / "shots").glob("frame_*.bin")) == []


# ------------------------------------------------------- end-to-end (kernel)
def test_12_kernel_integration_open_chrome(tmp_path):
    """'Open Chrome.' through the REAL AgentKernel: capability gate ASK
    (desktop.launch) -> task-scoped grant via approver -> execution on
    MockDesktop -> verified window exists -> COMPLETED + receipt."""
    from bee.agent.context import Context
    from bee.kernel import AgentKernel, TaskState
    from test_kernel_integration import ScriptedClient, tc

    cfg = load_config()
    cfg.cloud.enabled = False
    cfg.workspace = tmp_path
    client = ScriptedClient([
        tc("c1", "computer_window",
           {"action": "open_application", "target": "chrome",
            "expected": {"window_exists": "Chrome"}}),
        "Chrome is open.",
    ])
    asks: list = []

    def approver(tool, args, reason):
        asks.append((tool, reason))
        return True

    ctx = Context(cfg, workspace=tmp_path, client=client,
                  guard_on=True, guard_mode="unattended",
                  episodes_on=False, rag_on=False,
                  cancel_event=threading.Event())
    kernel = AgentKernel(ctx, approver=approver,
                         sessions_dir=tmp_path / "sessions",
                         receipts_path=tmp_path / "receipts.jsonl")
    ctx.kernel = kernel

    md = MockDesktop()
    md.add_window("Program Manager", "Progman", (0, 0, 1920, 1080))
    md.map_app("chrome", "Google Chrome")
    ctx.computeruse_desktop = md

    # "Open the Chrome browser window..." deliberately does NOT match the
    # `open <app>` fastpath (group would be "the"), so this exercises the
    # real LLM -> tool -> gate -> execute -> verify path.
    r = kernel.run("Open the Chrome browser window and confirm it is visible.",
                   session_id="cu-int")
    assert r.ok and r.task.state == TaskState.COMPLETED
    assert any(w.title == "Google Chrome" for w in md.list_windows())
    # the gate asked before executing (Phase 3 policy, desktop.launch ASK)
    assert any("desktop.launch" in t for t, _ in asks)
    # receipt records the tool with a verification result
    rows = [json.loads(l) for l in (tmp_path / "receipts.jsonl")
            .read_text(encoding="utf-8").splitlines()]
    cu = [row for row in rows if row["tool"] == "computer_window"]
    assert cu and cu[0].get("verification") in ("pass", "unverified")


# ---------------- emergency-stop wiring (audit 2026-10-08) ------------------
# STATUS.md listed three stop mechanisms, but the Ctrl+Alt+Q poller was only
# ever constructed inside tests — nothing in bee/ instantiated it — and
# computeruse.action_timeout / screenshot_retention_minutes / screenshot_save /
# hotkey / hotkey_enabled were read by no code path at all.

def test_17_creating_a_session_arms_the_hotkey_and_reads_config(monkeypatch, tmp_path):
    from bee.computeruse import tools as cu_tools
    armed: list = []
    monkeypatch.setattr(cu_tools, "start_emergency_hotkey",
                        lambda cfg: armed.append(cfg))
    ctx = make_ctx(tmp_path)
    s = cu_tools._get_session(ctx)
    assert armed == [ctx.cfg], "desktop control must arm the LLM-independent stop"
    cu = ctx.cfg.computeruse
    assert s.action_timeout == float(cu.action_timeout)
    assert s.screenshots.max_age == pytest.approx(cu.screenshot_retention_minutes * 60)
    assert s.screenshots.save_dir is None      # screenshot_save defaults False


def test_18_screenshot_save_and_retention_reach_the_store(monkeypatch, tmp_path):
    from bee.computeruse import tools as cu_tools
    monkeypatch.setattr(cu_tools, "start_emergency_hotkey", lambda cfg: None)
    ctx = make_ctx(tmp_path)
    ctx.cfg.computeruse.screenshot_save = True
    ctx.cfg.computeruse.screenshot_retention_minutes = 2.0
    s = cu_tools._get_session(ctx)
    assert s.screenshots.save_dir is not None
    assert s.screenshots.max_age == 120.0


def test_19_config_action_timeout_is_the_ceiling(monkeypatch):
    from bee.computeruse import session as cu_session
    seen: list[float] = []

    def fake_timeout(fn, timeout):
        seen.append(timeout)
        fn()
        return None, False

    monkeypatch.setattr(cu_session, "_with_timeout", fake_timeout)
    md = MockDesktop()
    md.add_window("Program Manager", "Progman", (0, 0, 100, 100))
    s = make_session(md, action_timeout=2.0)
    out = s.execute(ComputerAction(action="screenshot", timeout=30.0))
    assert seen == [2.0], f"a model asking for 30s must be capped by config: {seen}"
    assert out["executed"]


def test_20_hotkey_starts_once_is_introspectable_and_stops(monkeypatch):
    from bee.computeruse import session as cu_session
    cu_session.stop_emergency_hotkey()
    monkeypatch.setattr(cu_session, "default_windows_key_state",
                        lambda: (lambda name: False))
    cfg = load_config()
    cfg.computeruse.hotkey_enabled = True
    a = cu_session.start_emergency_hotkey(cfg)
    b = cu_session.start_emergency_hotkey(cfg)
    assert a is not None and a is b, "one poller per process"
    st = cu_session.hotkey_state()
    assert st["armed"] and st["combo"] == cfg.computeruse.hotkey
    assert tuple(a.combo) == tuple(k.strip() for k in cfg.computeruse.hotkey.split("+"))
    cu_session.stop_emergency_hotkey()
    assert not cu_session.hotkey_state()["armed"]


def test_21_hotkey_disabled_by_config_never_starts(monkeypatch):
    from bee.computeruse import session as cu_session
    cu_session.stop_emergency_hotkey()
    started: list = []
    monkeypatch.setattr(cu_session, "default_windows_key_state",
                        lambda: (lambda name: False))
    monkeypatch.setattr(cu_session.HotkeyStopper, "start",
                        lambda self: started.append(self))
    cfg = load_config()
    cfg.computeruse.hotkey_enabled = False
    assert cu_session.start_emergency_hotkey(cfg) is None
    assert started == []


def test_22_unavailable_key_backend_is_reported_not_silent(monkeypatch, caplog):
    """A deaf poller is the one failure an emergency stop must never hide."""
    import logging
    from bee.computeruse import session as cu_session
    cu_session.stop_emergency_hotkey()
    monkeypatch.setattr(cu_session, "default_windows_key_state", lambda: None)
    with caplog.at_level(logging.WARNING, logger="bee.computeruse"):
        assert cu_session.start_emergency_hotkey(load_config()) is None
    assert "NOT armed" in caplog.text


def test_23_unknown_hotkey_key_is_refused_with_a_reason(monkeypatch, caplog):
    import logging
    from bee.computeruse import session as cu_session
    cu_session.stop_emergency_hotkey()
    monkeypatch.setattr(cu_session, "default_windows_key_state",
                        lambda: (lambda name: False))
    cfg = load_config()
    cfg.computeruse.hotkey = "ctrl+alt+f13"
    with caplog.at_level(logging.WARNING, logger="bee.computeruse"):
        assert cu_session.start_emergency_hotkey(cfg) is None
    assert "unsupported key" in caplog.text
    assert not cu_session.hotkey_state()["armed"]


def test_24_kernel_releases_task_scoped_sessions(tmp_path, monkeypatch):
    """A long-lived Context must not accumulate one session (and one provenance
    + budget state) per task."""
    from bee.agent.context import Context
    from bee.kernel import AgentKernel, TaskState
    from bee.computeruse import session as cu_session
    from test_kernel_integration import ScriptedClient, tc
    monkeypatch.setattr(cu_session, "default_windows_key_state",
                        lambda: (lambda name: False))

    cfg = load_config()
    cfg.cloud.enabled = False
    cfg.workspace = tmp_path
    client = ScriptedClient([
        tc("c1", "computer_window",
           {"action": "open_application", "target": "chrome",
            "expected": {"window_exists": "Chrome"}}),
        "Chrome is open.",
    ])
    ctx = Context(cfg, workspace=tmp_path, client=client, guard_on=True,
                  guard_mode="unattended", episodes_on=False, rag_on=False,
                  cancel_event=threading.Event())
    kernel = AgentKernel(ctx, approver=lambda *a: True,
                         sessions_dir=tmp_path / "sessions",
                         receipts_path=tmp_path / "receipts.jsonl")
    ctx.kernel = kernel
    md = MockDesktop()
    md.add_window("Program Manager", "Progman", (0, 0, 1920, 1080))
    md.map_app("chrome", "Google Chrome")
    ctx.computeruse_desktop = md

    before = cu_session.active_sessions()
    r = kernel.run("Open the Chrome browser window and confirm it is visible.",
                   session_id="cu-prune")
    assert r.ok and r.task.state == TaskState.COMPLETED
    assert getattr(ctx, "cu_sessions", {}) == {}, "task-scoped session must be dropped"
    assert cu_session.active_sessions() == before, "stopped sessions must leave the registry"


# ------------------------------------- foreground window on the real backend --
class _FakeWin32:
    def __init__(self, handle=0, title="x", cls="c", rect=(0, 0, 10, 10), alive=True):
        self._h, self._t, self._c, self._r, self._alive = handle, title, cls, rect, alive

    def GetForegroundWindow(self):
        return self._h

    def IsWindow(self, h):
        return bool(h) and self._alive

    def GetWindowText(self, h):
        return self._t

    def GetClassName(self, h):
        return self._c

    def GetWindowRect(self, h):
        return self._r


def _fake_win32(monkeypatch, gui):
    """WindowsDesktop validates `import win32con, win32gui` at construction.
    These doubles stand in for BOTH names so the foreground-window logic runs
    on any runner (CI has no pywin32; nothing on this path reads win32con)."""
    import types
    monkeypatch.setitem(sys.modules, "win32con", types.ModuleType("win32con"))
    monkeypatch.setitem(sys.modules, "win32gui", gui)


def test_active_window_resolves_the_handle_directly(monkeypatch):
    """The old version searched list_windows() (which drops untitled windows),
    so a real foreground window with an empty title reported active=None and the
    active_window verification claimed failure where there was none."""
    import sys
    from bee.computeruse import desktop as D
    _fake_win32(monkeypatch, _FakeWin32(handle=1234, title=""))
    w = D.WindowsDesktop().active_window()
    assert w is not None, "an untitled foreground window must still resolve"
    assert w.active and w.title == ""


def test_active_window_is_none_only_when_truly_unknown(monkeypatch):
    import sys
    from bee.computeruse import desktop as D
    _fake_win32(monkeypatch, _FakeWin32(handle=0))
    assert D.WindowsDesktop().active_window() is None, \
        "a non-interactive session must report unknown, not guess a window"


def test_active_window_falls_back_when_the_api_raises(monkeypatch):
    import sys
    from bee.computeruse import WindowInfo, desktop as D

    class Boom:
        def GetForegroundWindow(self):
            raise RuntimeError("no win32 here")

    _fake_win32(monkeypatch, Boom())
    d = D.WindowsDesktop()
    d.list_windows = lambda: [WindowInfo(title="Notepad", cls="N", x=0, y=0, w=9, h=9,
                                          active=True)]
    assert d.active_window().title == "Notepad"
