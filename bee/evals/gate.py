"""J3 — model-upgrade quality gate.

The local model is a moving target (SFT retrain, Ollama base upgrade). This
module is the ONLY sanctioned way to promote a new local model: a candidate
must PROVE itself against the current model's recorded baseline before BEE
points at it. This is the actual fix for the 8–13/21 eval ceiling — instead
of discovering a regression on a Tuesday afternoon, the regression is caught
by the gate before the model ships.

Promotion rule (all must hold):
  1. candidate eval score  >=  baseline score + margin   (config: model_gate.margin)
  2. NO structurally-stable task that passed in the baseline fails in the
     candidate. Structural tasks are the ones with deterministic assertions
     (expect_route / expect_guard / expect_verify / expect_redact) — the
     parts of the system that must NEVER get worse, regardless of how
     fluent the new model is.

Baselines live in evals/baselines.json, keyed by model name. The first gate
run for a model SEEDS its baseline (a model is never auto-promoted from an
empty baseline). Promotion writes models.yaml (local_model: <candidate>) —
the documented config layer that sits between .env and config.yaml for
model selection — and records the promotion in baselines.json for rollback.

Runs as a durable function job (bee.evals.model_gate, nightly) and manually
via `/gate`.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path

import yaml

from .. import paths

log = logging.getLogger("bee.gate")


BASELINES_FILE: Path = paths.EVALS_DIR / "baselines.json"
# P0-5: the auto-chain (scheduler.maybe_train_qlora) writes the night's model
# here; model_quality_gate consumes it (explicit arg > queue > config.yaml).
GATE_CANDIDATE_FILE: Path = paths.TRAIN_DIR / "gate_candidate.json"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ------------------------------------------------------------ baselines
def load_baselines() -> dict:
    if not BASELINES_FILE.exists():
        return {"models": {}, "promotions": []}
    try:
        data = json.loads(BASELINES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"models": {}, "promotions": []}
    data.setdefault("models", {})
    data.setdefault("promotions", [])
    return data


def save_baselines(data: dict) -> None:
    BASELINES_FILE.parent.mkdir(parents=True, exist_ok=True)
    data["promotions"] = (data.get("promotions") or [])[-50:]   # bounded history
    tmp = BASELINES_FILE.with_name(BASELINES_FILE.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(BASELINES_FILE)


# ------------------------------------------------------ gate candidate queue
def pending_candidate() -> str:
    """Model queued by the P0-5 auto-chain, else '' (missing/corrupt = '')."""
    try:
        if GATE_CANDIDATE_FILE.exists():
            data = json.loads(GATE_CANDIDATE_FILE.read_text(encoding="utf-8"))
            return str(data.get("model") or "").strip()
    except Exception:
        pass
    return ""


def queue_candidate(model: str, src: str = "", **extra) -> None:
    """Queue `model` for the next gate run (atomic write)."""
    GATE_CANDIDATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {"model": model, "src": src, "ts": _now(), **extra}
    tmp = GATE_CANDIDATE_FILE.with_name(GATE_CANDIDATE_FILE.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(GATE_CANDIDATE_FILE)


def clear_pending_candidate() -> None:
    """Consume the queue — one decisive gate attempt per queued artifact
    (VOID verdicts keep it: a quota-dead arm is not an attempt)."""
    try:
        GATE_CANDIDATE_FILE.unlink(missing_ok=True)
    except Exception:
        pass


# -------------------------------------------------------- structural tasks
def structural_task_ids() -> list[str]:
    """Task ids whose pass/fail is DETERMINISTIC (event assertions), i.e. the
    non-regression floor for any model promotion."""
    from .runner import load_tasks
    out = []
    for t in load_tasks():
        if any(t.get(k) for k in ("expect_route", "expect_guard", "expect_verify", "expect_redact")):
            out.append(t.get("id", ""))
    return [i for i in out if i]


# ------------------------------------------------------------ evaluation
def run_score(ctx, model: str) -> dict:
    """Run the full eval suite pinned to `model`; return per-task outcomes.

    Returns {"passed": int, "total": int, "per_task": {id: bool},
             "models_used": set, "rows": [rows]}."""
    from . import runner
    rows = runner.run_suite(ctx, model=model)
    per_task: dict[str, bool] = {}
    models_used: set[str] = set()
    for r in rows:
        if r.get("skipped"):
            continue
        per_task[r["id"]] = bool(r.get("ok"))
        if r.get("model"):
            models_used.add(str(r["model"]))
    passed = sum(1 for v in per_task.values() if v)
    return {"passed": passed, "total": len(per_task), "per_task": per_task,
            "models_used": models_used, "rows": rows}


def baseline_record(model: str, score: dict) -> dict:
    return {
        "model": model,
        "ts": _now(),
        "passed": score["passed"],
        "total": score["total"],
        "score": f"{score['passed']}/{score['total']}",
        "per_task": score["per_task"],
    }


def _adjudicate(ctx, active: str, candidate: str, base: dict, cand: dict,
                rounds: int) -> list[dict]:
    """P0-5: re-run tasks the two arms DISAGREE on; majority decides.

    Mutates `base` / `cand` (per_task + passed) in place and returns every
    re-run row (the caller's 429 check). Only disagreements are re-run — a
    verdict costs a couple of minutes, not a second full suite — and at n=21
    a single flaky task can no longer flip a verdict: it must lose a majority
    of `rounds` extra votes per side. `rounds < 1` = single-shot (old
    behavior)."""
    if rounds < 1:
        return []
    disagree = sorted(tid for tid, ok in cand["per_task"].items()
                      if tid in base["per_task"] and base["per_task"][tid] != ok)
    if not disagree:
        return []
    rerun_rows: list[dict] = []
    for score, model in ((base, active), (cand, candidate)):
        votes = {tid: [score["per_task"][tid]] for tid in disagree}
        for _ in range(rounds):
            try:
                from . import runner
                rows = runner.run_suite(ctx, model=model, only=disagree)
            except Exception as e:
                log.warning("adjudication re-run failed for %s (%s); votes so far stand",
                            model, e)
                break
            rerun_rows.extend(rows)
            for r in rows:
                if r.get("skipped"):
                    continue
                tid = str(r.get("id", ""))
                if tid in votes:
                    votes[tid].append(bool(r.get("ok")))
                # only the LIVE candidate score carries a models_used set —
                # the stored baseline record must stay JSON-safe (no new keys)
                if r.get("model") and isinstance(score.get("models_used"), set):
                    score["models_used"].add(str(r["model"]))
        for tid, v in votes.items():
            score["per_task"][tid] = sum(1 for x in v if x) * 2 > len(v)
        score["passed"] = sum(1 for v in score["per_task"].values() if v)
    return rerun_rows


def _rate_limited_ids(score: dict) -> list[str]:
    """Task ids whose failure was a provider rate limit (HTTP 429), not a model
    verdict. A quota-dead arm is not comparable: on 2026-10-17 the Gemini quota
    died between the seeded baseline arm and the candidate arm, three
    cloud-dependent tasks failed with `litellm.RateLimitError`, and the gate
    printed "score 14/21 < baseline 16/21 + margin 1" — a line that reads like
    model quality but is provider availability. Fail closed (never promote) but
    say "void", and allow a re-run once the quota recovers."""
    out = []
    for r in score.get("rows") or []:
        if r.get("skipped") or r.get("ok"):
            continue
        err = str(r.get("error") or "").lower()
        if "ratelimiterror" in err or "rate limit" in err or "429" in err:
            out.append(str(r.get("id")))
    return sorted(out)


def set_baseline(ctx, model: str | None = None) -> dict:
    """Record (or re-record) the baseline for `model` (default: the active
    local model). Costs one full eval run — that is deliberate."""
    model = model or ctx.cfg.ollama.model
    score = run_score(ctx, model)
    if score["total"] < 1:
        return {"ok": False, "reason": "eval produced no usable rows (all skipped?)"}
    if model not in score["models_used"]:
        return {"ok": False, "reason": f"model {model!r} was never invoked during the "
                                        "suite — check the name against `ollama list`"}
    rl = _rate_limited_ids(score)
    if rl:
        return {"ok": False, "reason": "eval hit provider rate limits (429) on: "
                                        + ", ".join(rl) + " — baseline NOT seeded (a "
                                        "quota-dead arm is not a baseline); re-run when "
                                        "the quota recovers"}
    data = load_baselines()
    data["models"][model] = baseline_record(model, score)
    save_baselines(data)
    return {"ok": True, "model": model, "baseline": data["models"][model]}


# -------------------------------------------------------------- promotion
def promote_model(model: str) -> None:
    """Point BEE at `model` via models.yaml (the documented promotion layer)."""
    data = {}
    if paths.MODELS_YAML.exists():
        try:
            data = yaml.safe_load(paths.MODELS_YAML.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}
    data["local_model"] = model
    data["promoted_at"] = _now()
    tmp = paths.MODELS_YAML.with_name("models.yaml.tmp")
    tmp.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    tmp.replace(paths.MODELS_YAML)


def rollback_model() -> dict:
    """Undo a promotion: remove local_model from models.yaml -> config.yaml wins again."""
    if not paths.MODELS_YAML.exists():
        return {"ok": False, "reason": "models.yaml absent — nothing to roll back"}
    data = {}
    try:
        data = yaml.safe_load(paths.MODELS_YAML.read_text(encoding="utf-8")) or {}
    except Exception:
        pass
    removed = data.pop("local_model", None)
    if removed is None:
        return {"ok": False, "reason": "no local_model override in models.yaml"}
    tmp = paths.MODELS_YAML.with_name("models.yaml.tmp")
    tmp.write_text(yaml.safe_dump(data, sort_keys=False) if data else "", encoding="utf-8")
    tmp.replace(paths.MODELS_YAML)
    return {"ok": True, "rolled_back": removed}


# ------------------------------------------------------------------ gate
def model_quality_gate(ctx, candidate: str | None = None, margin: int | None = None) -> dict:
    """J3 gate. `candidate` defaults to the P0-5 auto-chain queue
    (train/gate_candidate.json), then config.yaml model_gate.candidate.

    Outcomes:
      {"ok": True,  "promoted": ...}     candidate beats baseline -> models.yaml updated
      {"ok": True,  "seeded": ...}       no baseline for the active model yet -> recorded
      {"ok": False, "reasons": [...]}    candidate rejected (kept on the current model)
      {"ok": False, "void": True, ...}   provider rate-limit (429) corrupted an arm -> retry later
      {"ok": True,  "skipped": ...}      nothing to do (no candidate configured)
    """
    mg = getattr(ctx.cfg, "model_gate", None)
    if mg is not None and not getattr(mg, "enabled", True):
        return {"ok": True, "skipped": "model_gate.enabled=false (config)"}
    # P0-5: explicit arg > auto-chain queue > config.yaml. Only a candidate
    # that CAME from the queue is consumed here (one attempt per artifact).
    queued = "" if candidate else pending_candidate()
    candidate = candidate or queued or (getattr(mg, "candidate", "") if mg else "")
    if not candidate:
        return {"ok": True, "skipped": "no candidate configured (config.yaml: model_gate.candidate)"}
    margin = int(margin if margin is not None else (getattr(mg, "margin", 1) if mg else 1))
    active = ctx.cfg.ollama.model
    if candidate == active:
        if queued:
            clear_pending_candidate()   # the queue pointed at the already-active model
        return {"ok": True, "skipped": f"candidate == active model ({candidate})"}

    # candidate must actually exist in Ollama before we spend an eval on it
    try:
        models = ctx.client.models_list() or []
    except Exception:
        models = []
    if models and candidate not in {m.split(":")[0] if isinstance(m, str) else m for m in models} \
            and candidate not in models:
        return {"ok": False, "reasons": [f"candidate {candidate!r} not in `ollama list` — "
                                         f"train/pull it first (available: {len(models)})"]}

    data = load_baselines()
    # seed the active model's baseline on first use (one extra suite run)
    if active not in data["models"]:
        seed = set_baseline(ctx, active)
        if not seed.get("ok"):
            return {"ok": False, "reasons": [f"could not seed baseline for {active!r}: {seed.get('reason')}"]}
        data = load_baselines()
        if candidate == active:
            return {"ok": True, "seeded": active}

    base = data["models"][active]
    cand = run_score(ctx, candidate)
    if cand["total"] < 1:
        return {"ok": False, "reasons": ["candidate suite produced no usable rows"]}
    if candidate not in cand["models_used"]:
        return {"ok": False, "reasons": [f"candidate {candidate!r} was never invoked during the "
                                         "suite (escalation/fallback?) — cannot score"]}

    rl = _rate_limited_ids(cand)
    if rl:
        # not recorded: a 429-dead arm is not an attempt (see _rate_limited_ids)
        return {"ok": False, "void": True, "rate_limited": rl, "reasons": [
            "candidate arm hit provider rate limits (429) on: " + ", ".join(rl)
            + " — comparison void (provider availability, not model quality); "
            "re-run when the quota recovers"]}

    # A62 + A64 (2026-10-18): skipped rows are dropped from BOTH sides, so the
    # arms can score different task sets while the score test below is a raw pass
    # COUNT. A candidate that skipped the hard half read as a clean 12/12 against
    # a baseline of 10/21 (A62); and a baseline SEEDED from a partial run could be
    # compared against a larger candidate, letting a loss on a baseline task hide
    # behind passes on tasks the baseline never ran (A64). Only an identical task
    # set is comparable, whichever side is bigger.
    base_tasks = set(base.get("per_task") or {})
    cand_tasks = set(cand["per_task"])
    if base_tasks != cand_tasks:
        diff = []
        if base_tasks - cand_tasks:
            diff.append(f"{len(base_tasks - cand_tasks)} baseline task(s) did not "
                        "run for the candidate")
        if cand_tasks - base_tasks:
            diff.append(f"{len(cand_tasks - base_tasks)} task(s) ran only for "
                        "the candidate")
        return {"ok": False, "reasons": [
            f"not comparable: the {active} baseline scored {len(base_tasks)} task(s) "
            f"and the candidate {len(cand_tasks)} — " + "; ".join(diff)
            + ". Both arms must cover the same task set: re-run with the skipped "
            "tasks available (usually: cloud up), and re-seed the baseline if it "
            "was itself recorded from a partial run."]}

    # P0-5: majority-vote re-runs for the tasks the two arms DISAGREE on, BEFORE
    # judging (statistical power; see ModelGateCfg.adjudication_rounds). A
    # failed re-run degrades to fewer votes, never to a crash (see _adjudicate).
    rerun_rows = _adjudicate(ctx, active, candidate, base, cand,
                             int(getattr(mg, "adjudication_rounds", 2) or 0))
    rl_rerun = _rate_limited_ids({"rows": rerun_rows})
    if rl_rerun:
        return {"ok": False, "void": True, "rate_limited": rl_rerun, "reasons": [
            "adjudication re-runs hit provider rate limits (429) on: " + ", ".join(rl_rerun)
            + " — comparison void (provider availability, not model quality); "
            "re-run when the quota recovers"]}

    structural = set(structural_task_ids())
    regressed = sorted(tid for tid, ok in (base.get("per_task") or {}).items()
                       if ok and tid in structural and not cand["per_task"].get(tid))
    reasons: list[str] = []
    if cand["passed"] < base["passed"] + margin:
        reasons.append(f"score {cand['passed']}/{cand['total']} < baseline "
                       f"{base['passed']}/{base['total']} + margin {margin}")
    if regressed:
        reasons.append("structural regressions: " + ", ".join(regressed))

    # record the candidate's attempt either way (useful history, bounded)
    data["models"][candidate] = baseline_record(candidate, cand)
    if reasons:
        if queued:
            clear_pending_candidate()
        save_baselines(data)
        try:
            from ..memory.md import diary_add
            diary_add(f"model gate REJECTED {candidate}: " + "; ".join(reasons))
        except Exception:
            pass
        return {"ok": False, "reasons": reasons,
                "before": base["score"], "after": f"{cand['passed']}/{cand['total']}",
                "regressed": regressed}

    # ---- promote
    if queued:
        clear_pending_candidate()
    promote_model(candidate)
    data["promotions"].append({
        "ts": _now(), "from": active, "to": candidate,
        "before": base["score"], "after": f"{cand['passed']}/{cand['total']}",
    })
    save_baselines(data)
    try:
        from ..memory.md import diary_add
        diary_add(f"model gate PROMOTED {active} -> {candidate} "
                  f"({base['score']} -> {cand['passed']}/{cand['total']})")
    except Exception:
        pass
    return {"ok": True, "promoted": candidate, "from": active,
            "before": base["score"], "after": f"{cand['passed']}/{cand['total']}"}
