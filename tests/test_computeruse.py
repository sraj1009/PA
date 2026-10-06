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
