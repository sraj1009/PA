"""Capability-based authorization tests (Phase 3, Parts A/B).

Run:  python -m pytest tests/test_capabilities.py -q
"""
from __future__ import annotations

import json

import pytest

from bee.kernel import AgentEventKind, TaskState
from bee.security.capabilities import (CAPABILITIES, CapabilityGate,
                                       CapabilityStore, Risk,
                                       capabilities_for, _Entry)


# ------------------------------------------------------------- registry
def test_registry_has_all_required_capabilities():
    required_ids = {"files.read", "files.write", "files.delete", "shell.execute",
                    "python.execute", "browser.read", "browser.interact",
                    "network.read", "system.control", "messaging.draft",
                    "messaging.send", "email.draft", "email.send", "calendar.read",
                    "calendar.write", "financial.action", "purchase",
                    "camera.access", "microphone.access"}
    have = set(CAPABILITIES)
    assert required_ids <= have, f"missing: {required_ids - have}"
    assert len(have) >= 19


def test_every_capability_has_full_metadata():
    for c in CAPABILITIES.values():
        assert c.id and c.name and c.description
        assert isinstance(c.risk, Risk)
        assert c.default_policy in {"always_allow", "ask", "task", "deny"}
        assert c.confirmation in {"none", "on_ask", "always"}


def test_dangerous_capabilities_default_off():
    for cid in ("system.control", "financial.action", "purchase", "camera.access"):
        assert CAPABILITIES[cid].default_policy == "deny", cid
    assert CAPABILITIES["purchase"].risk == Risk.R5
    assert CAPABILITIES["financial.action"].risk == Risk.R5
    assert CAPABILITIES["system.control"].risk == Risk.R4


def test_risk_levels_exist():
    assert [Risk.R0, Risk.R1, Risk.R2, Risk.R3, Risk.R4, Risk.R5] == list(Risk)


# ------------------------------------------------------ tool -> capability
def test_tool_capability_mapping():
    assert [c.id for c in capabilities_for("file_read", {})] == ["files.read"]
    assert [c.id for c in capabilities_for("file_write", {})] == ["files.write"]
    assert [c.id for c in capabilities_for("automate", {})] == ["browser.interact"]
    assert [c.id for c in capabilities_for("web_fetch", {"url": "https://x"})] == ["network.read"]
    assert [c.id for c in capabilities_for("email_send", {})] == ["email.send"]


def test_shell_escalation_delete():
    caps = {c.id for c in capabilities_for("shell", {"command": "rm reports/x.txt"})}
    assert "files.delete" in caps and "shell.execute" in caps


def test_shell_escalation_system_and_network():
    caps = {c.id for c in capabilities_for("shell", {"command": "shutdown /s /t 0"})}
    assert "system.control" in caps
    caps = {c.id for c in capabilities_for("shell", {"command": "curl https://example.com"})}
    assert "network.read" in caps


def test_code_run_delete_escalation():
    caps = {c.id for c in capabilities_for("code_run", {"code": "import shutil\nshutil.rmtree('tmp')"})}
    assert "files.delete" in caps and "python.execute" in caps


# ------------------------------------------------------------ policies
def _gate(confirmer=None, store=None):
    return CapabilityGate(store or CapabilityStore(None), confirmer=confirmer)


def test_read_never_confirms():
    asked = []
    g = _gate(confirmer=lambda c, r: (asked.append(c.id), False)[1])
    d = g.check("file_read", {"path": "a.txt"}, task_id="t")
    assert d.allowed and asked == []
    d = g.check("file_write", {"path": "a.txt", "content": "x"}, task_id="t")
    assert d.allowed and asked == []          # creating a draft/file: no confirmation


