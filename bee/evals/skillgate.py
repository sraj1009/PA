"""J2 — skill versioning + eval gate.

A skill (skills/<name>/SKILL.md [+ script.py]) is only ADDED to the agent's
system prompt once it has passed the gate. Lifecycle:

    skill_create / teach-back  ->  version bumped, status = "candidate"
    candidate                   ->  hidden from the prompt (not indexed)
    gate (nightly job + /skillgate)  ->
        structural check  (content complete, script.py compiles)
        + eval probe      (structural eval tasks re-run WITH the skill in the
                           prompt; any task that passed before must not fail)
        pass -> status = "active"  (indexed, shipped)
        fail -> stays "candidate", failure recorded in meta.json (agent/user
                can fix and re-bump; the next gate pass retries)

Metadata lives at skills/<name>/meta.json:
    {name, version, status, source, created, updated,
     eval: {checked, passed, reason, score}, history: [{version, ts, status}]}

Legacy skills (no meta.json) are treated as active/v1 — existing libraries
keep working untouched.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import time
from datetime import datetime
from pathlib import Path

from .. import paths

MAX_HISTORY = 20
PROBE_MAX_TASKS = 8          # bounded: at most this many structural eval tasks
SCRIPT_COMPILE_TIMEOUT = 30  # seconds; not used (compile is near-instant) — kept as contract


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _slugify(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", str(s or "").strip()) or "skill"


def meta_path(name: str) -> Path:
    return paths.SKILLS_DIR / _slugify(name) / "meta.json"


def skill_dir(name: str) -> Path:
    return paths.SKILLS_DIR / _slugify(name)


# ----------------------------------------------------------------- metadata
def read_meta(name: str) -> dict:
    """Meta with defaults. A skill WITHOUT meta.json is legacy-active/v1."""
    meta = {"name": _slugify(name), "version": 1, "status": "active",
            "source": "legacy", "created": "", "updated": "",
            "eval": {}, "history": []}
    p = meta_path(name)
    if p.exists():
        try:
            stored = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(stored, dict):
                for k, v in stored.items():
                    meta[k] = v
        except Exception:
            pass
    meta.setdefault("history", [])
    meta.setdefault("eval", {})
    return meta


def write_meta(name: str, meta: dict) -> None:
    d = skill_dir(name)
    d.mkdir(parents=True, exist_ok=True)
    meta["updated"] = _now()
    meta["history"] = (meta.get("history") or [])[-MAX_HISTORY:]
    fd, tmp = tempfile.mkstemp(dir=str(d), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=1, ensure_ascii=False)
        os.replace(tmp, meta_path(name))
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass


def bump_skill(name: str, source: str = "agent") -> dict:
    """Create/bump a skill's version and mark it CANDIDATE (hidden until it
    passes the gate). Called by skill_create and the teach-back distiller."""
    meta = read_meta(name)
    is_new = not meta_path(name).exists()
    meta["version"] = 1 if is_new else int(meta.get("version", 1)) + 1
    meta["status"] = "candidate"
    meta["source"] = source
    if is_new:
        meta["created"] = _now()
    meta["history"] = (meta.get("history") or []) + [
        {"version": meta["version"], "ts": _now(), "status": "candidate"}]
    write_meta(name, meta)
    return meta


# ------------------------------------------------------------- structural
def structural_check(name: str) -> tuple[bool, str]:
    """Deterministic content gate — no LLM. A skill ships only if it is
    actually complete and any shipped script at least compiles."""
    d = skill_dir(name)
    md = d / "SKILL.md"
    if not md.exists():
        return False, "SKILL.md missing"
    try:
        body = md.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return False, f"SKILL.md unreadable: {e}"
    if len(body.strip()) < 40:
        return False, "SKILL.md too short to be usable (<40 chars)"
    if not re.search(r"(?im)^\s*description\s*:", body):
        return False, "SKILL.md missing 'description:' line"
    if "##" not in body:
        return False, "SKILL.md missing sections (## How / ## Gotchas)"
    script = d / "script.py"
    if script.exists():
        try:
            src = script.read_text(encoding="utf-8", errors="ignore")
            compile(src, str(script), "exec")
        except SyntaxError as e:
            return False, f"script.py does not compile (line {e.lineno}: {e.msg})"
        except Exception as e:
            return False, f"script.py unreadable: {e}"
    return True, "ok"


# --------------------------------------------------------------- eval probe
def _latest_per_task() -> dict[str, bool]:
    """Latest recorded outcome per eval task id (the pre-probe baseline)."""
    from .. import paths as _p
    latest: dict[str, bool] = {}
    f = _p.EVAL_RESULTS
    if not f.exists():
        return latest
    for ln in f.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not ln.strip():
            continue
        try:
            row = json.loads(ln)
        except Exception:
            continue
        tid = row.get("id")
        if tid and not row.get("skipped"):
            latest[tid] = bool(row.get("ok"))
    return latest


def eval_probe(ctx, name: str, max_tasks: int = PROBE_MAX_TASKS) -> dict:
    """Re-run a bounded subset of STRUCTURAL eval tasks with the skill
    force-included in the prompt; pass = no task that passed before now fails.

    Bounded by design: at most `max_tasks` tasks, each on the agent's normal
    (max_iters-capped) path. The probe's rows also become the fresh results
    for those tasks in evals/results.jsonl — honest, current data."""
    from .gate import structural_task_ids
    from . import runner
    ids = structural_task_ids()[:max_tasks]
    if not ids:
        return {"ok": True, "note": "no structural tasks defined — probe skipped", "fail": []}
    before = {tid: v for tid, v in _latest_per_task().items() if tid in ids and v}
    old_force = getattr(ctx, "force_skills", None)
    try:
        ctx.force_skills = set(getattr(ctx, "force_skills", None) or set()) | {name}
        rows = runner.run_suite(ctx, only=ids)
    finally:
        if old_force is None:
            try:
                delattr(ctx, "force_skills")
            except AttributeError:
                pass
        else:
            ctx.force_skills = old_force
    after = {r["id"]: bool(r.get("ok")) and not r.get("skipped") for r in rows if not r.get("skipped")}
    failed = sorted(tid for tid, ok in after.items() if before.get(tid) and not ok)
    passed_now = sum(1 for v in after.values() if v)
    return {"ok": not failed, "fail": failed,
            "score": f"{passed_now}/{len(after)}", "baseline_passed": sorted(before)}


# ------------------------------------------------------------------ gating
def gate_skill(ctx, name: str) -> dict:
    """Run the full gate for one skill. Mutates meta.json."""
    meta = read_meta(name)
    if meta.get("status") == "active":
        # already shipped and unchanged — re-check is cheap (structural only)
        ok, why = structural_check(name)
        meta["eval"] = {"checked": _now(), "passed": ok, "reason": why,
                        "score": meta.get("eval", {}).get("score", "")}
        write_meta(name, meta)
        return {"name": name, "ok": ok, "status": "active", "reason": why}
    # candidate (or newly created) path: full gate
    ok, why = structural_check(name)
    probe: dict = {"ok": True, "fail": []}
    if ok:
        probe = eval_probe(ctx, name)
    passed = ok and bool(probe.get("ok"))
    meta["eval"] = {"checked": _now(), "passed": passed,
                    "reason": "" if passed else (why if not ok else "eval regression: " + ", ".join(probe["fail"])),
                    "score": probe.get("score", "")}
    if passed:
        meta["status"] = "active"
        meta["history"] = (meta.get("history") or []) + [
            {"version": meta.get("version"), "ts": _now(), "status": "active"}]
        write_meta(name, meta)
        return {"name": name, "ok": True, "status": "active",
                "version": meta.get("version"), "score": probe.get("score", "")}
    write_meta(name, meta)
    return {"name": name, "ok": False, "status": "candidate", "version": meta.get("version"),
            "reason": meta["eval"]["reason"]}


def candidate_names() -> list[str]:
    out = []
    for md in sorted(paths.SKILLS_DIR.glob("*/SKILL.md")):
        try:
            if read_meta(md.parent.name).get("status") == "candidate":
                out.append(md.parent.name)
        except Exception:
            continue
    return out


def gate_candidates(ctx, limit: int = 5) -> dict:
    """Nightly job body: gate every candidate skill (bounded per run)."""
    names = candidate_names()[:limit]
    if not names:
        return {"gated": 0, "note": "no candidate skills"}
    results = []
    for n in names:
        try:
            results.append(gate_skill(ctx, n))
        except Exception as e:
            results.append({"name": n, "ok": False, "status": "candidate",
                            "reason": f"{type(e).__name__}: {e}"})
    promoted = [r["name"] for r in results if r.get("ok")]
    rejected = [r["name"] for r in results if not r.get("ok")]
    try:
        from ..memory.md import diary_add
        diary_add(f"skill gate: promoted {promoted or 'none'}; "
                  f"kept as candidate {rejected or 'none'}")
    except Exception:
        pass
    return {"gated": len(names), "promoted": promoted, "rejected": rejected,
            "results": results}
