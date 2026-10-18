"""Post-loop answer shaping: grounded fallback, plan relay, execution of the
code block the model presented, and false-claim annotation.

Moved verbatim from `bee.agent.loop` — the live-eval notes are preserved with
each block. The wording here is load-bearing: small models answer the text,
so any paraphrase is a behavior change.
"""
from __future__ import annotations

import time

from .. import guard
from ..monitor import metrics
from . import policy
from .tool_dispatch import fmt_result_text


def grounded_fallback(messages: list, n_tool_calls: int) -> str:
    """What to ship when even the no-tools pass only talked about plumbing.

    The live eval did this on a 40-second task: the wrap answer was `I'm ready to
    provide the response now. Please let me know how I can assist you further with
    the available functions…`. That is a shrug after the user waited. The last
    thing a tool actually returned is real, so report that and say plainly that
    the task was not finished. Refusals, errors and loop-control notes are skipped —
    they are the harness talking, not a fact about the world, and quoting one made
    the 'honest' answer a JSON plumbing blob (plan_complex, live)."""
    last = ""
    for m in reversed(messages):
        if m.get("role") != "tool":
            continue
        c = str(m.get("content") or "").strip()
        if c and not policy.is_harness_plumbing(c):
            last = c
            break
    if last:
        return ("I ran out of steps before I could put this together. The last thing "
                "a tool actually returned was:\n\n"
                + last[:1200]
                + "\n\n(I have not combined the results — ask me again, or narrow the "
                  "question and I will run it end to end.)")
    return (f"I could not finish this in the steps I had ({n_tool_calls} tool call(s)). "
            "Nothing you asked for was computed or changed — tell me a narrower version "
            "and I will run it.")


def should_run_attached_code(task: str, final_output: str, *, ran_code: bool,
                             sub: bool, cancelled: bool) -> bool:
    """Gate for run_attached_snippet (see the block comment there)."""
    return bool(not sub and not cancelled and not ran_code and final_output
                and (policy.wants_python(task)
                     or (policy.wants_result(task)
                         and policy.first_py_fence(final_output)))
                and not policy.is_meta_ramble(final_output))


def run_attached_snippet(ctx, cfg, task: str, final_output: str, *, on_ask, emit,
                         episode, messages) -> tuple[str, int]:
    """Never ship code you did not run. Three eval tasks ask for a computation 'with a
    short Python snippet'; the 3B model returns the snippet plus prose with tools=0,
    so the number it states is its own arithmetic. Execute the block it presented —
    through the capability gate and the guard, exactly like any other tool call — and
    report the real output, or say plainly that nothing was verified.

    Returns (final_output, tool_calls_used)."""
    fm = policy.first_py_fence(final_output)
    snippet = (fm.group(1).strip() if fm else "")
    if not (8 <= len(snippet) <= 4000):
        return final_output, 0
    from ..tools import tools_by_name as _tbn
    # What the gate authorizes, the guard checks and the interpreter runs
    # must be the SAME text — otherwise a read-out appended after
    # approval would run unreviewed.
    echoed = not policy.prints_output(snippet)
    run_src = snippet + policy.VALUE_READOUT if echoed else snippet
    proceed, action, reason = True, "allow", "not needed"
    gate = getattr(ctx, "capability_gate", None)
    if gate is not None:
        g = gate.check("code_run", {"code": run_src},
                       task_id=getattr(ctx, "current_task_id", ""),
                       untrusted_context=False)
        if not g.allowed:
            proceed, action, reason = False, "capability_deny", g.reason
    if proceed and ctx.guard_on and cfg.guard.enabled:
        proceed, action, reason = guard.check("code_run", {"code": run_src}, True,
                                              ctx.guard_mode, approver=on_ask)
    if not proceed:
        metrics.record("guard", tool="code_run", action=action, reason=reason)
        final_output += ("\n\n⚠ I was not allowed to run that snippet ("
                         f"{str(reason)[:160]}), so its output above is unverified.")
        return final_output, 0
    t0 = time.time()
    bus = getattr(getattr(ctx, "kernel", None), "bus", None)
    try:
        if bus is not None:
            rv, _bd, _bk, _bm = bus.call(ctx, "code_run", {"code": run_src},
                                         stop_check=lambda: False)
        else:
            rv = _tbn()["code_run"](ctx, code=run_src)
    except Exception as e:
        rv = {"error": f"{type(e).__name__}: {e}"}
    dt = time.time() - t0
    used = 1
    rv = rv if isinstance(rv, dict) else {}
    exit_code = rv.get("exit_code")
    out = str(rv.get("output") or "").strip()
    err = str(rv.get("error") or "").strip()
    ok_run = not (rv.get("error") or rv.get("blocked"))
    emit({"type": "tool_start", "tool": "code_run", "args": {"code": run_src[:120]}})
    emit({"type": "tool_result", "tool": "code_run", "seconds": round(dt, 1),
          "ok": ok_run, "preview": (out or err)[:300]})
    if episode:
        episode.tool("code_run", {"code": run_src}, ok_run, dt, rv)
    metrics.record("tool", tool="code_run", ok=ok_run, seconds=round(dt, 2),
                   blocked=bool(rv.get("blocked")))
    messages.append({"role": "tool", "tool_call_id": "verify_shown_code",
                     "name": "code_run", "content": fmt_result_text(rv)})
    if rv.get("blocked"):
        final_output += ("\n\n⚠ I did not run the snippet, so the value above is "
                         "unverified.")
    elif not ok_run or exit_code not in (None, 0):
        final_output += ("\n\n⚠ I ran the snippet and it failed"
                         + (f" (exit {exit_code})" if exit_code not in (None, 0) else "")
                         + f": {(err or out)[:300]} — the value above is unverified.")
    else:
        # Stated as authoritative, not as a footnote: the live probe had
        # the model write 'the LCM is **308**' in prose while the snippet it
        # displayed prints 588. A user copies the confident number, so the
        # measured output has to be labelled the thing to trust.
        if echoed and not out:
            final_output += ("\n\n⚠ I ran the snippet and it neither printed "
                             "anything nor computed a value I could report — "
                             "the number above is unverified.")
        elif echoed:
            final_output += ("\n\nI ran that snippet. It printed nothing itself, "
                             "so these are the values it actually computed — "
                             "trust them over any number stated above:\n```\n"
                             + out[:800] + "\n```")
        else:
            final_output += ("\n\nI ran that snippet; this is what it actually "
                             "printed — trust it over any number stated above:\n```\n"
                             + out[:800] + "\n```")
    return final_output, used


