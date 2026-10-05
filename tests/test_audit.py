"""Audit trail: redaction on write, JSONL shape, best-effort safety."""
from __future__ import annotations

import json

from bee.security import audit
from bee.security.risk import RiskLevel, RiskDecision


FAKE_KEY = "sk-abcdefghijklmnop1234"  # synthetic fixture (matches privacy.api_key)


def test_record_writes_redacted_row(tmp_path):
    p = tmp_path / "audit.jsonl"
    d = RiskDecision(level=RiskLevel.MEDIUM, action="allow", reason="",
                     capabilities=frozenset({"exec"}))
    audit.record(tool="shell", args={"command": f"echo key={FAKE_KEY}"},
                 decision=d, action="allow", ok=True, seconds=0.4, path=p)
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    r = rows[0]
    assert r["tool"] == "shell" and r["action"] == "allow" and r["ok"] is True
    assert r["risk"]["level"] == "MEDIUM" and r["risk"]["capabilities"] == ["exec"]
    # the secret must be redacted in the persisted args
    assert FAKE_KEY not in r["args"]
    assert "[REDACTED:API_KEY]" in r["args"]
    assert "echo key=" in r["args"]


def test_record_denial_with_reason_redacted(tmp_path):
    p = tmp_path / "audit.jsonl"
    d = RiskDecision(level=RiskLevel.CRITICAL, action="deny",
                     reason=f"python: leaked {FAKE_KEY}", capabilities=frozenset())
    audit.record(tool="code_run", args={"code": "x"}, decision=d, action="deny",
                 ok=False, blocked=True, path=p)
    r = json.loads(p.read_text(encoding="utf-8"))
    assert r["action"] == "deny" and r["blocked"] is True
    assert FAKE_KEY not in json.dumps(r)
    assert "[REDACTED:API_KEY]" in r["risk"]["reason"]


def test_record_never_raises(tmp_path):
    p = tmp_path / "audit.jsonl"
    audit.record(tool="x", args={"a": object()}, decision=None, action="allow", path=p)
    audit.record(tool="x", args=None, decision=None, action="allow", path=p)
    rows = p.read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 2


def test_recent_returns_rows(tmp_path):
    p = tmp_path / "audit.jsonl"
    for i in range(3):
        audit.record(tool=f"t{i}", args={}, decision=None, action="allow", path=p)
    # recent() reads the default path; point it via monkeypatch of audit_path
    import bee.security.audit as A
    orig = A.audit_path
    A.audit_path = lambda: p
    try:
        rows = A.recent(2)
    finally:
        A.audit_path = orig
    assert [r["tool"] for r in rows] == ["t1", "t2"]
