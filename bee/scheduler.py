"""Nightly jobs: memory consolidation (diary -> longterm), vector rebuild.

Consolidation: summarize diary entries older than KEEP_DAYS using the local
LLM, append durable bullets to memory/longterm.md, prune old diary files.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from . import paths

log = logging.getLogger("bee.sched")

KEEP_DAYS = 7


def summarize_diary(ctx, files: list[Path]) -> str:
    client = ctx.client
    blob = "\n\n".join(f"### {f.name}\n{f.read_text(encoding='utf-8', errors='ignore')[:4000]}" for f in files)
    prompt = (
        "Summarize the following diary entries into at most 8 Durable, one-line bullets "
        "(decisions, preferences, recurring tasks, user facts). No preamble, no dates.\n\n"
        f"{blob[:12000]}"
    )
    out = client.chat("local", [{"role": "user", "content": prompt}])
    return (out.get("content") or "").strip()


def consolidate(ctx, keep_days: int = KEEP_DAYS) -> dict:
    cutoff = date.today() - timedelta(days=keep_days)
    old = []
    for f in sorted(paths.DIARY_DIR.glob("*.md")):
        try:
            d = datetime.strptime(f.stem, "%Y-%m-%d").date()
        except ValueError:
            continue
        if d < cutoff:
            old.append(f)
    if not old:
        return {"pruned": 0, "added": 0}
    try:
        summary = summarize_diary(ctx, old)
    except Exception as e:
        log.warning("consolidation LLM failed: %s", e)
        return {"pruned": 0, "added": 0, "error": str(e)}
    bullets = [ln.strip().lstrip("-* ").strip() for ln in summary.splitlines() if ln.strip()]
    bullets = [b for b in bullets if b][:8]
    if bullets:
        lt = paths.LONGTERM_MD
        cur = lt.read_text(encoding="utf-8") if lt.exists() else "# Long-term memory\n"
        lt.write_text(cur.rstrip() + "\n\n" + "\n".join(f"- {b}" for b in bullets) + "\n", encoding="utf-8")
    # Archive (NOT delete): a bad summary must never destroy the originals.
    # Archived diaries stay under memory/diary/archive/ for inspection/restore.
    arch = paths.DIARY_DIR / "archive"
    moved = 0
    for f in old:
        try:
            arch.mkdir(parents=True, exist_ok=True)
            dest = arch / f.name
            n = 1
            while dest.exists():
                dest = arch / f"{f.stem}-{n}.md"
                n += 1
            f.replace(dest)  # atomic move
            moved += 1
        except Exception as e:
            log.warning("could not archive %s: %s", f, e)
    return {"pruned": moved, "added": len(bullets), "archived_to": str(arch)}


def rebuild_vectors(ctx) -> dict:
    try:
        from .memory.search import get_store
        store = get_store(ctx)
        if store in (None, False):
            return {"ok": False, "reason": "lancedb not installed"}
        n = store.rebuild()
        return {"ok": True, "chunks": n}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


def maybe_train_router(ctx) -> dict:
    """Self-learning: retrain the ML route classifier when enough new episodes exist.

    Cheap (TF-IDF + LogisticRegression, seconds, CPU-only) and only runs when
    there is genuinely new data — the stored artifact's n_train vs current rows.
    """
    cfg = ctx.cfg
    if not cfg.router.ml_enabled:
        return {"skipped": "ml router disabled"}
    try:
        from .pipeline.build_sft import load_episodes
        from .brain import mlrouter
        rows = load_episodes()
        s = mlrouter.summarize()
        if s.get("trained") and (s.get("n_train") or 0) >= len(rows):
            return {"skipped": "router already current"}
        if len(rows) < cfg.router.ml_min_episodes:
            return {"skipped": f"episodes {len(rows)} < min {cfg.router.ml_min_episodes}"}
        import contextlib
        import io
        from .pipeline import train_router
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            train_router.main(min_samples=10)  # explicit arg — no sys.argv mutation
        s2 = mlrouter.summarize()
        if s2.get("trained"):
            return {"trained": True, "n_train": s2["n_train"], "cv_acc": s2.get("cv_acc")}
        return {"trained": False, "note": buf.getvalue()[-200:]}
    except Exception as e:
        return {"error": str(e)}


def _slugify(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s[:40] or "lesson"


def maybe_teach_back(ctx) -> dict:
    """Teach-back: distill new golden cloud answers into reusable skills so the
    local model (and future cloud sessions) benefit from what the cloud solved.

    Deterministic extraction (no LLM call): a golden row qualifies for a skill
    when its response contains a code block and is substantial. Cap: 3/night.
    """
    import json
    try:
        g = paths.TRAIN_DIR / "golden" / "cloud_golden.jsonl"
        state_f = paths.TRAIN_DIR / "golden" / "digest_state.json"
        if not g.exists():
            return {"skipped": "no golden examples yet (successful cloud answers land here)"}
        rows = [json.loads(ln) for ln in g.read_text(encoding="utf-8", errors="ignore").splitlines()
                if ln.strip()]
        n_done = 0
        try:
            n_done = json.loads(state_f.read_text(encoding="utf-8")).get("n", 0)
        except Exception:
            pass
        fresh = rows[n_done:]
        made: list[str] = []
        for r in fresh[:3]:
            text = r.get("response") or ""
            if "```" not in text or len(text) < 200:
                continue
            d = paths.SKILLS_DIR / f"cloud-{_slugify(r.get('task'))}"
            if (d / "SKILL.md").exists():
                continue
            d.mkdir(parents=True, exist_ok=True)
            (d / "SKILL.md").write_text(
                f"# {_slugify(r.get('task'))}\n"
                f"description: distilled from a successful cloud answer "
                f"({r.get('model', '?')}, {r.get('ts', '?')})\n\n"
                "## Original task\n" + (r.get("task") or "")[:500] + "\n\n"
                "## Proven solution\n" + text[:6000],
                encoding="utf-8")
            # J2: distilled skills enter as CANDIDATES — version 1, hidden
            # from the prompt until the skill gate (structural + eval probe)
            # passes (nightly skill_gate job or /skillgate).
            try:
                from .evals.skillgate import bump_skill
                bump_skill(d.name, source="teach-back")
            except Exception:
                pass
            made.append(d.name)
        state_f.parent.mkdir(parents=True, exist_ok=True)
        state_f.write_text(json.dumps({"n": len(rows), "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}),
                           encoding="utf-8")
        if fresh:
            from .memory.md import diary_add
            diary_add(f"teach-back: {len(fresh)} new golden example(s); distilled skills: {made or 'none'}")
        return {"new": len(fresh), "skills": made}
    except Exception as e:
        return {"error": str(e)}


def maybe_build_sft(ctx) -> dict:
    """Rebuild train/sft_v1.jsonl from episodes + cloud goldens (cheap, file-only).

    Runs nightly so the QLoRA dataset always contains the latest responses —
    including successful cloud answers (teach-back) that the local model will
    learn from on the next training run.
    """
    try:
        from .pipeline.build_sft import build
        return build(workspace=ctx.workspace)
    except Exception as e:
        return {"error": str(e)}


def run_nightly(ctx) -> dict:
    out = {}
    out["consolidated"] = consolidate(ctx)
    out["vectors"] = rebuild_vectors(ctx)
    out["router"] = maybe_train_router(ctx)
    out["teach_back"] = maybe_teach_back(ctx)
    out["sft"] = maybe_build_sft(ctx)
    from .memory.md import diary_add
    diary_add(f"nightly job: {out}")
    log.info("nightly job done: %s", out)
    return out


# ======================================================================
# Phase 6 — durable automation (replaces the APScheduler callback model)
# ======================================================================
def _cron_time(cron: str) -> str:
    """'0 3 * * *' -> '03:00' (minute hour; fallback '03:00')."""
    try:
        parts = (cron or "").split()
        mi, hh = int(parts[0]), int(parts[1])
        return f"{hh:02d}:{mi:02d}"
    except Exception:
        return "03:00"


def _register_nightly_jobs(worker, cfg) -> None:
    """Register maintenance work as DURABLE FUNCTION JOBS (idempotent by
    stable id). This is real, persisted work — never a no-op: each job runs
    through JobWorker -> the registered function -> execution history +
    failure notification. Schedules derive from the existing scheduler
    config, so an existing setup keeps its behavior."""
    from .automation.models import PENDING, Job, JobTrigger
    tz = cfg.automation.default_timezone or "Asia/Kolkata"
    nightly = _cron_time(cfg.scheduler.consolidate_cron)

    def _plus(mins: int) -> str:
        total = int(nightly[:2]) * 60 + int(nightly[3:5]) + mins
        return f"{(total // 60) % 24:02d}:{total % 60:02d}"

    # (id, description, trigger, action, max_runtime)
    specs = [
        ("nightly_consolidate", "memory consolidation (diary -> longterm)",
         JobTrigger(kind="daily", time=nightly),
         {"type": "function", "fn": "bee.scheduler.consolidate"}, 1800.0),
        ("vector_rebuild", "vector index rebuild (12h)",
         JobTrigger(kind="interval", every_seconds=12 * 3600),
         {"type": "function", "fn": "bee.scheduler.rebuild_vectors"}, 1800.0),
        ("router_retrain", "ML router retrain (only if new episodes)",
         JobTrigger(kind="daily", time=_plus(30)),
         {"type": "function", "fn": "bee.scheduler.maybe_train_router"}, 1800.0),
        ("teach_back", "cloud teach-back (golden -> skills)",
         JobTrigger(kind="daily", time=_plus(60)),
         {"type": "function", "fn": "bee.scheduler.maybe_teach_back"}, 1800.0),
        ("sft_build", "SFT dataset rebuild",
         JobTrigger(kind="daily", time=_plus(75)),
         {"type": "function", "fn": "bee.scheduler.maybe_build_sft"}, 1800.0),
        ("log_rotation", "rotate + cap all JSONL streams (M13)",
         JobTrigger(kind="daily", time=_plus(90)),
         {"type": "function", "fn": "bee.monitor.rotate_all"}, 1800.0),
        ("alert_scan", "threshold alerts (provider/verify/disk) + toast",
         JobTrigger(kind="daily", time=_plus(105)),
         {"type": "function", "fn": "bee.monitor.alert_scan"}, 1800.0),
        ("skill_gate", "J2 skill gate: structural check + eval probe for candidate skills",
         JobTrigger(kind="daily", time=_plus(120)),
         {"type": "function", "fn": "bee.skills.gate_candidates"}, 3600.0),
        ("model_gate", "J3 model-upgrade quality gate (candidate vs eval baseline)",
         JobTrigger(kind="daily", time=_plus(150)),
         {"type": "function", "fn": "bee.evals.model_gate"}, 7200.0),
    ]
    for jid, desc, trigger, action, max_rt in specs:
        if worker.store.load_job(jid) is not None:
            continue
        job = Job(id=jid, owner="system", description=desc, action=action,
                  trigger=trigger, timezone=tz, enabled=True,
                  permissions={"guard_mode": "unattended",
                               "preapproved_capabilities": []},
                  retry_policy={"max_attempts": 2, "backoff_seconds": 300},
                  max_runtime=max_rt, state=PENDING)
        worker.create_job(job)
        log.info("registered durable job %s (%s)", jid, trigger.describe())


def start_automation(ctx, cfg, kernel=None):
    """Phase 6 entry point: durable JobWorker over <workspace>/automation.

    * jobs persist across restarts (JobStore) and are restored + re-scheduled
      at startup (worker.restore);
    * nightly maintenance becomes durable function jobs (never no-op);
    * agent_task jobs run through the SAME AgentKernel as interactive
      requests — created here if absent and stored on ctx.kernel, which the
      web /chat path then reuses (auto-deny approver: unattended);
    * proactive rules load from the store (user-authorized only).
    Returns the JobWorker, or None when automation is disabled/unavailable.
    """
    auto = cfg.automation
    if not auto.enabled:
        log.info("automation disabled by config")
        return None
    try:
        from .automation import EventBus, JobStore, JobWorker
    except Exception as e:
        log.warning("automation unavailable: %s", e)
        return None
    store = JobStore(Path(cfg.workspace) / "automation")
    if kernel is None:
        if getattr(ctx, "kernel", None) is not None:
            kernel = ctx.kernel
        else:
            from .kernel import AgentKernel
            kernel = AgentKernel(ctx, approver=lambda tool, args, reason: False)
            ctx.kernel = kernel
    worker = JobWorker(ctx, kernel, store, bus=EventBus(),
                       max_parallel=auto.max_parallel,
                       miss_grace_seconds=auto.miss_grace_seconds,
                       tick_seconds=auto.tick_seconds,
                       default_timezone=auto.default_timezone or "Asia/Kolkata")
    _register_nightly_jobs(worker, cfg)
    ctx.automation_worker = worker
    worker.start()
    log.info("automation started (store=%s, %d jobs)", store.dir, len(worker.jobs()))
    return worker


def start_scheduler(ctx, cfg) -> None:
    """Deprecated shim (pre-Phase-6 APScheduler callbacks). Kept so existing
    call sites keep working; delegates to the durable worker."""
    start_automation(ctx, cfg)
