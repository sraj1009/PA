"""Self-directed practice (P1-6) — the job that generates its own tasks.

Mines the freshest lesson-shaped failures (eval ids whose latest run failed,
recent failed episodes), asks the local model for sibling tasks in the same
family, attempts them through the SAME agent loop users use (so routing,
guard and verification behave identically), and keeps verifier-clean
trajectories: every attempt lands as an episode row tagged `practice`, which
the nightly SFT build reports separately from user rows.

Fences, deliberately:
  * local model only (`model="local"`, the explicit local engine) — the model
    never escalates to cloud, and web-shaped sources/tasks are filtered (a
    read-only web tool call remains possible if a task invites it);
  * idle only: defers when a non-practice episode ended in the last
    IDLE_MINUTES, stops early if the user comes back mid-run, and defers
    while a present NVIDIA GPU reports > GPU_UTIL_MAX utilization
    (nvidia-smi absent/unparsable -> not busy; the activity rule is the
    primary guard);
  * `guard_mode="unattended"` — guard `ask` actions are DENIED in a practice
    run, never queued for a human who is asleep;
  * memory-write-shaped and system-state-shaped tasks are dropped before
    they can run: a practice task must not edit the user's memory
    (provenance fencing is P1-7; this is the cheap fence until then);
  * bounded: MAX_SOURCES sources, MAX_VARIATIONS per source, MAX_ATTEMPTS
    total, and a wall-clock budget.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import replace

from . import paths
from .agent.loop import run_agent
from .monitor import metrics

log = logging.getLogger("bee.practice")

EVENT = "practice"
MAX_SOURCES = 2
MAX_VARIATIONS = 3
MAX_ATTEMPTS = 6
TIME_BUDGET_S = 1200          # 20 min wall clock
IDLE_MINUTES = 20             # user-quiet window required to start / continue
GPU_UTIL_MAX = 25             # % — defer above this when nvidia-smi answers
_TASK_MIN, _TASK_MAX = 8, 300

# High-precision blocks, three families: (a) memory writes (provenance fence
# until P1-7), (b) destructive/system command SHAPES — the guard's ask-class,
# so a practice task never rehearses `git reset --hard` or a service kill, and
# (c) cloud/network shapes, matching the local-only contract. DSA tasks
# legitimately contain words like "remove" or "delete a node" — this matches
# command shapes, not verbs; the unattended guard stays the real fence.
_UNSAFE = re.compile(
    r"(remember|forget)\b|(my|the user's)\s+(api|token|password|credential)"
    r"|\b(registry|reg\s+(add|delete)|shutdown|reboot|bcdedit|schtasks|"
    r"net\s+user|taskkill|pip\s+uninstall)\b"
    r"|\brm\s+-rf\b|\bgit\s+(reset|clean|push)\b|\bformat\s+[a-z]:|"
    r"\b(drop|truncate)\s+table\b|\bdocker\s+(prune|volume\s+rm)\b|"
    r"\bsystemctl\s+(stop|disable)\b|\bchmod\s+(-r\s+)?777\b|\bcloud\b",
    re.I,
)

# Desktop/web shapes are off-family for unattended practice: not
# self-verifiable, and desktop control must stay supervised (P1-7).
_OFF_FAMILY = re.compile(
    r"\b(chrome|firefox|browser|desktop|screenshot|click|scroll|website)\b"
    r"|\bexample\.(com|org)\b|\bsearch the (web|internet)\b",
    re.I,
)
# Deterministically gradable families (see pipeline.validate): episode
# mining keeps only these — math, file, shell, code.
_PRACTICE_TYPES = {"math", "file", "shell", "code"}
_JSON_ARRAY = re.compile(r"\[.*\]", re.S)
_BULLET = re.compile(r"^\s*(?:[-*\u2022]|\d+[.)])\s*")


def _recent_episode_rows(limit: int = 60) -> list[dict]:
    """Newest-first episode rows across the two newest day files (a 03:xx run
    needs yesterday's file for late-evening activity)."""
    out: list[dict] = []
    files = sorted(paths.EPISODES_DIR.glob("*.jsonl"), reverse=True)[:2]
    for f in files:
        try:
            lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for ln in reversed(lines[-400:]):
            if not ln.strip():
                continue
            try:
                out.append(json.loads(ln))
            except Exception:
                continue
            if len(out) >= limit:
                return out
    return out


def _user_active(minutes: int = IDLE_MINUTES) -> float | None:
    """Seconds since the last NON-practice episode ended, or None when there
    is no evidence either way (fresh install counts as idle)."""
    now = time.time()
    for r in _recent_episode_rows():
        if r.get("tag") == "practice":
            continue
        try:
            ended = float(r.get("ts", 0)) + float(r.get("seconds", 0))
        except (TypeError, ValueError):
            continue
        return max(0.0, now - ended)
    return None


def _gpu_busy(util_max: int = GPU_UTIL_MAX) -> bool:
    """True when a present NVIDIA GPU reports utilization above the cap.
    No nvidia-smi (or unparsable output) -> False: the activity rule above is
    the guard of record; this is an extra courtesy where it can answer."""
    import shutil
    import subprocess
    exe = shutil.which("nvidia-smi")
    if not exe:
        return False
    try:
        r = subprocess.run(
            [exe, "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5)
        nums = [int(x.strip()) for x in (r.stdout or "").splitlines()
                if x.strip().isdigit()]
        return bool(nums) and max(nums) > util_max
    except Exception:
        return False


def _failing_eval_tasks(cap: int = MAX_SOURCES) -> list[str]:
    """Task text of eval ids whose LATEST row in results.jsonl says ok=false."""
    p = paths.EVALS_DIR / "results.jsonl"
    try:
        lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []
    latest: dict[str, dict] = {}
    for ln in lines:
        try:
            row = json.loads(ln)
        except Exception:
            continue
        tid = row.get("id")
        if tid and row.get("ts", "") >= latest.get(tid, {}).get("ts", ""):
            latest[tid] = row
    failed = [tid for tid, r in latest.items() if r.get("ok") is False]
    if not failed:
        return []
    tasks: dict[str, str] = {}
    try:
        from .evals.runner import load_tasks
        for t in load_tasks() or []:
            tasks[str(t.get("id"))] = str(t.get("task") or t.get("prompt") or "")
    except Exception as e:
        log.info("could not read eval tasks for practice sources: %s", e)
    out = [tasks[tid] for tid in failed
           if tasks.get(tid) and not _UNSAFE.search(tasks[tid])
           and not _OFF_FAMILY.search(tasks[tid])]
    return out[:cap]


def _failed_episode_tasks(cap: int = MAX_SOURCES, scan: int = 200) -> list[str]:
    """Recent failed episode tasks, newest first, deduped — kept to the
    families a cheap deterministic check can grade (math/file/shell/code) and
    filtered through the same wrong-shape rules as generated tasks. A failed
    desktop or web episode is not practice material: unattended practice must
    be self-verifiable and side-effect-free."""
    from .pipeline.build_sft import load_episodes
    from .pipeline.validate import detect_type
    seen: set[str] = set()
    out: list[str] = []
    for r in reversed(load_episodes()[-scan:]):
        if r.get("ok", False):
            continue
        t = str(r.get("task") or "").strip()
        if not t or t in seen:
            continue
        if _UNSAFE.search(t) or _OFF_FAMILY.search(t):
            continue
        if detect_type(t, r.get("events") or []) not in _PRACTICE_TYPES:
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= cap:
            break
    return out


_VARIATION_PROMPT = (
    "You are preparing self-directed practice for a local assistant. Below are "
    "tasks that recently failed a check. Write up to {k} NEW tasks in the SAME "
    "family and difficulty — same kind of work, different specifics — one per "
    "line, as a JSON array of strings. Requirements: self-contained, a single "
    "clear request, under 200 characters, independently verifiable (math, "
    "algorithms, code, file work). Never destructive or system commands, "
    "cloud/network use, or anything about the user's memory, notes, profile "
    "or credentials. Return ONLY the JSON array.\n\n"
    "Failed tasks:\n{sources}"
)


def _clean(items, k: int) -> list[str]:
    """Whitespace-normalise, dedupe, and keep only usable practice tasks."""
    out: list[str] = []
    seen: set[str] = set()
    for s in items:
        s = " ".join(str(s).split())
        if not (_TASK_MIN <= len(s) <= _TASK_MAX):
            continue
        if s.lower().startswith("cloud:"):
            continue
        if _UNSAFE.search(s) or _OFF_FAMILY.search(s):
            continue
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= k:
            break
    return out


def _parse_variations(text: str, k: int) -> list[str]:
    """JSON array when present and usable, bullet/numbered lines as fallback.
    A bracketed snippet inside prose (e.g. a list literal in a task) must not
    masquerade as the JSON reply — if the extraction yields no usable task,
    the lines win."""
    text = text or ""
    items: list[str] = []
    m = _JSON_ARRAY.search(text)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, list) and any(isinstance(x, str) for x in data):
                items = [str(x) for x in data]
        except Exception:
            items = []
    out = _clean(items, k)
    if out:
        return out
    lines: list[str] = []
    for ln in text.splitlines():
        s = ln.strip()
        while True:
            s2 = _BULLET.sub("", s).strip()
            if s2 == s:
                break
            s = s2
        s = s.strip('"').strip(",").strip()
        if s:
            lines.append(s)
    return _clean(lines, k)


def _variations(ctx, sources: list[str], k: int = MAX_VARIATIONS) -> list[str]:
    prompt = _VARIATION_PROMPT.format(
        k=k, sources="\n".join(f"- {s[:300]}" for s in sources[:MAX_SOURCES]))
    try:
        out = ctx.client.chat("local", [{"role": "user", "content": prompt}])
        text = (out.get("content") or "") if isinstance(out, dict) else str(out or "")
    except Exception as e:
        log.warning("practice variation call failed: %s", e)
        return []
    return _parse_variations(text, k)


def run(ctx) -> dict:
    """Durable-job entry (registered as `practice` in bee.scheduler)."""
    started = time.time()
    out = {"sources": 0, "variations": 0, "attempts": 0, "ok": 0, "clean": 0,
           "skipped": ""}
    age = _user_active()
    if age is not None and age < IDLE_MINUTES * 60:
        out["skipped"] = f"user active {int(age)}s ago"
        metrics.record(EVENT, **out)
        return out
    if _gpu_busy():
        out["skipped"] = "gpu busy"
        metrics.record(EVENT, **out)
        return out

    if getattr(ctx, "client", None) is None:
        # The durable job's ctx may be cold (no interactive run yet today);
        # run_agent would build the client later, but the variation call needs
        # it first. Same construction run_agent uses.
        try:
            from .agent.client import LLMClient
            ctx.client = LLMClient(ctx.cfg)
        except Exception as e:
            out["skipped"] = f"no client ({type(e).__name__})"
            metrics.record(EVENT, **out)
            return out

    # The same wrong-shape filter applies to SOURCES: a failed destructive
    # request would only generate destructive siblings.
    sources = [s for s in (_failing_eval_tasks() + _failed_episode_tasks())
               if s and not _UNSAFE.search(s)][:MAX_SOURCES]
    out["sources"] = len(sources)
    if not sources:
        out["skipped"] = "no failures to practice"
        metrics.record(EVENT, **out)
        return out
    tasks = _variations(ctx, sources)
    out["variations"] = len(tasks)
    if not tasks:
        out["skipped"] = "no usable variations"
        metrics.record(EVENT, **out)
        return out

    pctx = replace(ctx, practice=True, guard_mode="unattended")
    for task in tasks[:MAX_ATTEMPTS]:
        if time.time() - started > TIME_BUDGET_S:
            out["skipped"] = "time budget"
            break
        again = _user_active()
        if again is not None and again < IDLE_MINUTES * 60:
            out["skipped"] = "user returned mid-run"
            break
        try:
            res = run_agent(pctx, task, model="local")
        except Exception as e:
            log.warning("practice attempt failed to run: %s", e)
            continue
        out["attempts"] += 1
        if getattr(res, "ok", False):
            out["ok"] += 1
        if (getattr(res, "verify", "") or "") != "fail":
            out["clean"] += 1
    out["seconds"] = round(time.time() - started, 1)
    metrics.record(EVENT, **out)
    log.info("practice done: %s", out)
    return out
