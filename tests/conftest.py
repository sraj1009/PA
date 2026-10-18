"""Test pyramid markers (audit 2026-10-06; Phase-7 categories 2026-10-08).

The suite is one directory, but the TESTS themselves are layered. Markers are
assigned automatically by filename here (no per-file edits needed) so the
pyramid can be addressed with:

    python -m pytest tests -q -m unit          # fast, no I/O beyond tmp
    python -m pytest tests -q -m security      # guard/risk/capability/privacy/netguard/auth
    python -m pytest tests -q -m "voice or scheduler"
    python -m pytest tests -q -m e2e           # full agent loops / web TestClient
    python -m pytest tests -q -m core          # MUST pass on a bare install
    python -m pytest tests -q -m "not optional"   # same, by exclusion

Layers (a file may sit in more than one):

  unit        pure functions & small classes — guard.classify, risk, privacy,
              netguard, fastpath regexes, verifier, mlrouter, kernel state
              machine, dsa references, capability metadata, offline rules
  integration kernel + loop with scripted LLM (no model/network), episodes,
              RAG, pipeline, sandbox, webapp TestClient, livekit config,
              structured memory, automation store/worker
  security    the permission & secret surface: guard, risk AST, capability
              gate, PII redaction, SSRF netguard, secret scan, web auth,
              sandbox jail, audit log
  agent       agent BEHAVIOR: full task lifecycle, follow-ups, routing
              decisions, commands, automation agent_task e2e (same kernel)
  tools       tool contracts: automation_job, automate, extractor, sandbox
  voice       realtime voice engine (state machine, VAD, barge-in,
              reconnect) + STT device probe + livekit config
  scheduler   durable automation: triggers, restart recovery, missed jobs,
              retry, concurrency, proactive policy
  e2e         end-to-end through the REAL kernel/run_agent/web stack with
              scripted stand-ins only (no Ollama, no network, no display)

Program Phase 7 categories (additive):
  core        = unit + integration minus files needing OPTIONAL packages —
                the default core suite must not fail because optional
                packages are unavailable
  windows     = Windows-specific behavior (run ON Windows; never emulated
                with fake assumptions on Linux CI)
  livekit     = LiveKit transport/config/bridge tests
  ml          = ML router / training pipeline / RAG (scikit-learn/numpy)
  optional    = files that importorskip on optional deps or a specific
                platform — they are expected to skip, never to block core

Run the whole pyramid:  python -m pytest tests -q
Do NOT weaken a test to get green — fix the code or document the
environment-specific reason (see docs/PRODUCTION_READINESS.md).
"""
from __future__ import annotations

import sys
from pathlib import Path

# make `from tests.test_kernel_integration import ...` work no matter how
# pytest is invoked (the files are a namespace package, no __init__.py)
_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest  # noqa: E402

