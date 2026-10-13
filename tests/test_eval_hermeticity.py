"""Eval hermeticity for telemetry and the training corpus (A44).

`_isolated_memory()` (A31b) redirected memory, so a scored run kept appending to
the two streams the USER reads: `metrics/metrics.jsonl` (dashboard KPIs + the
`cfg.alerts` thresholds, so a synthetic failure can raise a real desktop alert)
and `train/episodes/*.jsonl` (the corpus the nightly router retrain and the SFT
build eat). Measured after one full run on 2026-10-09: 322 of 375 of that day's
episode rows were eval prompts, and 473 new metric rows carried eval session ids.
"""
from __future__ import annotations

import json
import pathlib

from bee import paths
from bee.evals import runner
from bee.monitor import metrics


class _null:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_recording_inside_the_isolation_reaches_neither_real_file(tmp_path, monkeypatch):
    real_metrics = paths.METRICS_FILE
    real_episodes = paths.EPISODES_DIR
    before = real_metrics.read_bytes() if real_metrics.exists() else b""
    before_files = sorted(p.name for p in real_episodes.glob("*.jsonl")) \
        if real_episodes.exists() else []

    monkeypatch.setattr(runner, "_isolated_memory", lambda: _null())
    monkeypatch.setattr(runner, "_restore_workspace", lambda p: _null())
    ctx = _SpyCtx(tmp_path)
    seen = {}

    def spy(_ctx, model=None, only=None):
        # inside the suite: writes must land in a temp tree
        seen["metrics"] = str(paths.METRICS_FILE)
        seen["episodes"] = str(paths.EPISODES_DIR)
        metrics.record("tool", tool="code_run", ok=False, seconds=0.1)
        (paths.EPISODES_DIR / "2099-01-01.jsonl").write_text('{"task": "eval prompt"}\n',
                                                             encoding="utf-8")
        return []

    monkeypatch.setattr(runner, "_run_suite", spy)
    runner.run_suite(ctx)

    assert "bee_eval_telemetry_" in seen["metrics"], seen
    assert "bee_eval_telemetry_" in seen["episodes"], seen
    after = real_metrics.read_bytes() if real_metrics.exists() else b""
    assert after == before, "the run appended to the user's real metrics stream"
    after_files = sorted(p.name for p in real_episodes.glob("*.jsonl")) \
        if real_episodes.exists() else []
    assert after_files == before_files, "the run wrote into the training corpus"


def test_the_paths_are_restored_after_the_run(tmp_path, monkeypatch):
    saved = (paths.METRICS_FILE, paths.EPISODES_DIR, paths.SKILLS_DIR)
    monkeypatch.setattr(runner, "_isolated_memory", lambda: _null())
    monkeypatch.setattr(runner, "_restore_workspace", lambda p: _null())
    monkeypatch.setattr(runner, "_run_suite", lambda c, model=None, only=None: [])
    runner.run_suite(_SpyCtx(tmp_path))
    assert (paths.METRICS_FILE, paths.EPISODES_DIR, paths.SKILLS_DIR) == saved


def test_the_isolation_covers_every_append_only_stream():
    """The defect class is 'a stream nobody redirected' — so the list itself is
    pinned, not just the two paths I thought of."""
    import inspect
    src = inspect.getsource(runner._isolated_telemetry)
    for key in ("METRICS_DIR", "METRICS_FILE", "EPISODES_DIR", "SKILLS_DIR"):
        assert key in src, f"_isolated_telemetry no longer redirects {key}"
    src = inspect.getsource(runner._isolated_memory)
    for key in ("SESSIONS_DIR", "RECEIPTS_FILE", "AUDIT_FILE"):
        assert key in src, (f"_isolated_memory no longer redirects {key} — a scored "
                            "run then writes the user's audit trail")


def test_the_audit_path_resolves_through_paths_so_it_can_be_redirected():
    """`audit_path()` returned `paths.PROJECT_ROOT / "audit.jsonl"` inline.
    PROJECT_ROOT is the checkout and is never redirected, so no caller could move
    the stream — the eval's tool rows landed in the user's audit file (3142 rows
    with no session field, i.e. unrecoverable after the fact)."""
    from bee.security import audit
    real = paths.AUDIT_FILE
    assert audit.audit_path() == real
    with runner._isolated_memory() as root:
        assert audit.audit_path() != real
        # root is the memory COPY; the audit file lives one level up, in the
        # same throwaway tree the context manager rmtree's on exit
        assert str(audit.audit_path()).startswith(str(root.parent)), audit.audit_path()
    assert audit.audit_path() == real


