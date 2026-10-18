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
    repeat: N                  (run the task N times; EVERY rep must pass — all
                                reps run even after a failure, and the row keeps
                                reps_passed/reps_total as the flake evidence)
    skip_if: "cloud"           (skip unless cloud is configured)

P1-3: every run also reports a 95% Wilson interval for its own pass rate, so a
"38/60" is not read as a measurement — at these n a one-task delta is inside the
noise, and the model gate compares PASS COUNTS across two arms.
"""
from __future__ import annotations

import json
import hashlib
import os
import shutil
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import yaml

from .. import paths
from ..agent.loop import AgentResult


@contextmanager
def _isolated_memory():
    """Run the suite against a COPY of the user's memory, not the original.

    The eval writes: `memory_write` stores a fact, the remember/recall paths
    append to profile/longterm, and the kernel persists sessions + receipts.
    Pointed at the real tree, every `/eval` left rows behind — seven copies of
    one eval fragment ("Neovim. Use the profile memory tool.") ended up in
    memory/store.json as user facts. A copy keeps the recall tasks honest (their
    premise is still in the data the run reads) while discarding what the run
    created."""
    keys = ("MEMORY_DIR", "DIARY_DIR", "LESSONS_DIR", "VECTOR_DIR",
            "PROFILE_MD", "LONGTERM_MD", "SYSTEM_MD",
            "SESSIONS_DIR", "RECEIPTS_FILE", "AUDIT_FILE")
    saved = {k: getattr(paths, k) for k in keys}
    tmp = Path(tempfile.mkdtemp(prefix="bee_eval_memory_"))
    try:
        root = tmp / "memory"
        try:
            shutil.copytree(saved["MEMORY_DIR"], root)
        except Exception:
            root.mkdir(parents=True, exist_ok=True)
        paths.MEMORY_DIR = root
        paths.DIARY_DIR = root / "diary"
        paths.LESSONS_DIR = root / "lessons"
        paths.VECTOR_DIR = root / "vectors"
        paths.PROFILE_MD = root / "profile.md"
        paths.LONGTERM_MD = root / "longterm.md"
        paths.SYSTEM_MD = root / "system.md"
        # The kernel builds its ReceiptLog/sessions dir at construction time, and
        # `_run_suite` builds the kernel inside this context manager — so these two
        # have to be redirected here or the run writes the user's audit trail
        # (measured 2026-10-13: 1568 of 1571 live receipt rows and 2540 of 2543
        # rotated ones carry an `eval-*` session id, plus 23 eval session files).
        paths.SESSIONS_DIR = root / "sessions"
        paths.RECEIPTS_FILE = root / "receipts.jsonl"
        # audit.jsonl is the third stream of that trio (one row per exec-tool call
        # and per guard decision). It lives at the project root, so it needs its own
        # entry — and unlike the receipts it stores no session id, so a run's rows
        # cannot be found and removed afterwards.
        paths.AUDIT_FILE = tmp / "audit.jsonl"
        yield root
    finally:
        for k, v in saved.items():
            setattr(paths, k, v)
        shutil.rmtree(tmp, ignore_errors=True)


@contextmanager
def _isolated_telemetry():
    """A44: the eval must not write the user's telemetry or training corpus.

    `_isolated_memory` (A31b) covered memory only, so every scored run kept
    appending to the two streams the USER reads: `metrics/metrics.jsonl` — which
    drives the dashboard KPIs *and* `cfg.alerts` thresholds, so a synthetic failure
    can raise a real desktop alert — and `train/episodes/*.jsonl`, the corpus the
    nightly router retrain and the SFT build eat. Measured on 2026-10-09 after one
    full run: **322 of 375** of today's episode rows had a task text that is an
    eval prompt (16 distinct eval ids), and 473 new rows in metrics.jsonl with
    session ids like `eval-cloud_redaction-r0`. Same class as A25b/A25c, one entry
    point later."""
    keys = ("METRICS_DIR", "METRICS_FILE", "EPISODES_DIR", "SKILLS_DIR")
    saved = {k: getattr(paths, k) for k in keys}
    tmp = Path(tempfile.mkdtemp(prefix="bee_eval_telemetry_"))
    try:
        (tmp / "metrics").mkdir()
        (tmp / "episodes").mkdir()
        (tmp / "skills").mkdir()
        paths.METRICS_DIR = tmp / "metrics"
        paths.METRICS_FILE = tmp / "metrics" / "metrics.jsonl"
        paths.EPISODES_DIR = tmp / "episodes"
        paths.SKILLS_DIR = tmp / "skills"
        yield tmp
    finally:
        for k, v in saved.items():
            setattr(paths, k, v)
        shutil.rmtree(tmp, ignore_errors=True)


# The suite's own report artefacts — allowed to change (they are the run's output).
_KEEP_CHANGED = {"evals/results.jsonl", "evals/results_summary.json",
                 "evals/REPORT.md", "evals/verify_results.json",
                 "evals/bench_model.json", "evals/compare_results.jsonl"}

# Local, in-workspace compute and file actions a user answers 'yes' to every day.
# The suite used to auto-deny EVERY prompt, which graded the assistant in a
# configuration nobody runs: any task whose correct answer requires executing code
# (dsa_gcd_lcm, dsa_lis, math_sieve, file_roundtrip) was unsatisfiable by design —
# the executed 21/588 could never reach the answer. Destructive and
# externally-visible actions (shell, sandbox_run, systemctl, email, job creation,
# skill writes) stay denied, so `guard_blocked` still proves a dangerous command is
# refused and reported honestly.
_EVAL_ALLOW = {"code_run", "file_write", "file_read", "file_list", "planner",
               "calculator"}


def eval_approver(tool: str, args: dict, reason: str, workspace=None) -> bool:
    """The permission prompt the eval answers on the user's behalf.

    `file_write` is granted for CREATING a file (`file_roundtrip` asks for a new
    eval_probe.txt) and refused for overwriting one the user already has: the suite
    measures whether the assistant can do the work, it must never be able to destroy
    a line of it. `_restore_workspace` stays as the backstop, not the control."""
    if str(tool or "") not in _EVAL_ALLOW:
        return False
    if tool == "file_write" and workspace is not None:
        try:
            if (Path(workspace) / str((args or {}).get("path") or "")).exists():
                return False
        except Exception:
            return False
    return True


_SNAP_DIRS = {"bee", "tests", "docs", "evals", "scripts", "web", "site"}
_SNAP_SKIP = {".git", "__pycache__", ".venv", "venv", "node_modules", ".pytest_cache",
              ".mypy_cache", "build", "dist", "memory", "models", "logs", "tmp",
              "temp", ".idea", ".vscode"}
_SNAP_MAX = 4 * 1024 * 1024          # bytes; larger files are data, not code


def _tree_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        top = rel_dir.split("/")[0]
        if rel_dir != "." and top not in _SNAP_DIRS:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in _SNAP_SKIP]
        for fn in filenames:
            if fn.endswith((".pyc", ".log")):
                continue
            yield Path(dirpath) / fn


@contextmanager
def _restore_workspace(root: Path):
    """Leave every source file exactly as the run found it — by bytes, not by git.

    Approving `file_write` and `code_run` (A36a) means the suite can now create and
    edit files in the user's real project; `file_roundtrip` literally asks for
    eval_probe.txt, and the first version of this guard used `git status` to decide
    what to restore. That misclassified the user's own uncommitted work — a file the
    run never touched (bee/agent/client.py, with real uncommitted changes) looked
    'clean before' because of a refreshed index, was moved aside, and the diff was
    nearly lost. So: snapshot the bytes of the code tree on entry and put them back
    where they differ. Pre-existing uncommitted work is then protected by
    construction, because 'as found' means 'as the user had it', not 'as HEAD has it'.

    NOTE (live 2026-10-17): an edit the OPERATOR makes while the suite is in flight
    is indistinguishable from run debris and gets rolled back with everything else —
    that is how docs/STATUS.md came back to its entry bytes mid-gate. What this
    restore puts back (and the run-invented files it sweeps) is now logged.
    """
    if not root or not Path(root).exists():
        yield Path(root) if root else None
        return
    root = Path(root)
    side = Path(tempfile.mkdtemp(prefix="bee_eval_ws_snapshot_"))
    orig = side / "orig"
    digests = {}
    for p in _tree_files(root):
        rel = p.relative_to(root).as_posix()
        try:
            if p.stat().st_size > _SNAP_MAX:
                continue
            b = p.read_bytes()
        except Exception:
            continue
        d = orig / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        try:
            d.write_bytes(b)
            digests[rel] = hashlib.sha256(b).hexdigest()
        except Exception:
            continue
    try:
        yield root
    finally:
        now = {}
        for p in _tree_files(root):
            rel = p.relative_to(root).as_posix()
            try:
                now[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
            except Exception:
                continue
        reverted, swept = [], []
        for rel, digest in sorted(digests.items()):
            if rel in _KEEP_CHANGED:
                continue
            if now.get(rel) == digest:
                continue                      # untouched by the run
            try:
                if now.get(rel) is None:       # the run deleted it
                    (root / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(orig / rel, root / rel)
                reverted.append(rel)
            except Exception:
                continue
        for rel in sorted(set(now) - set(digests)):
            if rel in _KEEP_CHANGED:
                continue
            p = root / rel                    # a file the run invented: keep it out
            try:
                dest = side / "invented" / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(p), str(dest))
                swept.append(rel)
            except Exception:
                continue
        # Say what was put back. A non-empty `reverted` can also mean the
        # operator edited a file WHILE this suite was in flight — that edit is
        # reverted by design (see the docstring) and this log line is the only
        # place the rollback is visible.
        if reverted or swept:
            import logging as _logging
            _logging.getLogger("bee.evals").info(
                "eval workspace restore: put back %d file(s), swept %d "
                "run-invented file(s)%s", len(reverted), len(swept),
                (" — put back: " + ", ".join(reverted[:8])) if reverted else "")


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
    # tool executed (negative control against vacuous passes: an empty
    # `expect` plus r.ok alone certifies nothing — require the tool's
    # tool_result event so the task proves the mechanism ran)
    want_tool = t.get("expect_tool")
    if want_tool:
        if not any(e.get("type") == "tool_result" and e.get("tool") == want_tool
                   for e in events):
            return False, f"expect_tool={want_tool} but no tool_result event for it"
    return True, ""


def check_task(t: dict, r: AgentResult, events: list[dict]) -> tuple[bool, str]:
    if not r.ok:
        return False, r.error or "task not ok"
    out = (r.output or "").lower()
    for e in t.get("expect") or []:
        if str(e).lower() not in out:
            return False, f"missing substring {e!r}"
    # A45d: some expectations encode a CHOICE rather than a requirement.
    # `plan_complex` asserts the plan names the library it will load a 50 MB CSV
    # with; the literal was 'pandas', but the plan named `polars` — a defensible,
    # arguably better answer for that size — so a correct plan failed on vocabulary.
    # The premise being tested is "commits to a real library", so that is what is
    # asserted now, against a set of libraries that can actually do the job. This
    # is a corrected premise, not a loosened one: an answer naming NO library still
    # fails, and it must name one of a closed list.
    any_of = [str(x) for x in (t.get("expect_any") or [])]
    if any_of and not any(a.lower() in out for a in any_of):
        return False, f"expected at least one of {any_of}"
    return _events_ok(t, events, r)


def wilson_interval(k: int, n: int, z: float = 1.96) -> "tuple[float, float] | None":
    """95% Wilson score interval for k passes in n trials (None when n = 0).

    P1-3: the printed score is a point estimate over 21-60 tasks; the normal
    approximation has zero width at k=0/k=n (where the answer is least certain),
    so the interval here is Wilson, which stays sane at the extremes."""
    if n <= 0:
        return None
    p = k / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def summarize(latest: dict[str, dict], results: list[dict]) -> dict:
    """A52: `score` is the latest row per task id over ALL of results.jsonl, so a
    1-task run printed "21/21 overall" while 20 of those rows came from earlier runs
    of different code — and that is the number reports kept quoting. The run's own
    result is now its own field, and the carry-over is stated instead of hidden.

    A62 adds the second half of the same lie: a task that never ran is written
    `ok: True, skipped: True` (cloud not up), and `ok` alone counted it as a pass.
    So a 21-task run with 5 skips reported "21/21" and `single_run: True`. Skipped
    tasks are now in neither the numerator nor the denominator, are listed by id,
    and forbid the `single_run` claim.

    P1-3: the same number gains its uncertainty (`ci95`/`ci95_str` over this
    run's task-level outcomes) and a `flaky` list — repeat tasks whose reps did
    not all pass, with the per-rep counts — so a near-threshold gate verdict
    cannot be argued from a bare ratio."""
    ran = [r for r in results if not r.get("skipped")]
    skipped_ids = sorted(str(r.get("id")) for r in results if r.get("skipped"))
    passed = sum(1 for r in latest.values() if r.get("ok"))
    ran_ids = {str(r.get("id")) for r in ran}
    run_ok = sum(1 for r in ran if r.get("ok"))
    carried = len([i for i in latest if i not in ran_ids])
    ci = wilson_interval(run_ok, len(ran))
    flaky = [
        {"id": str(r.get("id")), "passed": int(r.get("reps_passed") or 0),
         "total": int(r.get("reps_total") or 0)}
        for r in ran
        if int(r.get("reps_total") or 0) > 1
        and 0 < int(r.get("reps_passed") or 0) < int(r.get("reps_total") or 0)
    ]
    return {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "n": len(latest), "ok": passed, "score": f"{passed}/{len(latest)}",
        "failures": sorted(str(r.get("id")) for r in latest.values() if not r.get("ok")),
        "run_n": len(ran), "run_ok": run_ok,
        "run_score": f"{run_ok}/{len(ran)}",
        "run_failures": sorted(str(r.get("id")) for r in ran if not r.get("ok")),
        "ci95": [round(ci[0] * 100, 1), round(ci[1] * 100, 1)] if ci else None,
        "ci95_str": f"{ci[0] * 100:.1f}-{ci[1] * 100:.1f}%" if ci else "",
        "flaky": flaky,
        "skipped": len(skipped_ids), "skipped_ids": skipped_ids,
        "carried": carried,
        "single_run": carried == 0 and skipped_ids == [] and len(ran) == len(latest),
    }


def _should_skip(t: dict, ctx, model: "str | None" = None) -> bool:
    """skip_if contract.

    `cloud`: the cloud tier is down, so a task that grades it cannot run.
    `pinned_model` (P1-3): run_suite was called with an explicit model — the
    fastpath tier is then bypassed by design (loop.py: "explicit model hints
    always win over fast paths"), so a task asserting the fastpath's OWN
    behavior has nothing to measure and would grade the model instead, failing
    by construction in both gate arms. Skipped, and reported as skipped."""
    cond = t.get("skip_if")
    if cond == "cloud":
        from ..agent.loop import _cloud_up
        if not _cloud_up(ctx.cfg):
            return True
    elif cond == "pinned_model":
        return model is not None
    return False


def run_suite(ctx, model: str | None = None, only: "str | list[str] | None" = None) -> list[dict]:
    """Public entry: the run happens against an isolated copy of memory, and the
    workspace is restored to the state it was found in afterwards.

    `model` pins every task to that model (explicit route): det/smalltalk still
    answer deterministically, but fastpath tasks that assert the fastpath tier
    are skipped (`skip_if: pinned_model`) — they are scored in interactive runs
    (model=None), where the fastpath tier is live. Gate runs always pin a model
    (they compare models); interactive runs score the full stack."""
    cfg = getattr(ctx, "cfg", None)
    prev = None
    if cfg is not None:
        # A40b: the kernel now reflects after every task on every surface. Inside
        # the scored run that would add an extra local-model call per task AND grow
        # the isolated lessons file mid-run, so later tasks would see a different
        # system prompt than earlier ones. Neither is what the eval measures.
        prev = cfg.learning.reflect
        cfg.learning.reflect = False
    try:
        with _isolated_memory(), _isolated_telemetry(), \
                _restore_workspace(getattr(ctx, "workspace", None)):
            return _run_suite(ctx, model=model, only=only)
    finally:
        if cfg is not None and prev is not None:
            cfg.learning.reflect = prev


def _run_suite(ctx, model: str | None = None, only: "str | list[str] | None" = None) -> list[dict]:
    """only: substring match (str) or explicit id list (list) — for batched runs.

    Audit item 1: tasks run through the SAME AgentKernel as interactive use
    (capability gate, task state, receipts, verification, telemetry) — the
    eval now measures what the user actually gets. A fresh session id per
    task/rep keeps follow-up resolution from leaking across tasks.

    The kernel is built HERE rather than reused: it resolves its memory store,
    sessions and receipts at construction time, and inside `_isolated_memory()`
    those must point at the copy. The caller's own kernel is put back after."""
    kernel = getattr(ctx, "kernel", None)
    from ..kernel import AgentKernel
    from functools import partial
    ctx.kernel = AgentKernel(ctx, approver=partial(
        eval_approver, workspace=getattr(ctx, "workspace", None)))
    try:
        return _run_tasks(ctx, model, only)
    finally:
        ctx.kernel = kernel


def _run_tasks(ctx, model, only) -> list[dict]:
    kernel = ctx.kernel
    tasks = load_tasks()
    results = []
    print(f"\n== BEE eval suite — {len(tasks)} tasks ==")
    for i, t in enumerate(tasks, 1):
        tid = t.get("id", f"task{i}")
        if only and not (tid in only if isinstance(only, list) else only in tid):
            continue
        if _should_skip(t, ctx, model):
            print(f"  [SKIP] {t.get('id', f'task{i}'):18s} "
                  f"({t.get('skip_if') or 'condition'} not met)")
            results.append({"ts": datetime.now().isoformat(timespec="seconds"),
                            "id": t.get("id", f"task{i}"), "ok": True, "skipped": True,
                            "seconds": 0, "error": "", "model": None,
                            "expect": t.get("expect"), "output_excerpt": ""})
            continue
        tid = t.get("id", f"task{i}")
        reps = max(1, int(t.get("repeat") or 1))
        t0 = time.time()
        ok, err, last_r = True, "", None
        reps_passed = 0
        for rep in range(reps):
            events: list[dict] = []
            rep_ok = False
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
                rep_ok, err = check_task(t, r, events)
            except Exception as e:
                rep_ok, err = False, f"{type(e).__name__}: {e}"
            if rep_ok:
                reps_passed += 1
            else:
                ok = False
            # P1-3: every rep runs even after one fails — "2/3 reps" is the
            # flake evidence and the pass bar was already missed. The old loop
            # let a later passing rep overwrite an earlier failure, so the
            # "every run must pass" contract above was documented but not kept.
        dt = round(time.time() - t0, 1)
        mark = "PASS" if ok else "FAIL"
        meta = f"  tools={last_r.tool_calls}" if last_r else ""
        rep_note = f"  x{reps} ({reps_passed}/{reps} reps)" if reps > 1 else ""
        print(f"  [{mark}] {tid:18s} {dt:6.1f}s{meta}{rep_note}")
        if not ok:
            print(f"         expect: {t.get('expect')}  events: {t.get('expect_route') or t.get('expect_guard') or t.get('expect_verify') or t.get('expect_redact') or ''}")
            if reps > 1:
                print(f"         reps: {reps_passed}/{reps} passed")
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
            **({"reps_passed": reps_passed, "reps_total": reps} if reps > 1 else {}),
        }
        results.append(row)
        # persist IMMEDIATELY — background batches can be killed at the 15-min
        # limit; per-task append keeps every finished result
        paths.EVAL_RESULTS.parent.mkdir(parents=True, exist_ok=True)
        from .. import safeio
        safeio.append_json(paths.EVAL_RESULTS, row)
        # user Ctrl-C during the suite: stop cleanly instead of running the
        # remaining tasks on a poisoned cancel event
        ce = getattr(ctx, "cancel_event", None)
        if (last_r is not None and last_r.error == "cancelled"
                and ce is not None and ce.is_set()):
            print(f"  (cancelled by user - stopping the suite after {i}/{len(tasks)})")
            break
    # summary over the LATEST result per task id (batch-tolerant: a partial
    # batch run must not clobber the aggregate picture) — but that aggregate is
    # NOT this run's score, and A52 made sure nobody reads it as one.
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
    summary = summarize(latest, results)
    (paths.EVALS_DIR / "results_summary.json").write_text(
        json.dumps(summary, indent=1), encoding="utf-8")
    skip_note = ""
    if summary["skipped"]:
        skip_note = (f"\n  SKIPPED (never ran, not counted as a pass): "
                     f"{summary['skipped']} — {', '.join(summary['skipped_ids'])}")
    # P1-3: the score is a point estimate over tens of tasks; say so.
    ci_note = f" (95% CI {summary['ci95_str']})" if summary.get("ci95_str") else ""
    flake_note = ""
    if summary.get("flaky"):
        flake_note = ("\n  rep flakes (repeat tasks that failed some reps): "
                      + ", ".join(f"{f['id']} {f['passed']}/{f['total']}"
                                  for f in summary["flaky"]))
    if summary["carried"]:
        print(f"\n  THIS RUN: {summary['run_score']}{ci_note} passed "
              f"(not a suite score — {summary['run_n']} of {summary['n']} tasks ran)"
              f"\n  latest result per task across all history: {summary['score']} "
              f"({summary['carried']} of those {summary['n']} rows are from earlier "
              f"runs of different code)"
              + skip_note + flake_note)
    elif summary["skipped"]:
        print(f"\n  score: {summary['run_score']}{ci_note} over the {summary['run_n']} "
              f"tasks that ran — NOT a full-suite score" + skip_note + flake_note)
    else:
        print(f"\n  score: {summary['run_score']}{ci_note} — full suite, every task run now"
              + flake_note)
    print(f"  (history: {paths.EVAL_RESULTS})")
    return results