_UNIT = [
    "test_kernel_unit", "test_guard", "test_risk", "test_privacy",
    "test_netguard", "test_fastpaths", "test_verifier", "test_mlrouter",
    "test_router_tiers", "test_secretscan", "test_dsa", "test_extractor",
    "test_capabilities", "test_offline", "test_audit",
    "test_config_precedence", "test_events", "test_providers",
    "test_plan_store",
    # A60a (2026-10-13): Ollama autostart — the launch, its gating, and the
    # router seam that used to degrade a task because nothing could start the server.
    "test_localserver",
    # A52 (2026-10-10): the eval headline is the run that ran, not the ledger.
    "test_eval_score",
    # A37 (2026-10-09): the real LLMClient streaming path (only the transport is
    # faked) + the static call-signature contract that catches the A27a/A37a
    # species before a blanket `except` can hide it.
    "test_streaming_contract", "test_static_contracts",
    # A40 (2026-10-09): lesson quality gate (lessons are injected into every
    # system prompt), kernel-owned reflection, the learning.reflect switch.
    "test_reflection_loop",
    # A41 (2026-10-09): the persisted engine choice — redirectable path, honest
    # failure reporting, corrupt-file handling.
    "test_engine_choice",
    # A42 (2026-10-09): the computer-use abort path (the stop verb must never be
    # capability-gated), driven through the real tool handlers.
    "test_computeruse_safety",
    # A44 (2026-10-09): the eval must not write the user's telemetry or the
    # training corpus (memory isolation alone left 322 eval episodes behind).
    "test_eval_hermeticity",
    # A43 (2026-10-09): automation_job create validation — a job that can never
    # fire is refused instead of stored as a silent no-op.
    "test_automation_tool_validation",
    # A45 (2026-10-09): planner inputs (real tool list), skill-index module names,
    # and the eval's expect_any premise.
    "test_plan_inputs",
    # Refactor (2026-10-18): the regex policy detectors extracted from
    # bee/agent/loop.py into bee/agent/policy.py — the loop only branches on
    # these booleans, and the legacy private names stay importable from loop.
    "test_agent_policy",
]
_INTEGRATION = [
    "test_kernel_integration", "test_automation", "test_episodes",
    "test_pipeline", "test_rag", "test_sandbox", "test_livekit",
    "test_engine_speed", "test_engines_session", "test_webauth",
    "test_structured_memory", "test_sft",
    "test_eval_gate", "test_skill_gate", "test_livekit_bridge",
    "test_livekit_live",
    "test_scheduling_unified",    # Phase 7 (2026-10-08): verified PORTABLE by running each file with its
    # "optional" package imports blocked (temp/blocker_plugin.py) — synthetic
    # audio / mocked desktop / stubbed subprocess, no real deps needed.
    "test_voice_engine", "test_stt_device", "test_computeruse",
    "test_jarvis_features",
    # Phase 8 (2026-10-08): conversation state, memory governance, typed
    # planner (scripted LLM, no model/network).
    "test_phase8_memory_planning",
    # Phase 11 (2026-10-08): proactive event intelligence (default-deny
    # policy, rate limits, quiet hours, external gating, sources).
    "test_proactive",
    # Phase 12 (2026-10-08): corrupted-memory / corrupt-persistence-file
    # reliability (degrade, never crash; salvage good rows).
    "test_phase12_reliability",
    # Coherence pass (2026-10-08): debt-fix regressions (N3 bus timeout,
    # N4 kernel-owned cancel scope, N9 full caps, H8 eval_safe budget).
    "test_debt_fixes",
    # Audit pass (2026-10-08): streaming-TTS busy/lifecycle contract and local
    # playback backend regressions (synthesized audio, no device, no network).
    "test_voice_tts",
    # Audit pass (2026-10-08): prompt-injection corpus through the real kernel
    # (untrusted wrap, gate escalation, grant revocation) — stubbed web, scripted LLM.
    "test_injection",
    # Audit pass (2026-10-08): operator switches that were read by no code
    # (computeruse/monitor/scheduler/model_gate/sandbox.max_output), the
    # app-wide logging handler, num_ctx + workspace resolution.
    "test_audit_fixes",
    # A47/A48 (2026-10-10): file claims checked against the disk (+ tool results
    # count as receipts), and three refusals in a row end the loop.
    "test_claim_grounding",
    # A49 (2026-10-10): code_run UTF-8 stdio + bee importable from any
    # workspace; shell is cmd.exe with a first-word PowerShell retry.
    "test_exec_tools",
    # A50 (2026-10-10): a request naming a BEE module gets its real signatures
    # (ast-read, never imported) so the model stops inventing APIs.
    "test_api_card",
    # A53/A54 (2026-10-10): the Welcome protocol only touches windows it owns;
    # /plan never erases a store it cannot read, and task ids stop repeating.
    "test_welcome_startup", "test_plan_store",
    # A51 (2026-10-10): the JSONL/markdown appenders are cross-process safe
    # (OS byte lock); this spawns real child writers to prove it.
    "test_safe_append",
    # A55/A56 (2026-10-10): the verify-retry ask names no mechanism and restates
    # the request; an honest refusal is no longer graded as a fabricated claim.
    "test_verify_retry",
    # Layering (2026-10-15): bee.tools must not statically depend on bee.agent
    # (the graph-reported cycle is a sanctioned call-time edge; pin it).
    "test_layering",
    # Self-improving bee4b (2026-10-16): pre-finalize self-critique loop,
    # SQLite ratings (RLAIF input), success-digest recall, SFT integration.
    "test_self_improve",
    # Security batch (2026-10-16): secret-free child env, always-refusal,
    # file-jail hardening, golden scrub-at-capture, recursive metrics scrub.
    "test_security_batch",
    # Web /voice route (2026-10-17): get_kernel NameError on every upload and
    # the float64 np.interp resample that crashed the ONNX VAD.
    "test_webapp_voice",
    # Web approvals (2026-10-17): interactive permission card over the /chat
    # SSE stream (bearer auth, one-time ids, timeout-deny) + the /voice route
    # staying off the event loop (live uvicorn, not TestClient).
    "test_web_approvals",
]
# Files that need OPTIONAL packages / a specific platform — the default CORE
# suite must not fail because these are absent (Program Phase 7). Phase 7
# classification rule (a file belongs here only if a blocked-import run FAILS):
#   REAL DEFECT        -> fix it, never xfail
#   MISSING OPTIONAL DEP -> importorskip inside the test (skip, never fail)
#   WRONG PLATFORM     -> pytest.mark.skipif(platform check) with the reason
#   NETWORK-DEPENDENT  -> make hermetic (fake resolver/transport), or move out
# of the deterministic suite. Empirical result 2026-10-08: only the livekit
# SDK is a true missing-dep gate (3 of its tests importorskip on it).
_OPTIONAL_DEPS = {
    "test_livekit": "livekit SDK",
}
_WINDOWS = ["test_computeruse", "test_jarvis_features"]
_LIVEKIT = ["test_livekit", "test_livekit_bridge", "test_livekit_live"]
_ML = ["test_mlrouter", "test_pipeline", "test_router_tiers", "test_rag",
       "test_phase7_repro"]
