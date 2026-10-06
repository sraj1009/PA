"""Structured telemetry + data-integrity hardening tests (audit 2026-10-06).

Covers:
  * LLM per-call latency + provider-failure telemetry (loop level)
  * agent_task terminal telemetry: success, latency, retries, verification
  * permission decision telemetry (capability ask: requested/denied)
  * metrics privacy scrub — secrets never reach the metrics stream
  * B2/M12 regression: vector rebuild must NOT duplicate rows
  * stats() exposes the structured keys

Run:  python -m pytest tests/test_telemetry.py -q
"""
from __future__ import annotations

import json
import threading
import time

import pytest

from bee.agent.client import LLMError
from bee import paths
from bee.monitor import metrics


# ------------------------------------------------------------------ helpers
def _slow_client(script, delay=0.12):
    from tests.test_kernel_integration import ScriptedClient

    class SlowScripted(ScriptedClient):
        def chat(self, name, msgs, **kw):
            time.sleep(delay)
            return super().chat(name, msgs, **kw)

    return SlowScripted(script)


@pytest.fixture
def metrics_file(tmp_path, monkeypatch):
    """Point the metrics stream at a temp file for the duration of a test."""
    f = tmp_path / "metrics.jsonl"
    monkeypatch.setattr(paths, "METRICS_FILE", f)
    monkeypatch.setattr(paths, "METRICS_DIR", tmp_path)
    return f


def _rows(f):
    return [json.loads(ln) for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()]


# ------------------------------------------------------------------ tests
def test_llm_latency_and_provider_failure(tmp_path, metrics_file):
    from tests.test_automation import _real_kernel
    from bee import privacy  # noqa: F401  (scrub is exercised via metrics)

    k, ctx, _ = _real_kernel(tmp_path, [], client=_slow_client(["Done with the task."]))
    r = k.run("Do a quick deterministic thing.", session_id="repl")
    assert r.ok is True

    llms = [x for x in _rows(metrics_file) if x["event"] == "llm"]
    assert llms and all(x["ok"] for x in llms)
    assert all(x["seconds"] >= 0.1 for x in llms), "LLM latency must be measured"
    assert all(x.get("model") for x in llms)

    agents = [x for x in _rows(metrics_file) if x["event"] == "agent_task"]
    assert agents and agents[-1]["ok"] is True
    assert agents[-1]["seconds"] is not None and agents[-1]["seconds"] >= 0.1
    assert agents[-1]["verification"] in ("pass", "unverified", "warn", "not_run")

    # provider failure path — the kernel retries transient provider failures
    # (bounded), so BOTH scripted attempts must fail for the task to fail
    k2, ctx2, _ = _real_kernel(tmp_path / "2", [], client=_slow_client(
        [LLMError("quota exceeded", kind="rate_limit"),
         LLMError("quota exceeded", kind="rate_limit")]))
    r2 = k2.run("Another task that hits a provider failure.", session_id="repl")
    assert r2.ok is False
    assert r2.retried, "provider failure must be visible as a kernel retry"
    bad = [x for x in _rows(metrics_file)
           if x["event"] == "llm" and not x["ok"]]
    assert bad and all(b["error_kind"] == "rate_limit" for b in bad)
    agents2 = [x for x in _rows(metrics_file) if x["event"] == "agent_task"]
    assert agents2[-1]["ok"] is False and agents2[-1]["retried"] >= 1


