"""Phase 12 — reliability: CORRUPTED MEMORY (and corrupt persistence files).

The spec requires: "Test: ... corrupted memory ..." — a corrupted store must
DEGRADE (empty or salvaged), never crash the agent, and the agent must keep
working afterwards (new items, new sessions, new jobs).

Covered here (the rest of the Phase-12 reliability list is covered by
existing suites: cloud/local unavailable -> test_providers/test_kernel_*;
tool failure/timeout/cancellation/verification -> test_kernel_integration;
retry/scheduler restart -> test_scheduling_unified/test_automation;
network failure -> test_voice_engine; missing optional dependency ->
portability audit + test_livekit importorskip):

  1. StructuredMemory with a garbage store.json      -> empty store, no crash
  2. StructuredMemory with one corrupt row           -> good rows SALVAGED
  3. StructuredMemory with a wrong-shape file        -> no crash
  4. After ANY corruption: remember/recall/save work -> agent keeps running
  5. AgentSession.load with a garbage session file   -> None, fresh session ok
  6. JobStore with corrupt job file                  -> load None, list skips
  7. JobStore with corrupt executions.jsonl          -> bad lines skipped
  8. JobStore with corrupt notifications.json / rules.json -> []

Run:  python -m pytest tests/test_phase12_reliability.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bee.memory.store import StructuredMemory          # noqa: E402
from bee.kernel.session import AgentSession            # noqa: E402
from bee.automation.store import JobStore              # noqa: E402

GARBAGE = b"\x00\xff\xfe not json at all \x00"


# ---------------------------------------------------------- StructuredMemory
def test_01_corrupt_memory_file_degrades_to_empty(tmp_path):
    p = tmp_path / "store.json"
    p.write_bytes(GARBAGE)
    mem = StructuredMemory(p)                 # must not raise
    assert mem.recall("anything", k=10) == []


def test_02_corrupt_memory_file_then_agent_works(tmp_path):
    """After a corrupt store, the agent keeps working: remember/recall/save
    all succeed and the NEW store is clean (no garbage persisted)."""
    p = tmp_path / "store.json"
    p.write_bytes(GARBAGE)
    mem = StructuredMemory(p)
    it = mem.remember("user fact after corruption", type="fact", source="user")
    # remember() auto-persists to the (repaired) store file
    mem2 = StructuredMemory(p)                # re-load the repaired store
    hits = mem2.recall("user fact", k=5)
    assert any(i.id == it.id for i in hits)


def test_03_memory_salvages_good_rows(tmp_path):
    """One corrupt row among two good rows: the good rows survive, the bad
    one is skipped (not silently dropped, not a crash)."""
    a = StructuredMemory(tmp_path / "store.json")
    good1 = a.remember("first good fact", source="user")
    good2 = a.remember("second good fact", source="user")
    rows = json.loads((tmp_path / "store.json").read_text())["items"]
    rows.append({"id": "mem_broken", "content": None, "source": "!!!bad"})
    (tmp_path / "store.json").write_text(json.dumps({"items": rows}))
    mem = StructuredMemory(tmp_path / "store.json")   # must not raise
    ids = {i.id for i in mem.all()}
    assert good1.id in ids and good2.id in ids
    assert "mem_broken" not in ids


def test_04_memory_wrong_shape_file_no_crash(tmp_path):
    """A store file whose top level is a LIST of items (or a bare string)
    degrades gracefully instead of raising AttributeError/TypeError."""
    a = StructuredMemory(tmp_path / "a.json")
    it = a.remember("list-shaped store", source="user")
    items = json.loads((tmp_path / "a.json").read_text())["items"]
    (tmp_path / "list.json").write_text(json.dumps(items))   # bare list
    mem = StructuredMemory(tmp_path / "list.json")
    assert any(i.id == it.id for i in mem.all())
    (tmp_path / "str.json").write_text('"just a string"')
    StructuredMemory(tmp_path / "str.json")     # must not raise


# -------------------------------------------------------------- AgentSession
def test_05_corrupt_session_file_degrades_to_new(tmp_path):
    f = tmp_path / "sess_abc.json"
    f.write_bytes(GARBAGE)
    assert AgentSession.load(tmp_path, "sess_abc") is None
    # a fresh session can be created, saved and reloaded in the same dir
    s = AgentSession(id="sess_new")
    s.active_task_text = "task after corruption"
    s.save(tmp_path)
    assert AgentSession.load(tmp_path, "sess_new").active_task_text == \
        "task after corruption"


# ------------------------------------------------------------------ JobStore
def test_06_corrupt_job_files_degrade(tmp_path):
    store = JobStore(tmp_path)
    good = store._job_path("j_good")
    bad = store._job_path("j_bad")
    # a well-formed job + a garbage job in the same directory
    from bee.automation.models import Job, JobTrigger
    job = Job(id="j_good", owner="test", description="d",
              action={"type": "notify", "text": "hi"},
              trigger=JobTrigger(kind="one_time",
                                 at="2026-12-31T12:00:00+00:00"))
    store.save_job(job)
    bad.write_bytes(GARBAGE)
    assert store.load_job("j_bad") is None
    jobs = store.load_all_jobs()
    assert [j.id for j in jobs] == ["j_good"]   # corrupt one skipped, not fatal
    # the worker's restart path uses load_all_jobs -> clean state


def test_07_corrupt_executions_skips_bad_lines(tmp_path):
    store = JobStore(tmp_path)
    p = tmp_path / "executions.jsonl"
    good_line = json.dumps({"id": "ex_ok", "job_id": "j1", "status": "ok"})
    p.write_text(good_line + "\n" + "{{{ not json\n" +
                 json.dumps({"id": "ex_ok2", "job_id": "j1", "status": "ok"})
                 + "\n")
    hist = store.executions()                  # must not raise
    assert {e.id for e in hist.entries} == {"ex_ok", "ex_ok2"}


def test_08_corrupt_notifications_and_rules_degrade(tmp_path):
    store = JobStore(tmp_path)
    (tmp_path / "notifications.json").write_bytes(GARBAGE)
    (tmp_path / "rules.json").write_bytes(GARBAGE)
    assert store.load_notifications() == []
    assert store.load_rules() == []
    # and both stores are usable again immediately after
    from bee.automation.events import ProactiveRule
    store.save_rules([ProactiveRule(kind="timer", action={"type": "notify"})])
    assert len(store.load_rules()) == 1