_CORE = [f for f in (_UNIT + _INTEGRATION) if f not in _OPTIONAL_DEPS]

MARKERS = {
    "unit": _UNIT,
    "integration": _INTEGRATION,
    "security": [
        "test_guard", "test_risk", "test_capabilities", "test_privacy",
        "test_netguard", "test_secretscan", "test_webauth", "test_sandbox",
        "test_audit", "test_injection", "test_computeruse_safety",
        "test_security_batch", "test_web_approvals",
    ],
    "agent": [
        "test_kernel_integration", "test_kernel_unit", "test_jarvis_features",
        "test_commands", "test_automation", "test_fastpaths",
        "test_router_tiers", "test_mlrouter",
    ],
    "tools": [
        "test_automate", "test_automation", "test_extractor", "test_sandbox",
        "test_exec_tools",
    ],
    "voice": [
        "test_voice_engine", "test_stt_device", "test_livekit",
        "test_voice_tts", "test_webapp_voice",
    ],
    "scheduler": [
        "test_automation", "test_scheduling_unified", "test_pipeline",
        "test_proactive",
    ],
    "e2e": [
        "test_kernel_integration", "test_engine_speed", "test_webauth",
        "test_jarvis_features", "test_automation",
    ],
    # ---- Program Phase 7 categories (additive; the layers above stay) ----
    "core": _CORE,                      # must pass on a bare install
    "windows": _WINDOWS,                # run on Windows only
    "livekit": _LIVEKIT,
    "ml": _ML,
    "optional": sorted(_OPTIONAL_DEPS), # importorskip-friendly; never blocks core
}


def pytest_collection_modifyitems(config, items):
    for item in items:
        # item.path (pathlib) — pytest 9 removed the old fspath attribute.
        # MARKERS stores full module names (test_guard), so match on the full
        # stem (with the test_ prefix) and fall back to the bare name.
        try:
            stem = item.path.name.rsplit(".py", 1)[0]
        except AttributeError:
            stem = item.fspath.purebasename.rsplit(".py", 1)[0]
        base = stem[len("test_"):] if stem.startswith("test_") else stem
        for marker, files in MARKERS.items():
            if stem in files or base in files:
                item.add_marker(getattr(pytest.mark, marker))


def pytest_configure(config):
    for name in MARKERS:
        config.addinivalue_line("markers", f"{name}: test-pyramid layer ({name})")
    # sklearn cross-version unpickle notice (1.9.0 artifact -> 1.9.1 load env).
    # Safe: minor drift is sklearn-supported; mlrouter does its own explicit
    # version check + clear message (Phase 7). Message-only filter so it also
    # works when sklearn is absent (bare core install).
    config.addinivalue_line("filterwarnings", "ignore:Trying to unpickle estimator")
    _isolate_append_only_streams()
    _isolate_post_task_model_calls()


