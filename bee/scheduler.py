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


def start_scheduler(ctx, cfg) -> None:
    """Register nightly jobs with APScheduler (in-process). No-op if missing/disabled."""
    if not cfg.scheduler.enabled:
        return
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger
    except ImportError:
        log.warning("apscheduler not installed — nightly jobs disabled (pip install apscheduler)")
        return
    import threading
    s = BackgroundScheduler(timezone="Asia/Kolkata")
    try:
        s.add_job(lambda: run_nightly(ctx), CronTrigger.from_crontab(cfg.scheduler.consolidate_cron),
                  id="nightly_consolidation", replace_existing=True)
        s.add_job(lambda: rebuild_vectors(ctx), IntervalTrigger(hours=12),
                  id="vector_rebuild", replace_existing=True, max_instances=1)
        s.start()
        threading.Thread(target=lambda: log.info("scheduler started"), daemon=True).start()
    except Exception as e:
        log.warning("scheduler failed to start: %s", e)