def test_delete_always_confirms_even_when_allowed():
    # policy says always_allow, but confirmation=always still fires
    store = CapabilityStore(None)
    store._entries["files.delete"] = _Entry(policy="always_allow", confirm="default")
    g = _gate(confirmer=lambda c, r: True, store=store)
    d = g.check("shell", {"command": "rm x.txt"}, task_id="t")
    assert d.allowed and d.confirmed, "ALWAYS-confirm must fire even under always_allow"


def test_delete_confirm_can_be_explicitly_disabled():
    store = CapabilityStore(None)
    store._entries["files.delete"] = _Entry(policy="always_allow", confirm="never")
    g = _gate(confirmer=lambda c, r: (_ for _ in ()).throw(AssertionError("must not ask")), store=store)
    assert g.check("shell", {"command": "rm x.txt"}, task_id="t").allowed


def test_email_send_asks_by_default():
    asked = []
    g = _gate(confirmer=lambda c, r: (asked.append(c.id), True)[1])
    d = g.check("email_send", {"to": "x@y.z"}, task_id="t")
    assert d.allowed and "email.send" in asked


def test_purchase_always_confirm_and_default_deny():
    g = _gate(confirmer=lambda c, r: True)
    d = g.check("purchase", {"item": "thing"}, task_id="t")
    assert not d.allowed and "DENY" in d.reason          # default policy is deny
    store = CapabilityStore(None)
    store._entries["purchase"] = _Entry(policy="always_allow", confirm="default")
    g2 = _gate(confirmer=lambda c, r: (False), store=store)
    d2 = g2.check("purchase", {"item": "thing"}, task_id="t")
    assert not d2.allowed and d2.confirmed is False      # even allowed, confirm is required


def test_shutdown_always_confirms():
    store = CapabilityStore(None)
    store._entries["system.control"] = _Entry(policy="always_allow", confirm="default")
    asked = []
    g = _gate(confirmer=lambda c, r: (asked.append(c.id), True)[1], store=store)
    g.check("shell", {"command": "shutdown /r /t 0"}, task_id="t")
    assert "system.control" in asked


def test_grant_is_task_scoped_never_inferred():
    g = _gate(confirmer=lambda c, r: True)
    assert g.check("shell", {"command": "rm a"}, task_id="taskA").allowed
    # same task: no re-ask (allow during current task)
    d = g.check("shell", {"command": "rm a"}, task_id="taskA")
    assert d.allowed and d.policy == "ask"
    # different task: must ask again — permission is NEVER inferred across tasks
    asked = []
    g2 = CapabilityStore(None)
    g2 = _gate(confirmer=lambda c, r: (asked.append(c.id), True)[1], store=CapabilityStore(None))
    g2.store = g.store  # same store/grants
    d = g2.check("shell", {"command": "rm b"}, task_id="taskB")
    assert d.allowed and "files.delete" in asked, "new task must re-confirm"


def test_grant_does_not_cover_other_capabilities():
    g = _gate(confirmer=lambda c, r: True)
    g.check("file_write", {"path": "x", "content": "y"}, task_id="t")   # files.write grant
    asked = []
    g3 = CapabilityGate(g.store, confirmer=lambda c, r: (asked.append(c.id), True)[1])
    g3.check("shell", {"command": "rm x"}, task_id="t")                 # needs files.delete
    assert "files.delete" in asked, "a FILES_WRITE grant must not satisfy FILES_DELETE"


def test_end_task_revokes_grants():
    g = _gate(confirmer=lambda c, r: True)
    g.check("shell", {"command": "rm a"}, task_id="t")
    g.store.end_task("t")
    asked = []
    g4 = CapabilityGate(g.store, confirmer=lambda c, r: (asked.append(c.id), False)[1])
    d = g4.check("shell", {"command": "rm a"}, task_id="t")
    assert asked == ["files.delete"] and not d.allowed


