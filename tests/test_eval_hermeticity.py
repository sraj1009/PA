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


class _SpyCtx:
    def __init__(self, ws):
        from bee.config import load_config
        self.cfg = load_config()
        self.workspace = pathlib.Path(ws)