def test_permission_telemetry_capability_ask(tmp_path, metrics_file):
    from tests.test_automation import _real_kernel, make_worker, FakeClock, BASE
    from tests.test_kernel_integration import tc
    from datetime import timedelta

    future = (BASE + timedelta(hours=1)).isoformat()
    # approver DENIES everything — the ask must still be OBSERVABLE
    k, ctx, _ = _real_kernel(tmp_path,
                             [tc("c1", "automation_job",
                                 {"op": "create", "kind": "one_time", "at": future,
                                  "task": "denied job"}),
                              "I could not create that job."],
                             approver=lambda t, a, r: False)
    make_worker(tmp_path, k, FakeClock(BASE), ctx=ctx)
    k.run("Create a one-time job that must be denied.", session_id="repl")

    perms = [x for x in _rows(metrics_file) if x["event"] == "permission"]
    decisions = [p["decision"] for p in perms]
    assert "requested" in decisions and "denied" in decisions
    denied = [p for p in perms if p["decision"] == "denied"]
    assert any(p.get("capability") == "automation.manage" for p in denied)
    # the denied job was NOT created
    assert ctx.automation_worker.jobs() == []


def test_metrics_scrub_never_writes_secrets(tmp_path, metrics_file):
    key = "sk-abcdef1234567890abcdef1234567890abcdef12"
    card = "4242 4242 4242 4242"
    metrics.record("task", task=f"please note my key is {key} and card {card}",
                   model="local", ok=True, seconds=1.0)
    body = metrics_file.read_text(encoding="utf-8")
    assert key not in body, "API key must never reach the metrics stream"
    assert card[:4] + " " + card[5:9] not in body, "card number must be redacted"
    row = json.loads(body.strip().splitlines()[-1])
    assert row["event"] == "task" and row["model"] == "local"   # structure intact
    # short enum-like strings pass through untouched
    metrics.record("guard", tool="shell", action="deny", reason="recursive rm")
    last = _rows(metrics_file)[-1]
    assert last["tool"] == "shell" and last["reason"] == "recursive rm"


def test_vector_rebuild_no_duplicates(tmp_path, monkeypatch):
    """B2/M12: rebuilding twice must NOT double the row count."""
    from bee.memory import search

    monkeypatch.setattr(search.paths, "VECTOR_DIR", tmp_path / "vector")
    monkeypatch.setattr(search.md, "all_chunks",
                        lambda: [("a.md", "chunk one"), ("b.md", "chunk two")])

    class FakeClient:
        def embed(self, batch):
            return [[0.01] * 768 for _ in batch]

    store = search._VecStore(cfg=None, client=FakeClient())
    n1 = store.rebuild()
    assert n1 == 2
    n2 = store.rebuild()
    assert n2 == 2
    assert store._table().count_rows() == 2, "duplicate rows accumulated (B2)"
    # and the content actually changed between rebuilds is reflected
    monkeypatch.setattr(search.md, "all_chunks",
                        lambda: [("a.md", "chunk one (updated)"),
                                 ("b.md", "chunk two"), ("c.md", "chunk three")])
    assert store.rebuild() == 3
    assert store._table().count_rows() == 3


def test_stats_exposes_structured_keys(tmp_path, metrics_file):
    rows = [
        {"ts": time.time(), "event": "llm", "model": "local", "ok": True, "seconds": 0.5},
        {"ts": time.time(), "event": "llm", "model": "cloud", "ok": False,
         "seconds": 1.0, "error_kind": "auth"},
        {"ts": time.time(), "event": "permission", "decision": "denied",
         "capability": "automation.manage"},
        {"ts": time.time(), "event": "permission", "decision": "requested",
         "capability": "automation.manage"},
        {"ts": time.time(), "event": "agent_task", "ok": True, "seconds": 2.0,
         "verification": "pass", "retried": 0},
        {"ts": time.time(), "event": "agent_task", "ok": False, "seconds": 3.0,
         "verification": "fail", "retried": 1},
    ]
    with metrics_file.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    s = metrics.stats(window_hours=1)
    assert s["llm_calls"] == 2
    assert s["provider_failures"] == {"auth": 1}
    assert s["permission_denied"] == 1 and s["permission_asks"] == 1
    assert s["agent_tasks"] == 2 and s["agent_retried"] == 1
    assert s["agent_verify_fail"] == 1
    assert s["agent_success_rate"] == 0.5
    assert s["agent_avg_seconds"] == 2.5
