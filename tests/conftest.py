"""Test pyramid markers (audit 2026-10-06).

The suite is one directory, but the TESTS themselves are layered. Markers are
assigned automatically by filename here (no per-file edits needed) so the
pyramid can be addressed with:

    python -m pytest tests -q -m unit          # fast, no I/O beyond tmp
    python -m pytest tests -q -m security      # guard/risk/capability/privacy/netguard/auth
    python -m pytest tests -q -m "voice or scheduler"
    python -m pytest tests -q -m e2e           # full agent loops / web TestClient

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

MARKERS = {
    "unit": [
        "test_kernel_unit", "test_guard", "test_risk", "test_privacy",
        "test_netguard", "test_fastpaths", "test_verifier", "test_mlrouter",
        "test_router_tiers", "test_secretscan", "test_dsa", "test_extractor",
        "test_capabilities", "test_offline", "test_audit",
    ],
    "integration": [
        "test_kernel_integration", "test_automation", "test_episodes",
        "test_pipeline", "test_rag", "test_sandbox", "test_livekit",
        "test_engine_speed", "test_engines_session", "test_webauth",
        "test_structured_memory", "test_sft",
    ],
    "security": [
        "test_guard", "test_risk", "test_capabilities", "test_privacy",
        "test_netguard", "test_secretscan", "test_webauth", "test_sandbox",
        "test_audit",
    ],
    "agent": [
        "test_kernel_integration", "test_kernel_unit", "test_jarvis_features",
        "test_commands", "test_automation", "test_fastpaths",
        "test_router_tiers", "test_mlrouter",
    ],
    "tools": [
        "test_automate", "test_automation", "test_extractor", "test_sandbox",
    ],
    "voice": [
        "test_voice_engine", "test_stt_device", "test_livekit",
    ],
    "scheduler": [
        "test_automation", "test_pipeline",
    ],
    "e2e": [
        "test_kernel_integration", "test_engine_speed", "test_webauth",
        "test_jarvis_features", "test_automation",
    ],
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
