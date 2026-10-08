"""Phase 8 — CONVERSATION + MEMORY + PLANNING (2026-10-08).

Required scenarios (program spec):
  * follow-up context      ("Remind me to send the invoice." -> "Tomorrow.")
  * pronoun references     ("open that folder" resolves against the task)
  * task continuation      ("Actually at 10 AM." updates the SAME job)
  * plan creation          (kernel records a typed plan kind before execution)
  * plan failure           (unregistered tool -> rejected BEFORE ToolBus)
  * re-planning            (verification failure -> retry -> replans counter)
  * memory conflicts       (same key -> old item superseded, tombstoned)
  * forgetting             (explicit forget is respected, recall returns none)
  * expired memory         (past expiry excluded from recall, purged by expire)
  * provenance             (source labels, inference cap, no silent promotion)

Plus: impossible requests short-circuit WITHOUT an LLM call.

No model, no network: scripted LLM stand-ins (same pattern as
test_kernel_integration) and in-memory fakes for the automation worker.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

import pytest

from bee.agent.context import Context
from bee.config import load_config
from bee.kernel import AgentKernel, TaskState
from bee.kernel import planner as planner_mod
from bee.kernel.models import Action, Plan
from bee.kernel.session import AgentSession
from tests.test_kernel_integration import ScriptedClient, make_kernel


# ================================================================ PLANNING
def test_classify_intent_matrix():
    assert planner_mod.classify_intent("what is a router?")[0] == "informational"
    assert planner_mod.classify_intent("explain how DNS works")[0] == "informational"
    assert planner_mod.classify_intent("open chrome")[0] == "single_action"
    assert planner_mod.classify_intent("delete the temp folder")[0] == "requires_approval"
    assert planner_mod.classify_intent("send the invoice to finance")[0] == "requires_approval"
    assert planner_mod.classify_intent("   ")[0] == "impossible"
    # dangling reference WITHOUT an active task -> ambiguous
    k, why = planner_mod.classify_intent("do it")
    assert k == "ambiguous" and "dangling" in why
    # ...the SAME words with an active task are a legitimate follow-up
    s = AgentSession(id="p")
    s.active_task_id = "task-1"
    s.active_task_text = "open the file"
    assert planner_mod.classify_intent("do it", s)[0] != "ambiguous"
    # several distinct actions -> multi_step
    assert planner_mod.classify_intent(
        "open the file, analyze it, then verify the output")[0] in (
        "multi_step", "requires_approval")


def test_plan_creation_records_kind(tmp_path):
    k, client, _ = make_kernel(tmp_path, ["A router forwards packets."])
    r = k.run("Explain what a router does.", session_id="p1")
    assert r.ok and r.task.state == TaskState.COMPLETED
    assert r.task.plan is not None and r.task.plan.kind == "informational"
    d = r.task.plan.to_dict()
    assert d["kind"] == "informational" and "replans" in d
    # plan is validated: goal present, risks legal
    ok, errs = planner_mod.validate_plan(r.task.plan, k.bus)
    assert ok, errs


def test_impossible_request_short_circuits_without_llm(tmp_path):
    k, client, _ = make_kernel(tmp_path, ["this must never be called"])
    r = k.run("   ", session_id="p2")
    assert client.calls == [], "an impossible plan must not reach the LLM"
    assert r.ok
    # the kernel asks the user to rephrase — that IS 'waiting for user'
    assert r.task.state == TaskState.WAITING_FOR_USER
    assert r.task.plan.kind == "impossible"
    assert r.output


def test_plan_failure_rejected_before_toolbus(tmp_path, monkeypatch):
    k, client, _ = make_kernel(tmp_path, ["never called"])

    def bad_plan(kind, text, session=None):
        return Plan(goal=text, steps=[Action(tool="no_such_tool_xyz", risk="low")],
                    rationale="injected", kind="single_action")

    monkeypatch.setattr(planner_mod, "build_plan", bad_plan)
    r = k.run("do the thing", session_id="p3")
    assert client.calls == [], "rejected plan must not execute anything"
    assert r.task.state == TaskState.FAILED
    assert "plan rejected" in r.task.error
    assert "no_such_tool_xyz" in r.task.error


def test_replan_counter_increments_on_retry(tmp_path):
    # same scenario as test_kernel_integration.test_7 (claim wrong effect ->
    # kernel re-plans with a correction note): Phase 8 adds the counter.
    from tests.test_kernel_integration import tc
    k, client, _ = make_kernel(tmp_path, [
        tc("c1", "shell", {"command": "mkdir wrongdir"}),
        "Done — folder created.",
        tc("c2", "shell", {"command": "mkdir invoices"}),
        "Done — invoices folder created.",
    ])
    r = k.run("Create a folder called invoices.", session_id="p4")
    assert r.retried and r.task.retry_count == 1
    assert r.task.plan.replans == 1, "the retry must be recorded as a replan"


# ===================================================== CONVERSATION STATE
def test_followup_context_merges_time_hints():
    s = AgentSession(id="f1")
    s.add_turn("user", "Remind me to send the invoice.")
    s.active_task_id = "task-inv"
    s.active_task_text = "Remind me to send the invoice."
    d1, r1 = s.resolve_followup("Tomorrow.")
    assert d1 == "continue"
    assert "Tomorrow" in r1
    d2, r2 = s.resolve_followup("Actually at 10 AM.")
    assert d2 == "continue"
    assert "10 AM" in r2
    # the context block carries both the original task and the time hints so
    # the kernel/LLM can act on the merged intent
    block = s.context_block()
    assert "send the invoice" in block
    assert s.last_time_hint


def test_pronoun_reference_resolves_against_active_task():
    s = AgentSession(id="f2")
    s.add_turn("user", "Open the folder C:\\work\\reports and list it.")
    s.active_task_id = "task-folder"
    s.active_task_text = "Open the folder C:\\work\\reports and list it."
    d, merged = s.resolve_followup("open that folder")
    assert d == "continue"
    assert "reports" in merged, "the pronoun must resolve to the referenced entity"


def test_temporal_schedule_updates_existing_job(tmp_path, monkeypatch):
    """'Remind me to send the invoice.' -> 'Tomorrow.' -> 'Actually at 10 AM.'
    must produce ONE durable job whose trigger moves — never a duplicate."""
    from bee.kernel.memory_if import _Temporal
    from bee.memory import md
    monkeypatch.setattr(md, "diary_add", lambda *a, **k: None)  # no real diary

    class FakeWorker:
        default_timezone = "Asia/Kolkata"

        def __init__(self):
            self._jobs = []

        def create_job(self, job):
            job.next_run = datetime.now(timezone.utc).isoformat()
            self._jobs.append(job)
            return job

        def reschedule(self, job, trigger):
            job.trigger = trigger
            job.next_run = datetime.now(timezone.utc).isoformat()
            return job

        def jobs(self):
            return list(self._jobs)

    w = FakeWorker()
    t = _Temporal(lambda: w)
    r1 = t.schedule("send the invoice", "09:00")
    assert r1["ok"] and not r1.get("updated")
    r2 = t.schedule("send the invoice", "10:00")   # "Actually at 10 AM."
    assert r2["ok"] and r2.get("updated") is True
    assert r2["job"] == r1["job"], "follow-up must UPDATE the existing job"
    assert len(w._jobs) == 1, "no duplicate job may be created"
    assert w._jobs[0].trigger.at.endswith("10:00")
    # a DIFFERENT reminder still creates a new job
    r3 = t.schedule("call the dentist", "08:00")
    assert len(w._jobs) == 2 and r3["job"] != r1["job"]


def test_voice_to_text_continuity_shares_session(tmp_path):
    """The voice layer and the REPL are the same session: a voice follow-up
    resolves against the text task (session_id is the contract)."""
    k, client, _ = make_kernel(tmp_path, [
        "Invoice drafted.",
        "Updated for 10 AM.",
    ])
    k.run("Draft the invoice for Acme.", session_id="shared")
    r = k.run("Actually make it 10 AM.", session_id="shared")
    last_user = client.calls[-1][1][-1]["content"]
    assert "Acme" in last_user and "10 AM" in last_user
    s = AgentSession.load(tmp_path / "sessions", "shared")
    assert s is not None and "Acme" in s.active_task_text


# ================================================================ MEMORY
def _store(tmp_path):
    from bee.memory.store import StructuredMemory
    return StructuredMemory(tmp_path / "store.json")


def test_memory_conflict_supersedes_old_item(tmp_path):
    s = _store(tmp_path)
    a = s.remember("My project is called BEE.", type="fact", source="user",
                   key="project.name")
    b = s.remember("No — the project is now called BEE-PA.", type="fact",
                   source="user", key="project.name")
    assert b.id != a.id
    assert a.deleted is True and a.superseded_by == b.id
    got = s.recall("project name", k=5)
    live = [i for i in got if not i.deleted]
    assert all(i.id == b.id for i in live)
    # audit trail survives (tombstone kept)
    all_items = s.all(include_deleted=True)
    assert any(i.id == a.id and i.deleted for i in all_items)


def test_forgetting_is_respected(tmp_path):
    s = _store(tmp_path)
    s.remember("My dog's name is Rex.", type="fact", source="user",
               key="entity.dog")
    removed = s.forget(query="dog's name Rex")
    assert removed, "forget must actually delete"
    assert s.recall("dog name Rex") == []
    assert s.recall_by_key("entity.dog") is None


def test_expired_memory_excluded_and_purged(tmp_path):
    s = _store(tmp_path)
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    s.remember("This meeting was at 9.", type="event", source="user",
               key="event.old", expiry=past)
    assert s.recall("meeting 9", include_expired=False) == []
    with_exp = s.recall("meeting 9", include_expired=True)
    assert len(with_exp) == 1 and with_exp[0].expired()
    n = s.expire()
    assert n >= 1
    assert s.recall("meeting 9", include_expired=True) == []


def test_provenance_labels_and_inference_cap(tmp_path):
    s = _store(tmp_path)
    u = s.remember("I work in Kolkata.", type="fact", source="user",
                   key="fact.city", provenance="user message 2026-10-08")
    assert u.source == "user" and u.confidence >= 0.95
    i = s.remember("User probably prefers the morning.", type="fact",
                   source="model_inference", key="fact.pref",
                   provenance="inferred from 3 evening sessions")
    assert i.source == "model_inference" and i.confidence <= 0.5
    # NO silent promotion to a user fact
    with pytest.raises(PermissionError):
        s.update(i.id, source="user")
    # an explicit user re-statement is the only promotion path
    u2 = s.update(i.id, source="user", asserted_by_user=True)
    assert u2.source == "user" and u2.confidence >= 0.95


def test_semantic_add_writes_provenance(tmp_path, monkeypatch):
    from bee import paths
    from bee.kernel.memory_if import _Semantic
    monkeypatch.setattr(paths, "LONGTERM_MD", tmp_path / "longterm.md")
    if (tmp_path / "longterm.md").exists():
        (tmp_path / "longterm.md").unlink()
    _Semantic().add("Deployment window is Tuesdays.", kind="longterm",
                    source="tool", provenance="calendar scan 2026-10-08")
    txt = (tmp_path / "longterm.md").read_text(encoding="utf-8")
    assert "Deployment window is Tuesdays." in txt
    assert "source: tool" in txt