def test_task_policy_mode():
    store = CapabilityStore(None)
    store._entries["browser.interact"] = _Entry(policy="task", confirm="default")
    g = _gate(confirmer=lambda c, r: True, store=store)
    d = g.check("automate", {"action": "open"}, task_id="t1")
    assert d.allowed and store.granted_in_task("t1", "browser.interact")
    # ungranted task fails closed (confirmer would ask; with auto-deny it stays denied)
    g_deny = CapabilityGate(store, confirmer=lambda c, r: False)
    assert not g_deny.check("automate", {"action": "open"}, task_id="t2").allowed


def test_store_loads_user_config(tmp_path):
    p = tmp_path / "capabilities.yaml"
    p.write_text("email.send:\n  policy: always_allow\n  confirm: never\n", encoding="utf-8")
    store = CapabilityStore(p)
    d = CapabilityGate(store).check("email_send", {"to": "a@b.c"}, task_id="t")
    assert d.allowed and not d.confirmed
    # unknown capability ids in config are ignored, not fatal
    p.write_text("bogus.capability:\n  policy: deny\nemail.send:\n  policy: deny\n", encoding="utf-8")
    store2 = CapabilityStore(p)
    assert store2.entry("email.send").policy == "deny"


# ----------------------------------------------- kernel enforcement (pre-exec)
def test_gate_blocks_before_execution_in_kernel(tmp_path):
    from test_kernel_integration import make_kernel
    # 'del' needs files.delete (ask+always); unattended confirmer denies
    k, client, _ = make_kernel(tmp_path, [
        {"tool_calls": [{"id": "c1", "name": "shell", "arguments": {"command": "del notes.txt"}}]},
        "I could not delete that file — it was blocked by the capability policy.",
    ])
    (tmp_path / "notes.txt").write_text("keep me")
    r = k.run("Delete the file notes.txt.", session_id="g1")
    assert (tmp_path / "notes.txt").exists(), "denied tool must NOT execute"
    assert AgentEventKind.PERMISSION_DENIED in [e.kind for e in k.events.log]
    blocked = [o for o in r.task.observations if o.blocked]
    assert blocked and "capability" in blocked[0].result_text


def test_gate_confirms_then_proceeds_in_kernel(tmp_path):
    from test_kernel_integration import make_kernel
    k, client, _ = make_kernel(tmp_path, [
        {"tool_calls": [{"id": "c1", "name": "shell", "arguments": {"command": "del notes.txt"}}]},
        "Deleted notes.txt as requested.",
    ], approver=lambda tool, args, reason: True)
    (tmp_path / "notes.txt").write_text("old")
    r = k.run("Delete the file notes.txt.", session_id="g2")
    assert not (tmp_path / "notes.txt").exists(), "confirmed delete must execute"
    kinds = [e.kind for e in k.events.log]
    assert AgentEventKind.PERMISSION_REQUESTED in kinds
    assert AgentEventKind.PERMISSION_GRANTED in kinds
    rows = [json.loads(l) for l in (tmp_path / "receipts.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(row["tool"] == "capability:files.delete" and row["permission"] == "granted"
               for row in rows)


def test_guard_still_runs_after_gate(tmp_path):
    """Layering: capability gate first, then the guard's per-command layer."""
    from test_kernel_integration import make_kernel
    # capability shell.execute is allowed by default, but the guard DENIES rm -rf /tmp/x
    k, client, _ = make_kernel(tmp_path, [
        {"tool_calls": [{"id": "c1", "name": "shell", "arguments": {"command": "rm -rf /tmp/x"}}]},
        "Blocked.",
    ], approver=lambda tool, args, reason: True)
    r = k.run("Remove /tmp/x recursively.", session_id="g3")
    denied = [e for e in k.events.log if e.kind == AgentEventKind.PERMISSION_DENIED]
    assert denied
    rows = [json.loads(l) for l in (tmp_path / "receipts.jsonl").read_text(encoding="utf-8").splitlines()]
    # the guard's own deny (recursive rm) is recorded in the tool receipt
    tool_rows = [row for row in rows if row["tool"] == "shell"]
    assert tool_rows and "recursive rm" in tool_rows[0]["result"]
