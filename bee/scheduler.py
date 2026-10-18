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
    written = {"added": 0, "updated": 0, "duplicates": 0}
    if bullets:
        # Through add_facts, not a raw append: the raw append re-piled the same
        # summary facts on every nightly run (no dedupe/update, no self-talk
        # filter) and never marked the file dirty, so fresh facts stayed
        # invisible to vector recall until the 12 h rebuild.
        from .memory import md
        written = md.add_facts(paths.LONGTERM_MD, "\n".join(bullets))
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
    return {"pruned": moved, "added": written.get("added", 0),
            "updated": written.get("updated", 0),
            "duplicates": written.get("duplicates", 0), "archived_to": str(arch)}


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


def flush_memory_index(ctx) -> dict:
    """Index whatever memory changed since the last flush.

    The full rebuild runs every 12 h, which meant a fact the user stated minutes
    ago was not findable semantically for the rest of the day. This is the cheap
    incremental path: it embeds only the files marked dirty and keeps the queue on
    disk, so an unreachable embedder retries rather than loses the work."""
    try:
        from .memory.search import flush_dirty
        return flush_dirty(ctx)
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

    keep_unknown=True with a quality floor: strict pass-only starves the
    dataset (157 pass of 1360 episodes — never trainable), while unknown is
    'no cheap check', not 'wrong'. The quality heuristic + bad-event dropping
    + PII scrub in build() are the honesty levers; fail is still never trained.
    """
    try:
        from .pipeline.build_sft import build
        return build(workspace=ctx.workspace, keep_unknown=True, min_quality=0.6)
    except Exception as e:
        return {"error": str(e)}


def _auto_chain(ctx, adapter_dir: Path, logf: Path) -> dict:
    """P0-5: merge -> GGUF -> `ollama create` -> queue for the J3 gate.

    Runs right after a successful nightly training (the operator already opted
    into the GPU burn). Each step is reported; a missing llama.cpp or a failed
    import never loses the adapter — the chain stops with a note and the next
    successful training supersedes it. Only a FULLY IMPORTED model is queued
    (train/gate_candidate.json), so the J3 gate can never score a half-built
    artifact.
    """
    import shutil as _sh
    import subprocess as _sp
    import sys as _sys

    t = getattr(ctx.cfg, "training", None)
    tag = adapter_dir.name.replace("bee-qlora-", "") or adapter_dir.name
    merged = paths.PROJECT_ROOT / "models" / f"bee-merged-{tag}"
    model_name = f"bee-qlora-{tag}"
    try:
        logf.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    def run_step(cmd, cwd=None, timeout=3600.0) -> bool:
        with logf.open("a", encoding="utf-8") as lf:
            lf.write("\n$ " + " ".join(str(c) for c in cmd) + "\n")
            lf.flush()
            r = _sp.run([str(c) for c in cmd], cwd=(str(cwd) if cwd else None),
                        stdout=lf, stderr=_sp.STDOUT, timeout=timeout)
        return getattr(r, "returncode", 1) == 0

    # 1. merge the adapter into the base (torch step; skipped when re-run)
    cmd = [_sys.executable, str(paths.PROJECT_ROOT / "training" / "qlora" / "merge_export.py"),
           "--adapter", str(adapter_dir), "--out", str(merged)]
    if (merged / "model.safetensors").exists():
        cmd.append("--skip-merge")
    try:
        if not run_step(cmd, timeout=7200.0):
            return {"merged": str(merged), "error": "merge_export.py exited nonzero"}
    except Exception as e:
        return {"merged": str(merged), "error": f"merge failed: {e}"}
    modelfile = merged / "Modelfile"
    if not modelfile.exists():
        return {"merged": str(merged), "error": "merge_export.py produced no Modelfile"}

    # 2. convert + quantize + import, when an unpacked llama.cpp is configured
    lc_arg = str(getattr(t, "llama_cpp_dir", "") or "").strip() if t else ""
    lc = Path(lc_arg) if lc_arg else None
    convert = lc / "convert_hf_to_gguf.py" if lc else None
    if not lc or not convert.exists():
        return {"merged": str(merged),
                "note": "merge done; set training.llama_cpp_dir (unpacked llama.cpp: "
                        "convert_hf_to_gguf.py + llama-quantize*.exe) to import + queue"}
    f16 = merged / "bee4b-f16.gguf"
    q4 = merged / "bee4b-q4_k_m.gguf"
    try:
        if not run_step([_sys.executable, str(convert), str(merged),
                         "--outfile", str(f16), "--outtype", "f16"], cwd=lc, timeout=7200.0):
            return {"merged": str(merged), "error": "convert_hf_to_gguf.py exited nonzero"}
        qexe = next(iter(sorted(lc.glob("llama-quantize*.exe"))), None) \
            or _sh.which("llama-quantize")
        if not qexe:
            return {"merged": str(merged), "f16": str(f16),
                    "note": "converted to f16; no llama-quantize*.exe in "
                            "training.llama_cpp_dir (nor PATH) — quantize + import by hand"}
        if not run_step([str(qexe), str(f16), str(q4), "Q4_K_M"], cwd=lc, timeout=3600.0):
            return {"merged": str(merged), "error": "llama-quantize exited nonzero"}
        oll = _sh.which("ollama") or "ollama"
        if not run_step([oll, "create", model_name, "-f", str(modelfile)], timeout=3600.0):
            return {"merged": str(merged), "gguf": str(q4),
                    "error": "ollama create exited nonzero"}
    except Exception as e:
        return {"merged": str(merged), "error": f"export chain failed: {e}"}

    # 3. queue for the J3 gate
    try:
        from .evals.gate import queue_candidate
        queue_candidate(model_name, src="auto-chain",
                        adapter=str(adapter_dir), merged=str(merged))
    except Exception as e:
        return {"merged": str(merged), "model": model_name,
                "error": f"model imported but queue write failed: {e}"}
    return {"merged": str(merged), "gguf": str(q4), "model": model_name, "queued": True}


def maybe_train_qlora(ctx) -> dict:
    """Nightly QLoRA refresh trigger (GPU-gated, bounded, stateful).

    Runs train/sft_v1.jsonl through training/qlora/train.py when ALL hold:
      training.auto_qlora is true (operator opt-in — a multi-hour GPU burn
        must never start by surprise on a daily-driver machine),
      CUDA torch + the HF stack import (else: report why, skip),
      samples >= training.min_samples,
      no adapter trained in the last training.min_interval_days.
    Bounded by the --fast preset + --max-samples so one night cannot run away.
    P0-5 auto-chain: a successful run is merged (merge_export.py), GGUF-
    converted + Q4_K_M-quantized + `ollama create`d when training.llama_cpp_dir
    points at an unpacked llama.cpp, and the finished model is queued for the
    J3 gate (train/gate_candidate.json). Promotion still only happens when the
    gate adopts it on an eval win.
    """
    import sys as _sys
    cfg = ctx.cfg
    t = getattr(cfg, "training", None)
    if t is None or not getattr(t, "auto_qlora", False):
        return {"skipped": "training.auto_qlora=false (opt-in; no surprise GPU burn)"}
    try:
        import torch
        cuda = bool(getattr(torch, "cuda", None) and torch.cuda.is_available())
    except Exception:
        cuda = False
    if not cuda:
        return {"skipped": "no CUDA torch (train needs the cu124 stack)"}
    for mod in ("transformers", "peft", "datasets", "bitsandbytes"):
        try:
            __import__(mod)
        except Exception:
            return {"skipped": f"missing HF stack module: {mod} (training/requirements.txt)"}
    import json as _json
    data = paths.TRAIN_DIR / "sft_v1.jsonl"
    try:
        n = sum(1 for ln in data.read_text(encoding="utf-8").splitlines() if ln.strip())
    except Exception:
        n = 0
    min_n = int(getattr(t, "min_samples", 150) or 150)
    if n < min_n:
        return {"skipped": f"only {n} samples (< min_samples {min_n})"}
    state_f = paths.TRAIN_DIR / "qlora_state.json"
    try:
        state = _json.loads(state_f.read_text(encoding="utf-8")) if state_f.exists() else {}
    except Exception:
        state = {}
    interval = float(getattr(t, "min_interval_days", 7) or 7) * 86400.0
    if time.time() - float(state.get("last_train_ts", 0) or 0) < interval:
        return {"skipped": "adapter trained within min_interval_days"}
    import datetime as _dt
    import subprocess as _sp
    tag = _dt.datetime.now().strftime("%Y%m%d")
    out = paths.PROJECT_ROOT / "models" / f"bee-qlora-{tag}"
    logf = paths.TRAIN_DIR / f"qlora_{tag}.log"
    cmd = [_sys.executable, str(paths.PROJECT_ROOT / "training" / "qlora" / "train.py"),
           "--data", str(data), "--out", str(out),
           "--max-samples", str(int(getattr(t, "max_samples", 500) or 500))]
    if str(getattr(t, "preset", "fast") or "fast") == "fast":
        cmd.append("--fast")
    try:
        with logf.open("w", encoding="utf-8") as lf:
            r = _sp.run(cmd, capture_output=False, stdout=lf, stderr=_sp.STDOUT,
                        timeout=float(getattr(t, "max_seconds", 6 * 3600) or 6 * 3600))
        ok = r.returncode == 0
    except Exception as e:
        return {"error": f"train launch failed: {e}"}
    if ok:
        state["last_train_ts"] = time.time()
        state["last_out"] = str(out)
        chain = _auto_chain(ctx, out, logf)
        state["last_chain"] = chain
        try:
            state_f.write_text(_json.dumps(state, indent=1), encoding="utf-8")
        except Exception:
            pass
        if chain.get("queued"):
            note = f"merged, imported as {chain.get('model')}, queued for the J3 gate"
        elif chain.get("note"):
            note = chain["note"]
        else:
            note = f"merge/export incomplete: {chain.get('error', chain)}"
        return {"trained": True, "out": str(out), "log": str(logf),
                "chain": chain, "note": note}
    return {"error": f"train.py exited nonzero (see {logf})"}


def run_nightly(ctx) -> dict:
    out = {}
    out["consolidated"] = consolidate(ctx)
    out["vectors"] = rebuild_vectors(ctx)
    out["router"] = maybe_train_router(ctx)
    out["teach_back"] = maybe_teach_back(ctx)
    out["sft"] = maybe_build_sft(ctx)
    out["qlora"] = maybe_train_qlora(ctx)
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


# The maintenance jobs this module owns. A test pins that this list matches the
# specs actually registered, so the disable path can never pause a stale set.
_SYSTEM_JOB_IDS = ("nightly_consolidate", "vector_rebuild", "memory_index_flush",
                   "router_retrain", "teach_back", "sft_build", "qlora_train", "log_rotation",
                   "alert_scan", "skill_gate", "model_gate")


def _set_system_jobs_enabled(worker, job_ids, enabled: bool) -> None:
    """Flip the persisted SYSTEM maintenance jobs to match scheduler.enabled.

    Only jobs this module owns (id + owner == "system") are touched — a
    user-created job with a colliding id is never modified.
    """
    for jid in job_ids:
        job = worker.store.load_job(jid)
        if job is not None and job.owner == "system" and job.enabled != enabled:
            job.enabled = enabled
            worker.store.save_job(job)
            log.info("%s durable job %s", "paused" if not enabled else "resumed",
                     jid)


def _register_nightly_jobs(worker, cfg) -> None:
    """Register maintenance work as DURABLE FUNCTION JOBS (idempotent by
    stable id). This is real, persisted work — never a no-op: each job runs
    through JobWorker -> the registered function -> execution history +
    failure notification. Schedules derive from the existing scheduler
    config, so an existing setup keeps its behavior."""
    from .automation.models import PENDING, Job, JobTrigger
    if not getattr(getattr(cfg, "scheduler", None), "enabled", True):
        # The switch must stop REAL work — including the jobs an earlier run of
        # this build already persisted, which would otherwise keep firing.
        _set_system_jobs_enabled(worker, _SYSTEM_JOB_IDS, enabled=False)
        log.info("nightly maintenance disabled (scheduler.enabled=false)")
        return
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
        ("memory_index_flush", "index memory written since the last flush (5 min)",
         JobTrigger(kind="interval", every_seconds=300),
         {"type": "function", "fn": "bee.scheduler.flush_memory_index"}, 600.0),
        ("router_retrain", "ML router retrain (only if new episodes)",
         JobTrigger(kind="daily", time=_plus(30)),
         {"type": "function", "fn": "bee.scheduler.maybe_train_router"}, 1800.0),
        ("teach_back", "cloud teach-back (golden -> skills)",
         JobTrigger(kind="daily", time=_plus(60)),
         {"type": "function", "fn": "bee.scheduler.maybe_teach_back"}, 1800.0),
        ("sft_build", "SFT dataset rebuild",
         JobTrigger(kind="daily", time=_plus(75)),
         {"type": "function", "fn": "bee.scheduler.maybe_build_sft"}, 1800.0),
        ("qlora_train", "QLoRA refresh (GPU-gated, opt-in via training.auto_qlora)",
         JobTrigger(kind="daily", time=_plus(135)),
         {"type": "function", "fn": "bee.scheduler.maybe_train_qlora"}, 21600.0),
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
        existing = worker.store.load_job(jid)
        if existing is not None:
            # config is the authority for SYSTEM jobs: an scheduler.enabled that
            # went false and comes back true un-pauses exactly what it paused
            if existing.owner == "system" and not existing.enabled:
                existing.enabled = True
                worker.store.save_job(existing)
                log.info("re-enabled durable job %s", jid)
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
      requests; interactive owners (REPL, web) pass theirs in — when created
      HERE the approver auto-denies (jobs have no browser stream attached,
      so approvals fail closed either way);
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
    # Start the event sources (heartbeat + battery + network, plus file watch
    # when configured). Before this, sources existed only as classes: nothing
    # in the production path ever started one, so proactive rules could fire
    # solely from events published inside tests.
    try:
        from .automation.events import start_sources
        worker.event_sources = start_sources(worker.bus, cfg)
    except Exception as e:
        worker.event_sources = []
        log.warning("event sources not started: %s", e)
    log.info("automation started (store=%s, %d jobs)", store.dir, len(worker.jobs()))
    return worker


def start_scheduler(ctx, cfg) -> None:
    """Deprecated shim (pre-Phase-6 APScheduler callbacks). Kept so existing
    call sites keep working; delegates to the durable worker."""
    start_automation(ctx, cfg)