def _isolate_post_task_model_calls():
    """Reflection (A40b) adds ONE local-model call after every non-trivial task,
    on every surface. That is real product behaviour, but it must not be visible
    to tests that assert on the task loop: `test_6_failed_task_provider_retry`
    counts LLM calls to prove the retry budget ("exactly one retry, then stop"),
    and a post-task review call is not part of that budget — nor is any test's
    scripted reply meant to be eaten by it.

    So the suite turns the switch off by default, exactly as it redirects metrics
    and lessons: a behavioural isolation, not a weakened assertion. The capability
    has its own coverage with it explicitly re-enabled —
    tests/test_reflection_loop.py.
    """
    import bee.config as bc
    if getattr(bc.load_config, "_bee_tests_no_reflect", False):
        return
    real = bc.load_config

    def load_config_no_reflect(*a, **kw):
        cfg = real(*a, **kw)
        cfg.learning.reflect = False
        return cfg

    load_config_no_reflect._bee_tests_no_reflect = True
    bc.load_config = load_config_no_reflect



# ------------------------------------------------------------------ isolation
# Applied in pytest_configure (NOT a fixture) on purpose: script-style modules
# like tests/test_monitor.py record events while they are being *collected*,
# which happens before any fixture runs. A fixture-based guard leaked one
# `test_probe` event per run into the user's real metrics.jsonl.
_STREAM_MP = None