def test_a_kernel_built_inside_the_isolation_uses_the_copy(tmp_path):
    """`_run_suite` documents that the kernel resolves its sessions and receipts at
    construction time so they point at the copy. Both were hardcoded to
    PROJECT_ROOT/memory, so the promise was false: measured 2026-10-13, 1568 of 1571
    live receipt rows and 2540 of 2543 rotated ones carry an `eval-*` session id,
    plus 23 memory/sessions/eval-*.json files from runs that only meant to score."""
    from bee.kernel import AgentKernel
    ctx = _SpyCtx(tmp_path)
    saved = (paths.SESSIONS_DIR, paths.RECEIPTS_FILE)
    with runner._isolated_memory() as root:
        k = AgentKernel(ctx, approver=lambda *a, **kw: False)
        assert str(k.sessions_dir).startswith(str(root)), k.sessions_dir
        assert str(k.receipts.path).startswith(str(root)), k.receipts.path
    # compare against what the run found, not a literal: conftest already moved
    # the suite off the user's real memory tree, so the hardcoded path here would
    # assert the harness's own redirect back into place.
    assert (paths.SESSIONS_DIR, paths.RECEIPTS_FILE) == saved


def test_the_pytest_harness_itself_keeps_the_audit_streams_off_the_real_tree():
    """Making SESSIONS_DIR/RECEIPTS_FILE module constants is what exposed the
    second half of this bug: conftest's memory isolation listed the older names
    only, so a kernel built anywhere in the suite without an explicit
    `sessions_dir=` appended to the user's real receipts. Pinned as a static
    check because the leak is in the harness, not in a product call path."""
    real = paths.PROJECT_ROOT / "memory"
    assert not str(paths.SESSIONS_DIR).startswith(str(real)), paths.SESSIONS_DIR
    assert not str(paths.RECEIPTS_FILE).startswith(str(real)), paths.RECEIPTS_FILE
    assert not str(paths.AUDIT_FILE).startswith(str(paths.PROJECT_ROOT)), paths.AUDIT_FILE


def _digest(root) -> str:
    import hashlib
    h = hashlib.sha256()
    base = pathlib.Path(root)
    for p in sorted(base.rglob("*")):
        if p.is_file():
            h.update(p.name.encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def _user_state_snapshot() -> tuple:
    """Everything a scored run must leave byte-for-byte alone."""
    real_memory = paths.PROJECT_ROOT / "memory"
    audit = paths.PROJECT_ROOT / "audit.jsonl"
    return (_digest(real_memory),
            audit.read_bytes() if audit.exists() else b"")


def test_a_real_scored_run_leaves_the_users_audit_state_byte_identical(tmp_path, monkeypatch):
    """Drives the REAL stack (run_suite -> AgentKernel -> run_agent) and fakes only
    the model. Every earlier test in this file faked `run_suite` or wrote from inside
    the context manager, so none of them could see a path the kernel resolved itself."""
    from bee.agent.context import create_context
    from bee.config import load_config
    from tests.test_kernel_integration import ScriptedClient

    ctx = create_context(load_config(), client=ScriptedClient([
        "There are 25 prime numbers between 1 and 100."]))
    ctx.workspace = pathlib.Path(tmp_path)
    before = _user_state_snapshot()
    monkeypatch.setattr(runner, "_restore_workspace", lambda p: _null())

    rows = runner.run_suite(ctx, only=["math_sieve"])

    assert rows and rows[0]["ok"], rows
    assert _user_state_snapshot() == before, (
        "the scored run wrote into the user's real audit state (memory/sessions, "
        "memory/receipts.jsonl, memory/checkpoints or audit.jsonl) — see "
        "paths.SESSIONS_DIR / paths.RECEIPTS_FILE / paths.AUDIT_FILE")


class _SpyCtx:
    def __init__(self, ws):
        from bee.config import load_config
        self.cfg = load_config()
        self.workspace = pathlib.Path(ws)
