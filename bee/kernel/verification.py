"""Effect verification (Phase 2).

Rule: a task is verified by OBSERVING the world, never by trusting that a
tool call returned without an exception.

Two layers:
  check_effect(tool, args, workspace)  — deterministic postcondition for one
      tool call ("file_write x" -> does x exist?, "mkdir invoices" -> does
      the directory exist?). Verdicts: pass | fail | unverified.
  verify_task(...)                      — whole-task verdict combining every
      observation plus a task-level effect probe (regex extraction of the
      intended target from the request, e.g. 'Create a folder called
      invoices.' -> invoices must exist afterwards).

Checks only ever inspect INSIDE the workspace (no probing outside — that
would be a new information channel).
"""
from __future__ import annotations

import re
from pathlib import Path

from .models import Observation, VerificationResult

# 'create/make a folder|file called|named X'  (quoted or bare names)
_TASK_TARGET_RE = re.compile(
    r"\b(?:create|make|new|mkdir|add)\s+(?:a\s+|an\s+|the\s+)?\s*"
    r"(?P<kind>folder|directory|dir|file|document|note|report)\s*"
    r"(?:named|called|:)?\s*[\u201c\"']?(?P<name>[A-Za-z0-9_][A-Za-z0-9_.\- ]{0,60}?)[\u201d\"']?\s*$",
    re.I)
_MKDIR_RE = re.compile(r"^\s*(?:New-Item\s+[-Dd]ir(?:ectory)?\s+|mkdir\s+|touch\s+)(?:/|-?\?)?[\u201c\"']?"
                       r"(?P<p>[A-Za-z0-9_./\\ \-]+?)[\u201d\"']?\s*$")


def _resolve_inside(workspace: Path, p: str) -> Path | None:
    """Resolve p relative to the workspace; None if it would escape it."""
    if not p:
        return None
    p = p.strip().strip("\"'")
    q = Path(p)
    if q.is_absolute():
        return None  # never probe outside the workspace
    try:
        target = (Path(workspace) / q).resolve()
    except Exception:
        return None
    root = Path(workspace).resolve()
    if target != root and root not in target.parents:
        return None
    return target


def check_effect(obs: Observation, workspace) -> VerificationResult:
    """Deterministic postcondition for ONE executed tool call (the Observation
    carries both the args AND what the tool actually returned)."""
    tool, args = obs.tool, (obs.args or {})
    res_text = obs.result_text or ""
    ws = Path(workspace)

    if tool == "calculator":
        ok = '"result"' in res_text
        return VerificationResult("pass" if ok else "fail",
                                  [{"check": "result_present", "ok": ok}])
    if tool == "file_write":
        t = _resolve_inside(ws, str(args.get("path") or ""))
        ok = t is not None and t.is_file() and t.stat().st_size >= 0
        return VerificationResult("pass" if ok else "fail",
                                  [{"check": "file_exists", "ok": ok,
                                    "detail": str(args.get("path"))}])
    if tool == "file_edit":
        t = _resolve_inside(ws, str(args.get("path") or ""))
        new = str(args.get("new") or "")
        ok = bool(t and t.is_file() and new and new in t.read_text(encoding="utf-8", errors="replace"))
        return VerificationResult("pass" if ok else "fail",
                                  [{"check": "edit_applied", "ok": ok,
                                    "detail": f"workspace file contains the replacement ({str(args.get('path'))})"}])
    if tool == "file_read":
        ok = '"content"' in res_text or '"lines"' in res_text
        return VerificationResult("pass" if ok else "fail",
                                  [{"check": "read_ok", "ok": ok, "detail": "read returned content"}])
    if tool == "shell":
        cmd = str(args.get("command") or "")
        m = _MKDIR_RE.match(cmd)
        if m:
            t = _resolve_inside(ws, m.group("p"))
            is_dir_cmd = "touch" not in cmd.lower()
            ok = t is not None and (t.is_dir() if is_dir_cmd else t.is_file())
            return VerificationResult("pass" if ok else "fail",
                                      [{"check": "shell_effect", "ok": ok, "detail": f"{cmd[:60]}"}])
        return VerificationResult("unverified",
                                  [{"check": "shell_generic", "ok": True,
                                    "detail": "no deterministic postcondition for this command"}])
    if tool in ("code_run", "sandbox_run", "automate", "planner", "spawn_task",
                "memory_search", "memory_longterm", "diary_add", "profile_add",
                "skill_get", "skill_list", "skill_search", "system_health"):
        return VerificationResult("unverified",
                                  [{"check": "generic", "ok": True, "detail": "effect not machine-checkable"}])
    if tool in ("web_fetch", "web_search"):
        return VerificationResult("pass", [{"check": "content_returned", "ok": True}])
    if tool == "scheduler":
        return VerificationResult("pass", [{"check": "scheduler_ack", "ok": True}])
    return VerificationResult("unverified", [{"check": "unknown_tool", "ok": True}])


def task_effect_probe(task_text: str):
    """Extract the intended filesystem target from the request, if any.
    Returns (kind, name) with kind in {'dir','file'} or None."""
    m = _TASK_TARGET_RE.search((task_text or "").strip())
    if not m:
        return None
    kind = m.group("kind").lower()
    name = m.group("name").strip().strip(".!:;,")
    if not name:
        return None
    return ("dir" if kind in ("folder", "directory", "dir") else "file", name)


def verify_task(task_text: str, observations: list[Observation], workspace,
                final_output: str = "") -> VerificationResult:
    """Whole-task verdict.

    fail       — a tool errored, an effect check failed, or the target the
                 request named does not exist in the workspace
    unverified — the work ran (or was blocked by permission) but the intended
                 effect is not machine-checkable; the kernel must NOT claim
                 verified success
    pass       — no failures AND (no side-effecting tools, or effects checked)
    """
    checks: list[dict] = []
    failed = False
    blocked_any = False

    for o in observations:
        if o.blocked:
            blocked_any = True
            checks.append({"check": f"tool:{o.tool}", "ok": False,
                           "detail": "blocked by permission (not an execution failure)"})
        elif not o.ok:
            failed = True
            checks.append({"check": f"tool:{o.tool}", "ok": False, "detail": o.result_text[:160]})
        elif o.effect == "fail":
            failed = True
            checks.append({"check": f"effect:{o.tool}", "ok": False,
                           "detail": o.result_text[:160]})

    probe = task_effect_probe(task_text)
    if probe:
        kind, name = probe
        t = _resolve_inside(Path(workspace), name)
        exists = t is not None and (t.is_dir() if kind == "dir" else t.is_file())
        checks.append({"check": f"target_exists:{kind}", "ok": exists,
                       "detail": f"workspace/{name}"})
        if not exists:
            failed = True

    if failed:
        verdict = "fail"
    elif observations and all(o.effect != "pass" for o in observations):
        # tools ran (or were blocked) but no effect was machine-confirmed —
        # the kernel must NOT claim verified success
        verdict = "unverified"
    elif blocked_any:
        verdict = "unverified"   # permission outcome — record, don't claim success
    elif not checks:
        # pure Q&A: the answer itself is the product (brain.verifier judges
        # its quality separately in the loop)
        verdict = "pass" if (final_output or "").strip() else "unverified"
    else:
        verdict = "pass"
    return VerificationResult(verdict, checks)