def _isolate_append_only_streams():
    """A test run must not write into the user's real telemetry or training data.

    These streams feed things the USER sees: `metrics.jsonl` drives the dashboard
    KPIs *and* `cfg.alerts` thresholds (so a synthetic failure can raise a real
    desktop alert), and `train/episodes/` is the corpus the nightly router retrain
    eats (so synthetic episodes become training data). Observed on 2026-10-08:
    the live dashboard showed 563/639 `automation_job` calls failing and 101
    guard denials — suite noise, not the user's machine.

    A test that redirects these paths for itself still wins: its own monkeypatch
    applies later and restores to these tmp paths.
    """
    global _STREAM_MP
    import tempfile
    from pathlib import Path

    from bee import paths

    root = Path(tempfile.mkdtemp(prefix="bee_test_streams_"))
    mdir = root / "metrics"
    mdir.mkdir()
    sdir = root / "skills"
    sdir.mkdir()
    _STREAM_MP = pytest.MonkeyPatch()
    _STREAM_MP.setattr(paths, "METRICS_DIR", mdir)
    _STREAM_MP.setattr(paths, "METRICS_FILE", mdir / "metrics.jsonl")
    # skills/ is the agent's own procedure library: teach-back writes CANDIDATE
    # cards there and the nightly `skill_gate` job evaluates them, so a test that
    # runs the flywheel would leave the user with a skill the assistant believes
    # it has (observed: `skills/graph_operations/`, source=agent, body = Python
    # code where the markdown should be).
    _STREAM_MP.setattr(paths, "SKILLS_DIR", sdir)
    # settings.json holds the user's persisted ENGINE choice — which brain BEE
    # defaults to on every surface. `ask_engine()` writes it whenever stdin is not
    # a tty, so any test that launched the web/voice/talk/clap entry points under
    # a pipe would silently rewrite the user's default model (A41a). Copied rather
    # than emptied so tests that READ the engine still see the real choice.
    try:
        if paths.SETTINGS_JSON.exists():
            (root / "settings.json").write_text(
                paths.SETTINGS_JSON.read_text(encoding="utf-8"), encoding="utf-8")
        _STREAM_MP.setattr(paths, "SETTINGS_JSON", root / "settings.json")
    except Exception:
        pass

    # memory/ is the user's own history: profile facts, diary, long-term notes,
    # the structured store and its vector index. A test run must not add facts
    # to it (an invented GPU from an eval fixture ended up in store.json as a
    # `source: user` fact). Copied rather than emptied so tests that READ memory
    # still see the real content — writes just go to the copy.
    try:
        import shutil

        memroot = root / "memory"
        shutil.copytree(paths.MEMORY_DIR, memroot, dirs_exist_ok=True)
        for attr, sub in (("MEMORY_DIR", ""), ("DIARY_DIR", "diary"),
                          ("LESSONS_DIR", "lessons"), ("VECTOR_DIR", "vectors"),
                          # the kernel's audit streams. They live under memory/ but
                          # are their own module constants now, so a list of the
                          # older names silently misses them: every kernel built
                          # without an explicit sessions_dir appended to the user's
                          # real receipts.jsonl (measured 2026-10-13: 1569 of 1572
                          # rows carry an `eval-*` session id).
                          ("SESSIONS_DIR", "sessions")):
            _STREAM_MP.setattr(paths, attr, memroot / sub if sub else memroot)
        for attr, fn in (("PROFILE_MD", "profile.md"),
                         ("LONGTERM_MD", "longterm.md"),
                         ("SYSTEM_MD", "system.md"),
                         ("RECEIPTS_FILE", "receipts.jsonl")):
            _STREAM_MP.setattr(paths, attr, memroot / fn)
    except Exception:
        pass

    # audit.jsonl sits at the project ROOT, not under memory/, so the block above
    # cannot reach it. Copied so `recent(n)` readers (the /audit view, the
    # dashboard) still see the real trail while writes go to the copy.
    try:
        import shutil

        if paths.AUDIT_FILE.exists():
            shutil.copy2(paths.AUDIT_FILE, root / "audit.jsonl")
        for rot in sorted(paths.AUDIT_FILE.parent.glob(paths.AUDIT_FILE.name + ".*")):
            shutil.copy2(rot, root / rot.name)
        _STREAM_MP.setattr(paths, "AUDIT_FILE", root / "audit.jsonl")
    except Exception:
        pass

    # train/ and evals/ are the OUTPUTS of the flywheel and of scoring, and neither
    # was ever redirected (A61, measured 2026-10-15). Two live leaks came from that:
    # a suite run appends the scripted model's rows to evals/results.jsonl — the same
    # ledger `bee.cli eval` reads as history and evals/verify_suite.py quotes into the
    # git-tracked evals/REPORT.md, so the fake passes became the project's own evidence
    # — and teach-back writes a "cloud teacher" golden per scored turn into
    # train/golden/cloud_golden.jsonl, the corpus the nightly SFT build turns into
    # training prompts (2 rows of `resp='ok-response'` appeared mid-suite-run).
    # ROUTER_MODEL is redirected with them: a suite-side retrain would overwrite the
    # user's live routing model. No try/except here on purpose: the older blocks above
    # swallow their own failures, which is exactly how a half-listed redirect stayed
    # invisible — a broken copy must fail collection loudly, not leak into train/.
    import shutil

    troot = root / "train"
    eroot = root / "evals"
    (troot / "episodes").mkdir(parents=True, exist_ok=True)
    eroot.mkdir(parents=True, exist_ok=True)
    # copying, not emptying: the ledger, tasks.yaml and the golden corpus must stay
    # READABLE, or a test that drives the real runner fails for the wrong reason.
    # episodes are the exception — they are the user's real history and the SFT
    # corpus, and reading 2 MB of live episodes would make results machine-dependent.
    for p in sorted(paths.TRAIN_DIR.iterdir()) if paths.TRAIN_DIR.exists() else []:
        if p.is_dir() and p.name != "episodes":
            shutil.copytree(p, troot / p.name, dirs_exist_ok=True)
        elif p.is_file():
            shutil.copy2(p, troot / p.name)
    for p in sorted(paths.EVALS_DIR.iterdir()) if paths.EVALS_DIR.exists() else []:
        if p.is_dir():
            shutil.copytree(p, eroot / p.name, dirs_exist_ok=True)
        elif p.is_file():
            shutil.copy2(p, eroot / p.name)
    _STREAM_MP.setattr(paths, "TRAIN_DIR", troot)
    _STREAM_MP.setattr(paths, "EPISODES_DIR", troot / "episodes")
    _STREAM_MP.setattr(paths, "ROUTER_MODEL", troot / "router_model.joblib")
    _STREAM_MP.setattr(paths, "EVALS_DIR", eroot)
    _STREAM_MP.setattr(paths, "EVAL_RESULTS", eroot / "results.jsonl")


def pytest_unconfigure(config):
    if _STREAM_MP is not None:
        _STREAM_MP.undo()