def relay_plan(ctx, task: str, *, emit, episode) -> tuple[str, int]:
    """A45b: a plan the model narrates instead of producing. `plan_complex` asked
    for a plan "using the planner tool", the 3B model answered "I would follow
    these steps: 1. Loading…" and never called the planner — so the relay in the
    loop had nothing to relay and the answer lost the library names the planner
    does produce. The planner is risk-LOW and needs no capability, so asking it
    is not a new permission surface; it is the tool the user named.

    Returns (plan_text, tool_calls_used); plan_text is "" unless the planner
    actually answered."""
    from ..tools import tools_by_name as _tbn2
    bus2 = getattr(getattr(ctx, "kernel", None), "bus", None)
    t0p = time.time()
    try:
        if bus2 is not None:
            pv, _b1, _b2, _b3 = bus2.call(ctx, "planner", {"task": task},
                                          stop_check=lambda: False)
        else:
            pv = _tbn2()["planner"](ctx, task=task)
    except Exception as e:
        pv = {"error": f"{type(e).__name__}: {e}"}
    dtp = time.time() - t0p
    pv = pv if isinstance(pv, dict) else {}
    ptxt = str(pv.get("plan") or "").strip()
    okp = bool(ptxt) and not pv.get("error")
    emit({"type": "tool_start", "tool": "planner", "args": {"task": task[:120]}})
    emit({"type": "tool_result", "tool": "planner", "seconds": round(dtp, 1),
          "ok": okp, "preview": (ptxt or str(pv.get("error") or ""))[:300]})
    if episode:
        episode.tool("planner", {"task": task}, okp, dtp, pv)
    metrics.record("tool", tool="planner", ok=okp, seconds=round(dtp, 2), blocked=False)
    return (ptxt, 1) if okp else ("", 0)


def attach_plan(final_output: str, plan_text: str, task: str, sub: bool) -> str:
    """A plan the model paraphrases is a plan the user cannot act on. Asked to plan a
    CSV analysis with the planner tool, the reply was 'we would need to load the
    data, which may take some time' — the planner's own numbered steps named the
    libraries, and they were dropped on the way to the user."""
    if (not sub and plan_text and final_output and policy.wants_plan(task)
            and plan_text.splitlines()[0][:40] not in final_output):
        return (final_output.rstrip()
                + "\n\nPlan as produced:\n" + plan_text[:2000])
    return final_output


def annotate_unverified_claim(final_output: str, vres: dict, sub: bool) -> tuple[str, bool]:
    """A final answer that STILL asserts an action no tool performed must not be
    delivered as plain success. Verification already failed once and the model
    repeated the claim (live evidence: 'I executed git reset --hard HEAD~1'
    after 16 unrelated tool calls) — the user would read a destructive action
    into their own repository history. Say plainly that it is unverified.

    Returns (possibly annotated output, claim_fail)."""
    claim_fail = (not sub and vres.get("verdict") == "fail"
                  and any(f.get("check") == "claim" for f in vres.get("findings") or []))
    if claim_fail:
        final_output = ((final_output or "").rstrip() +
                        "\n\n⚠ I could not verify that this actually ran — no tool "
                        "result backs it up. Please treat the action as NOT done.")
    return final_output, claim_fail
