"""End-of-task bookkeeping for the agent loop: episode finish, metrics rows,
diary line, cloud teach-back goldens and the success digest.

Moved verbatim from `bee.agent.loop` (behavior unchanged). `AgentResult`
lives in .result, so there is no import cycle with the loop.
"""
from __future__ import annotations

import time

from ..episodes.logger import Episode
from ..monitor import metrics
from .result import AgentResult


def diary(task: str, result: AgentResult) -> None:
    try:
        from ..memory.md import diary_add
        snippet = (result.output or result.error or "")[:400].replace("\n", " ")
        diary_add(f"task: {task[:200].replace(chr(10), ' ')}\nresult: {snippet}",
                  model=result.model, escalated=result.escalated)
    except Exception:
        pass


def served_cloud(ctx, res: AgentResult) -> bool:
    """True when the CLOUD tier produced this answer (teach-back material).

    `res.escalated` alone under-counts: the hybrid speed tier routes routine
    work to cloud and deliberately clears the flag, so cloud-first successes
    never reached the golden corpus (measured 2026-10-17: 556 cloud-served
    episodes in the ledger, 5 goldens). The serving model name is the honest
    signal — plus `:cloud` Ollama models, which are remote."""
    if getattr(res, "escalated", False):
        return True
    name = (getattr(res, "model", "") or "").strip().lower()
    if not name:
        return False
    if name == "cloud" or name.endswith(":cloud"):
        return True
    try:
        return bool(ctx.cfg.get_llm(name).get("cloud"))
    except Exception:
        return False


def golden(task: str, res: AgentResult) -> None:
    """Teach-back: a successful CLOUD answer becomes training material for the
    local model (SFT pipeline) and skill distillation (nightly job).

    Quality gate: an explicit verifier FAIL is never recorded — a cloud
    hallucination that the verifier caught must not become a lesson.
    verify=None (no verifier run) still records: absence of a check is not
    evidence of wrongness, and starving the dataset would stall the loop."""
    if (res.verify or "") == "fail":
        return
    try:
        from .. import paths as _p, safeio as _safeio
        from ..privacy import redact as _redact
        d = _p.TRAIN_DIR / "golden"
        d.mkdir(parents=True, exist_ok=True)
        # Scrub at capture, not just at SFT build: the golden file sits on
        # disk (and in backups) between runs, and cloud answers echo user
        # PII back (see cloud_redaction). Best-effort — never block the loop.
        try:
            task_s, _ = _redact(task[:500])
            resp_s, _ = _redact((res.output or "")[:4000])
        except Exception:
            task_s, resp_s = task[:500], (res.output or "")[:4000]
        _safeio.append_json(d / "cloud_golden.jsonl",
                            {"task": task_s, "response": resp_s,
                             "model": res.model, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")})
    except Exception:
        pass


def finish(ctx, task, episode: Episode | None, res: AgentResult, start: float,
           emit, sub: bool, raw: str = "") -> AgentResult:
    # raw = the user's own wording (kernel route_text). Goldens record the
    # request as asked, not the context-augmented prompt the model saw.
    if episode:
        episode.finish(res.ok, res.output, error=res.error, escalated=res.escalated,
                       verify={"verdict": res.verify}, tokens=res.est_tokens)
    metrics.record("task", ok=res.ok, model=res.model, iters=res.iterations,
                   tools=res.tool_calls, seconds=round(time.time() - start, 1),
                   tokens=res.est_tokens, escalated=res.escalated,
                   verify=res.verify, source=res.route_source, error=res.error[:200])
    if not sub:
        diary(task, res)
        if res.ok and served_cloud(ctx, res) and (res.output or "").strip():
            golden(raw or task, res)
        if res.ok and (res.tool_calls or 0) > 0 and (res.output or "").strip():
            # Success digest for memory recall (indexed; diary transcripts are
            # not). Best-effort — recall must never break the main flow.
            try:
                from ..memory import md as _md
                _md.record_win(task, res.output)
            except Exception:
                pass
    emit({"type": "done", "output": res.output, "verify": res.verify})
    return res
