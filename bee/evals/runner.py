"""Eval suite runner — the self-improvement gate.

Runs evals/tasks.yaml through the real agent loop, checks expected substrings
AND deterministic event assertions (routing tier, guard blocks, verification
verdict, PII redaction), appends to evals/results.jsonl (one line per task per
run), writes evals/results_summary.json for the latest run and prints a table.
A model/prompt/skill change is a win only if this score goes up.

Task schema (evals/tasks.yaml):
  id, task, expect: [substrings]
  optional:
    expect_route:  "det" | "cloud" | "local" | "deterministic" | "fallback" ...
                   (first route event: model or source must match)
    expect_guard:  "blocked"   (a guard event with action ask|deny, or a
                   blocked tool result, must occur)
    expect_verify: "pass"      (verifier verdict on the final answer)
    expect_redact: true        (a redact event with n > 0 must occur)
    repeat: N                  (run the task N times; every run must pass)
    skip_if: "cloud"           (skip unless cloud is configured)
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import yaml

from .. import paths
from ..agent.loop import AgentResult

# model output may contain emoji — redirected Windows consoles default to
# cp1252 and would crash the run; force UTF-8 with replacement fallback
try:
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def load_tasks() -> list[dict]:
    p = paths.EVALS_DIR / "tasks.yaml"
    if not p.exists():
        return []
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("tasks", [])


def _events_ok(t: dict, events: list[dict], r: AgentResult) -> tuple[bool, str]:
    # route
    want = t.get("expect_route")
    if want:
        routes = [e for e in events if e.get("type") == "route"]
        if not routes:
            return False, f"expect_route={want} but no route event"
        e0 = routes[0]
        if want not in (e0.get("model"), e0.get("source")):
            return False, f"expect_route={want} got model={e0.get('model')} source={e0.get('source')}"
    # guard
    if t.get("expect_guard") == "blocked":
        blocked = (any(e.get("type") == "guard" and e.get("action") in ("ask", "deny") for e in events)
                   or any(e.get("type") == "tool_result" and (e.get("preview") or "").find("blocked") >= 0
                          for e in events))
        if not blocked:
            return False, "expect_guard=blocked but no guard block occurred"
    # verify
    want_v = t.get("expect_verify")
    if want_v:
        got_v = r.verify or next((e.get("verdict") for e in reversed(events)
                                  if e.get("type") == "verify"), None)
        if got_v != want_v:
            return False, f"expect_verify={want_v} got {got_v}"
    # redaction
    if t.get("expect_redact"):
        if not any(e.get("type") == "redact" and int(e.get("n") or 0) > 0 for e in events):
            return False, "expect_redact=true but no PII redaction event"
    return True, ""


def check_task(t: dict, r: AgentResult, events: list[dict]) -> tuple[bool, str]:
    if not r.ok:
        return False, r.error or "task not ok"
    out = (r.output or "").lower()
    for e in t.get("expect") or []:
        if str(e).lower() not in out:
            return False, f"missing substring {e!r}"
    return _events_ok(t, events, r)


def _should_skip(t: dict, ctx) -> bool:
    if t.get("skip_if") == "cloud":
        from ..agent.loop import _cloud_up
        if not _cloud_up(ctx.cfg):
            return True
    return False


def run_suite(ctx, model: str | None = None, only: "str | list[str] | None" = None) -> list[dict]:
    """only: substring match (str) or explicit id list (list) — for batched runs.

    Audit item 1: tasks run through the SAME AgentKernel as interactive use
    (capability gate, task state, receipts, verification, telemetry) — the
    eval now measures what the user actually gets. A fresh session id per
    task/rep keeps follow-up resolution from leaking across tasks."""
    kernel = getattr(ctx, "kernel", None)
    if kernel is None:
        from ..kernel import AgentKernel
        kernel = AgentKernel(ctx, approver=lambda t, a, r: False)
        ctx.kernel = kernel
    tasks = load_tasks()
    results = []
    print(f"\n== BEE eval suite — {len(tasks)} tasks ==")
    for i, t in enumerate(tasks, 1):
        tid = t.get("id", f"task{i}")
        if only and not (tid in only if isinstance(only, list) else only in tid):
            continue
        if _should_skip(t, ctx):
            print(f"  [SKIP] {t.get('id', f'task{i}'):18s} (condition not met)")
            results.append({"ts": datetime.now().isoformat(timespec="seconds"),
                            "id": t.get("id", f"task{i}"), "ok": True, "skipped": True,
                            "seconds": 0, "error": "", "model": None,
                            "expect": t.get("expect"), "output_excerpt": ""})
            continue
        tid = t.get("id", f"task{i}")
        reps = max(1, int(t.get("repeat") or 1))
        t0 = time.time()
        ok, err, last_r = True, "", None
        for rep in range(reps):
            events: list[dict] = []
            try:
                # never run a task on a poisoned cancel event (a Ctrl-C from an
                # earlier task would instantly cancel everything after it)
                ce = getattr(ctx, "cancel_event", None)
                if hasattr(ce, "clear"):
                    ce.clear()
                tr = kernel.run(t["task"], session_id=f"eval-{tid}-r{rep}",
                                model=model, on_event=events.append, max_iters=15)
                r = tr.agent_result
                last_r = r
                ok, err = check_task(t, r, events)
            except Exception as e:
                ok, err = False, f"{type(e).__name__}: {e}"
            if not ok and reps > 1 and rep < reps - 1:
                continue  # retry remaining reps; overall = all must pass
            if not ok:
                break
        dt = round(time.time() - t0, 1)
        mark = "PASS" if ok else "FAIL"
        meta = f"  tools={last_r.tool_calls}" if last_r else ""
        print(f"  [{mark}] {tid:18s} {dt:6.1f}s{meta}"
              + (f"  x{reps}" if reps > 1 else ""))
        if not ok:
            print(f"         expect: {t.get('expect')}  events: {t.get('expect_route') or t.get('expect_guard') or t.get('expect_verify') or t.get('expect_redact') or ''}")
            print(f"         error: {str(err)[:160]}")
        row = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "id": tid, "ok": ok, "seconds": dt, "error": str(err),
            "model": last_r.model if last_r else None,
            "route_source": last_r.route_source if last_r else None,
            "verify": last_r.verify if last_r else None,
            "repeat": reps,
            "expect": t.get("expect"),
            "output_excerpt": ((last_r.output if last_r else "") or "")[:300],
        }
        results.append(row)
        # persist IMMEDIATELY — background batches can be killed at the 15-min
        # limit; per-task append keeps every finished result
        paths.EVAL_RESULTS.parent.mkdir(parents=True, exist_ok=True)
        with paths.EVAL_RESULTS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        # user Ctrl-C during the suite: stop cleanly instead of running the
        # remaining tasks on a poisoned cancel event
        ce = getattr(ctx, "cancel_event", None)
        if (last_r is not None and last_r.error == "cancelled"
                and ce is not None and ce.is_set()):
            print(f"  (cancelled by user - stopping the suite after {i}/{len(tasks)})")
            break
    # summary over the LATEST result per task id (batch-tolerant: a partial
    # batch run must not clobber the aggregate picture)
    latest: dict[str, dict] = {}
    for ln in paths.EVAL_RESULTS.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        try:
            row = json.loads(ln)
        except Exception:
            continue
        latest.setdefault(row.get("id", "?"), row)
        if latest[row.get("id", "?")].get("ts", "") <= row.get("ts", ""):
            latest[row.get("id", "?")] = row
    passed = sum(1 for r in latest.values() if r.get("ok"))
    summary = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "n": len(latest), "ok": passed, "score": f"{passed}/{len(latest)}",
        "failures": [r.get("id") for r in latest.values() if not r.get("ok")],
    }
    (paths.EVALS_DIR / "results_summary.json").write_text(
        json.dumps(summary, indent=1), encoding="utf-8")
    print(f"\n  score: {passed}/{len(latest)} overall (this run: "
          f"{sum(1 for r in results if r['ok'])}/{len(results)})  (history: {paths.EVAL_RESULTS})")
    return results
