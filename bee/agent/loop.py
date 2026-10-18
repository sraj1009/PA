"""BEE core agent loop — production edition (Phase 4).

Pipeline per task:
  route — one entry: bee/agent/router.py:decide() (tier order documented
  there: deterministic → explicit → smalltalk → fast-path → ML → heuristic
  → escalate)
  → availability check (local down → cloud → offline rules)
  → RAG auto-context (grounding for dangling references)
  → think/act/observe loop with:
      - privacy redaction on cloud-bound messages (local never redacted)
      - guard gates before every execution tool
      - cancellation (Ctrl-C via ctx.cancel_event)
      - episode logging (data flywheel) + metrics (observability)
      - text tool-call recovery for small local models
  → deterministic verification with ONE bounded fix round
  → diary + metrics + result
"""
from __future__ import annotations

import json
import threading
import time

from ..config import Config
from .client import LLMClient, LLMError
from .context import Context, build_sub_system, build_system_prompt, module_api_card, compact_messages
from .result import AgentResult
from . import router as routing
from .router import strip_cloud_prefix, CLOUD_PREFIX

from .. import guard, privacy
from ..brain import rag as rag_mod
from ..brain import verifier
from ..episodes.logger import Episode
from ..monitor import metrics
from ..tools import tools_litellm, tools_by_name, tools_meta
from ..tools.base import untrusted_fence

# Extracted siblings (refactor: loop.py keeps run_agent + the AgentKernel
# contract). The aliases preserve this module's historical private names:
# reflection.py and pipeline/derive_prefs.py import _META_RAMBLE_RE; tests
# import _extract_text_tool_calls, _validate_call, _finish, _grounded_fallback.
from .answer_postprocess import (annotate_unverified_claim, attach_plan,
                                 grounded_fallback as _grounded_fallback,
                                 relay_plan, run_attached_snippet,
                                 should_run_attached_code)
from .episode_metrics import (diary as _diary, finish as _finish,
                              golden as _golden, served_cloud as _served_cloud)
from .policy import (META_RAMBLE_RE as _META_RAMBLE_RE,  # noqa: F401  (re-export)
                     asks_about_tools, is_meta_ramble, narrates_tool_call,
                     wants_plan)
from .tool_dispatch import (audit_record as _audit_record,
                            execute_tool as _execute_tool,
                            extract_text_tool_calls as _extract_text_tool_calls,
                            fmt_result_text as _fmt_result_text,
                            iter_json_blocks as _iter_json_blocks,
                            run_fastpath as _run_fastpath,
                            safe_args as _safe_args,
                            validate_call as _validate_call)

MAX_VERIFY_FIXES = 1


def _cloud_up(cfg) -> bool:
    """Cloud tier is usable only if enabled, configured AND credentialed.

    Availability comes from the ProviderRegistry (agent/providers.py) — the
    real configured provider is checked, never a hard-coded key list. An
    enabled cloud with no matching key would 401 on every call and drag the
    whole fallback chain into auth errors — treated as down so tasks stay on
    local (or drop to offline rules) instead.
    """
    from . import providers
    ok, _reason = providers.cloud_available(cfg)
    return ok


# --------------------------------------------------------------- helpers
def _redact_for_cloud(msgs: list[dict]) -> tuple[list[dict], int]:
    total = 0
    out = []
    for m in msgs:
        mm = dict(m)
        c = mm.get("content")
        if isinstance(c, str) and c:
            c2, n = privacy.redact(c)
            total += n
            mm["content"] = c2
        out.append(mm)
    return out, total


def _offline_result(task: str, workspace) -> AgentResult:
    from .offline import run_offline
    out = run_offline(task, workspace)
    metrics.record("offline", task=task[:200])
    return AgentResult(output=out, model="offline-rules", ok=True, route_source="offline")


# ----------------------------------------------------------------- main
def run_agent(ctx: Context, task: str, on_event=None, model: str | None = None,
              max_iters: int = 25, system: str | None = None, sub: bool = False,
              on_ask=None, on_token=None, route_text: str | None = None) -> AgentResult:
    # on_ask (Phase 2): kernel-injected permission approver (tool, args, reason)->bool,
    # consulted when the guard says 'ask'. None = guard's built-in mode approver.
    # on_token (Phase 4): when set, LLM completions use chat_stream and every
    # content delta is emitted as {"type": "token", "text": ...} — genuine
    # provider streaming (Ollama NDJSON / litellm chunks), not post-hoc splits.
    cfg: Config = ctx.cfg
    if ctx.client is None:
        ctx.client = LLMClient(cfg)
    raw = (task or "").strip()
    cloud_prefix = bool(CLOUD_PREFIX.search(raw))  # per-task explicit intent
    task = strip_cloud_prefix(raw).strip()
    if not task:
        return AgentResult(output="No task given.", ok=False, error="empty task")
    # `said` is what the USER typed; `task` may carry the kernel's session
    # context block prepended for the model. The instant tiers (deterministic
    # math, smalltalk, the 39 fast paths) must judge the raw utterance: they are
    # anchored to whole strings, so a context prefix used to disqualify bare
    # follow-ups like "1234 + 5678" or "open chrome" — turning a 0 ms answer into
    # a paid LLM round-trip (and, for math, an unverified one).
    said = strip_cloud_prefix((route_text or "").strip()).strip() or task
    if model is None:
        model = ctx.model_override  # session engine choice (set at launch / /engine / UI)
    if cloud_prefix:
        model = "cloud"  # typed 'cloud:' always wins over the session engine

    ev_cancel = ctx.cancel_event if isinstance(ctx.cancel_event, threading.Event) else threading.Event()
    start = time.time()

    def emit(ev: dict):
        if on_event:
            try:
                on_event(ev)
            except Exception:
                pass

    # ------------------------------------------------------------- routing
    rinfo = routing.decide(said, cfg, model)
    name, escalated = rinfo["name"], rinfo["escalated"]
    metrics.record("route", task=said[:200], route=name, source=rinfo.get("source"),
                   escalated=escalated, conf=rinfo.get("conf"))
    emit({"type": "route", "model": name, "escalated": escalated, "source": rinfo.get("source")})

    # --------------------------------------- hybrid speed tier (cloud-first)
    # Session engine = hybrid (model is None) and the router picked local:
    # send conversational work to the fast cloud model instead — zero local
    # RAM/VRAM load on this box. Explicit local hints, other session engines,
    # and det/smalltalk routes are untouched. Cloud failures de-escalate back
    # to local (below) so nothing is lost when offline.
    if (model is None and name == "local" and rinfo.get("source") != "explicit"
            and getattr(cfg.cloud, "cloud_first", True) and _cloud_up(cfg) and not sub):
        emit({"type": "engine", "model": "cloud",
              "reason": "hybrid cloud-first (fast + memory saver)"})
        name, escalated = "cloud", False
        metrics.record("route", task=said[:200], route="cloud", source="hybrid-speed",
                       escalated=False)
        emit({"type": "route", "model": "cloud", "escalated": False, "source": "hybrid-speed"})

    episode = Episode(said, model=name) if (not sub and ctx.episodes_on) else None

    # ------------------------------------------------- tier 0: deterministic
    if name == "det":
        from ..tools.base import eval_safe
        expr = rinfo.get("expr") or said.replace("^", "**")
        try:
            shown = expr if expr != said.strip() else said.strip()
            ans, ok, err = f"{shown} = {eval_safe(expr)}", True, ""
        except Exception as e:
            ans, ok, err = f"Could not evaluate deterministically: {e}", False, str(e)
        res = AgentResult(output=ans, model="deterministic", ok=ok, error=err,
                          verify="pass", route_source="deterministic")
        return _finish(ctx, said, episode, res, start, emit, sub)

    # ------------------------------------------ tier 0: smalltalk (instant reply)
    if name == "smalltalk":
        res = AgentResult(output=rinfo.get("smalltalk_reply") or "Ready. What do you need done?",
                          model="deterministic", ok=True, verify="pass", route_source="deterministic")
        return _finish(ctx, said, episode, res, start, emit, sub)

    # ------------------------------ tier 3: fast paths (matched in decide())
    # Pure Python, no LLM. decide() applies the gates: explicit model hints
    # ('cloud: ...' / 'local: ...') win over fast paths, and det/smalltalk
    # tasks never reach here (they returned above).
    hit = rinfo.get("fastpath")
    if hit is not None:
        done = _run_fastpath(ctx, cfg, said, hit[0], hit[1], episode, start, emit, sub,
                             on_ask=on_ask)
        if done is not None:
            return done

    # ------------------------------------------------- availability / fallback chain
    local_up = ctx.client.ollama_up()      # public provider API (Phase 6)
    if not local_up:
        # A launch started at boot may still be in flight (A60): give the server the
        # second it needs instead of degrading the task because the probe raced it.
        # Returns instantly when BEE never attempted a launch.
        from . import localserver
        local_up = localserver.grace(cfg)
    cloud_up = _cloud_up(cfg)
    if name == "local" and not local_up:
        if cloud_up:
            name, escalated = "cloud", True
            metrics.record("route", task=task[:200], route="cloud", source="fallback", escalated=True)
            emit({"type": "escalate", "reason": "local offline → cloud"})
            emit({"type": "route", "model": name, "escalated": True, "source": "fallback"})
        else:
            res = _offline_result(task, ctx.workspace)
            return _finish(ctx, task, episode, res, start, emit, sub)
    if name == "cloud" and not cloud_up:
        if local_up:
            name, escalated = "local", False
            emit({"type": "route", "model": name, "escalated": False, "source": "fallback"})
        else:
            res = _offline_result(task, ctx.workspace)
            res.error = "cloud not configured, local offline — deterministic mode"
            res.ok = False
            return _finish(ctx, task, episode, res, start, emit, sub)

    # ------------------------------------ P1: plan-first execution
    # The planner used to run only when the user explicitly asked for a plan —
    # post-hoc, as a rescue for dropped prose (A45b). Now every multi-step task
    # (and every plan request) gets an explicit, tool-grounded plan BEFORE the
    # loop starts, injected into the working context: the 3B executes a numbered
    # step list far better than it re-invents the plan mid-task, and a plan-only
    # request no longer depends on the model remembering to call the tool.
    # Deterministic tiers returned above, so nothing instant pays for this; the
    # real-client gate keeps scripted tests on an untouched call sequence (the
    # same rule as critique/reflection).
    plan_text = ""
    plan_tool_calls = 0
    if (not sub and local_up and not ev_cancel.is_set()
            and getattr(getattr(cfg, "learning", None), "plan_first", True)):
        _pf_kind = ""
        try:
            from ..kernel import planner as _kplanner
            _pf_kind = _kplanner.classify_intent(said)[0]
        except Exception:
            _pf_kind = ""
        if ((_pf_kind == "multi_step" or wants_plan(said))
                and _pf_kind not in ("informational", "impossible", "ambiguous")):
            from .client import LLMClient as _LLMClient
            if isinstance(ctx.client, _LLMClient):
                _pf_t0 = time.time()
                try:
                    bus2 = getattr(getattr(ctx, "kernel", None), "bus", None)
                    if bus2 is not None:
                        pv, _b1, _b2, _b3 = bus2.call(ctx, "planner", {"task": task},
                                                      stop_check=ev_cancel.is_set)
                    else:
                        from ..tools import tools_by_name as _tbn_pf
                        pv = _tbn_pf()["planner"](ctx, task=task)
                except Exception as e:
                    pv = {"error": f"{type(e).__name__}: {e}"}
                _pf_dt = time.time() - _pf_t0
                pv = pv if isinstance(pv, dict) else {}
                ptxt = str(pv.get("plan") or "").strip()
                okp = bool(ptxt) and not pv.get("error")
                emit({"type": "tool_start", "tool": "planner",
                      "args": {"task": task[:120]}})
                emit({"type": "tool_result", "tool": "planner",
                      "seconds": round(_pf_dt, 1), "ok": okp,
                      "preview": (ptxt or str(pv.get("error") or ""))[:300]})
                if episode:
                    episode.tool("planner", {"task": task}, okp, _pf_dt, pv)
                metrics.record("tool", tool="planner", ok=okp,
                               seconds=round(_pf_dt, 2), blocked=False)
                if okp:
                    plan_text = ptxt
                    plan_tool_calls = 1

    # ------------------------------------------------- messages + RAG
    system = system if system is not None else (build_sub_system(ctx) if sub else build_system_prompt(ctx))
    user_content = task
    if not sub and ctx.rag_on and cfg.rag.auto_context:
        try:
            mc = rag_mod.auto_context(ctx, task, k=cfg.rag.k)
            if mc:
                user_content = f"{task}\n\n{mc}"
        except Exception:
            pass
    if not sub:
        card = module_api_card(task)
        if card:
            user_content = f"{user_content}\n\n{card}"
    if plan_text:
        if wants_plan(said):
            # the user asked for a PLAN — the plan is the deliverable; the
            # injection must not read as an instruction to run it (live probe:
            # the 3B started executing a plan-only request once handed steps).
            _pf_note = ("[plan-first] A plan produced by the planner tool BEFORE "
                        "this step. The user asked for a plan: present it "
                        "(corrected or improved if you see a problem) as the "
                        "answer. Do NOT execute the steps unless the user also "
                        "asked for execution.")
        else:
            _pf_note = ("[plan-first] A plan produced by the planner tool BEFORE "
                        "execution. Treat it as a starting point: execute the "
                        "user's request following these steps where they fit, and "
                        "replace a step if the evidence contradicts it.")
        user_content = f"{user_content}\n\n{_pf_note}\n{plan_text[:1500]}"
    messages: list[dict] = [{"role": "system", "content": system}, {"role": "user", "content": user_content}]
    tools = None if sub else tools_litellm()
    # P0-1: the local route gets the fitted schema subset — num_ctx 8192 cannot
    # afford all 30 schemas (~5.2k est tokens) plus a conversation; cloud keeps
    # the full set. The executor registry below stays complete either way.
    tools_local = None if sub else tools_litellm(local=True)
    registry = tools_by_name() if tools else {}
    meta = tools_meta() if tools else {}

    def tools_for(info: dict) -> list | None:
        """Schemas for one call: full for cloud, fitted subset for local."""
        if tools is None:
            return None
        return tools if info.get("cloud") else tools_local

    def llm_call(cur_name: str):
        # A59/A60: Ollama silently truncates to ~num_ctx/2 when the prompt does not
        # fit. Compact old tool history *before* the call so the model at least keeps
        # the most recent context, and so the truncation is logged rather than hidden.
        info = cfg.get_llm(cur_name)
        cur_tools = tools_for(info)
        if not info.get("cloud") and cfg.ollama.num_ctx:
            compacted, compact_info = compact_messages(messages, cur_tools, cfg.ollama.num_ctx,
                                                        completion_reserve=cfg.ollama.max_tokens)
            if compacted is not messages:
                messages[:] = compacted
            if compact_info.get("compacted"):
                metrics.record("context_compact", model=cur_name, **compact_info)
                emit({"type": "context_compact", **compact_info})
        if info.get("cloud") and cfg.privacy.redact_cloud and ctx.privacy_on:
            msgs, n = _redact_for_cloud(messages)
            if n:
                metrics.record("redact", n=n, model=cur_name)
                emit({"type": "redact", "n": n})
        else:
            msgs = messages
        # structured LLM telemetry: per-call latency + provider failures
        # (kind: auth/quota/network/timeout/server) — observability, audit 2026-10-06
        t0 = time.time()
        streaming = on_token is not None
        try:
            if streaming:
                try:
                    out = ctx.client.chat_stream(cur_name, msgs,
                                                 on_token=lambda t: emit({"type": "token", "text": t}),
                                                 tools=cur_tools)
                except LLMError:
                    out = ctx.client.chat(cur_name, msgs, tools=cur_tools)  # one fallback
            else:
                out = ctx.client.chat(cur_name, msgs, tools=cur_tools)
            usage = (out or {}).get("usage") or {}
            metrics.record("llm", model=cur_name, seconds=round(time.time() - t0, 2),
                           ok=True, stream=streaming,
                           tokens=int(usage.get("prompt", 0)) + int(usage.get("completion", 0)))
            return out
        except LLMError as e:
            metrics.record("llm", model=cur_name, seconds=round(time.time() - t0, 2),
                           ok=False, stream=streaming,
                           error_kind=getattr(e, "kind", "server"))
            raise

    iters = 0
    n_tool_calls = plan_tool_calls   # the plan-first planner call is a real tool call
    tokens = 0
    sub_results: list[str] = []
    verify_rounds = 0
    rejected_drafts: list[str] = []  # verify-FAILed drafts, for preference pairs
    vres = {"verdict": "pass", "findings": []}
    cancelled = False
    final_output = ""
    # circuit breaker: a (tool, args) pair that fails twice is not executed a
    # third time - small models otherwise loop on dead endpoints for 20 calls
    fail_streak: dict = {}
    # how many times an already-cached call has been re-requested (see the repeat
    # breaker below)
    repeats: dict = {}
    # Per-tool DENIAL breaker (eval evidence: a 3B model re-requested the same
    # denied capability 6x with slightly different arguments — the exact-args
    # breakers above key on the argument tuple, so they never matched and 12 of
    # 25 iterations went to calls that could not possibly run).
    denials: dict = {}
    blocked_streak = 0
    tools_locked = False
    # Same idea for FAILING tools: a model that retries one failing call with
    # reworded arguments sidesteps the exact-args breaker too (observed: 12
    # memory_search rounds). Errors are counted per tool and cleared by any
    # success, so legitimate multi-file / multi-step work is never punished.
    failures: dict = {}
    # Per-tool CALL budget, independent of outcome. The exact-args and per-tool
    # failure breakers both key on something the 3B model varies: the last live run
    # spent 48 tool calls on dsa_gcd_lcm and 15 on file_roundtrip by editing one
    # character of the snippet between attempts — every call was 'new', none ever
    # returned a transport error, so nothing stopped it. Six calls of one tool in a
    # single task is plenty of evidence that the model is looping.
    attempts: dict = {}
    TOOL_ATTEMPT_CAP = 6
    # plan_text was filled by the plan-first block (P1) before the loop; it is
    # kept so the user can be given the planner's own numbered steps rather than
    # the model's vague paraphrase of them.
    # did any Python actually run in this task? decides whether the answer's own
    # code block has to be executed to be worth anything
    ran_code = False
    untrusted_active = False    # audit item 5: untrusted content ingested this turn
    # repeat-call guard: identical (tool, args) calls after the first return the
    # cached result + a nudge to finish (3B models re-issue the same search 5x)
    seen_calls: dict = {}
    # empty-completion retry: small models occasionally return a blank reply —
    # one explicit nudge converts that into an answer instead of "(no output)"
    empty_retries = 0
    empty_final = False        # the model never produced text: an unfinished task (A46)
    narration_nudged = False   # model described a call instead of making it
    force_wrap = False         # last text was meta-commentary: a no-tools pass must answer
    loop_closed = False        # model re-requested a refused call; tools are done

    def _wrap_text(kind: str) -> str:
        # The old wording was entirely about the budget ("your tool-call budget is
        # exhausted, do not call any tools"), and a 3B model answered THAT instead
        # of the user: seven eval tasks ended as "It seems like there might have
        # been an error… no function calls were provided for execution". So the
        # nudge restates the request and forbids meta-commentary explicitly.
        return (f"{kind}\n\nThe user's request was:\n{(task or '')[:600]}\n\n"
                "Answer that request now, in plain language, using only what is "
                "already in this conversation. Do not mention tools, functions, "
                "permissions, or your budget — the user cannot see those. If you "
                "could not confirm something, say what you found and what you did "
                "not verify.")

    _WRAP = _wrap_text("WRAP UP: stop calling tools and give your final answer now.")
    for it in range(max_iters):
        if ev_cancel.is_set():
            cancelled = True
            break
        iters = it + 1
        # wrap-up nudge: in the last 2 iterations, force the final answer —
        # small models (3B) otherwise burn the whole budget on tool calls
        if (it >= max_iters - 2 and n_tool_calls > 0
                and (not messages or messages[-1].get("content") != _WRAP)):
            messages.append({"role": "user", "content": _WRAP})
        try:
            out = llm_call(name)
        except LLMError as e:
            kind = getattr(e, "kind", "server")
            if kind == "connect" and name == "local" and cloud_up and not escalated:
                emit({"type": "escalate", "reason": f"local unreachable ({str(e)[:100]}) → cloud"})
                name, escalated = "cloud", True
                metrics.record("route", task=task[:200], route="cloud", source="fallback", escalated=True)
                emit({"type": "route", "model": name, "escalated": True, "source": "fallback"})
                continue
            if kind == "connect" and name == "cloud" and not local_up and not sub:
                res = _offline_result(task, ctx.workspace)
                res.ok = False
                res.error = f"cloud unreachable ({str(e)[:100]}), local offline — deterministic mode"
                return _finish(ctx, task, episode, res, start, emit, sub)
            # de-escalation: cloud failed (quota 429 / rate limit / server) and
            # the local model is reachable -> take it (slower, but the answer
            # lands). Covers router AND hybrid cloud_first routes; an explicit
            # `cloud:` task (model set) keeps retry-then-error behavior.
            if name == "cloud" and model is None and local_up and not sub:
                emit({"type": "deescalate", "reason": f"cloud failed ({str(e)[:80]}) → local"})
                name, escalated = "local", False
                metrics.record("route", task=task[:200], route="local",
                               source="deescalation", escalated=False)
                emit({"type": "route", "model": "local", "escalated": False, "source": "deescalation"})
                continue
            if not escalated and cfg.cloud.enabled and cfg.cloud.llm:
                emit({"type": "escalate", "reason": str(e)[:200]})
                messages = [
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"{task}\n\n(Note: previous model failed with: {str(e)[:150]}. Complete the task fully now.)"},
                ]
                name, escalated = "cloud", True
                metrics.record("route", task=task[:200], route="cloud", source="escalation", escalated=True)
                emit({"type": "route", "model": name, "escalated": True, "source": "escalation"})
                continue
            return _finish(ctx, task, episode, AgentResult(output="", model=name, iterations=iters,
                              escalated=escalated, tool_calls=n_tool_calls, est_tokens=tokens,
                              ok=False, error=f"LLM error: {e}"), start, emit, sub)
        except KeyboardInterrupt:
            ev_cancel.set()
            cancelled = True
            break

        content = out.get("content")
        tcs = out.get("tool_calls") or []
        if not tcs and tools:
            tcs = _extract_text_tool_calls(content or "")
        tokens += int((out.get("usage") or {}).get("prompt", 0)) + int((out.get("usage") or {}).get("completion", 0))

        if not tcs:
            txt = (content or "").strip()
            if txt and not sub and not narration_nudged and narrates_tool_call(txt):
                # "I will use a computer_command function call to run git reset…"
                # is not an answer and not a call — the eval evidence shows the loop
                # shipping exactly this. One bounded nudge converts it into either.
                narration_nudged = True
                messages.append({"role": "assistant", "content": txt})
                messages.append({"role": "user", "content":
                    "You described an action instead of performing it. Do not describe or "
                    "name functions or tools. Either make the call now, or answer the "
                    f"request directly from what you already know.\n\nRequest:\n{task[:600]}"})
                continue
            if (txt and not sub and not force_wrap and tools
                    and not asks_about_tools(task)
                    and is_meta_ramble(txt)):
                # The reply is about the plumbing, not the task. Never ship that:
                # force the no-tools final-answer pass (below) with the request
                # restated.
                force_wrap = True
                messages.append({"role": "assistant", "content": txt})
                messages.append({"role": "user", "content": _WRAP})
                continue
            if not (content or "").strip() and empty_retries < 1:
                empty_retries += 1
                messages.append({"role": "user", "content":
                    "Your previous reply was empty. Give your final answer now in plain text "
                    "(call a tool only if you still truly need one)."})
                continue
            # A46: after the one retry an EMPTY answer used to be delivered as the
            # literal string "(no output)" with ok=True, and the verifier — whose
            # three checks all key off events that happened — passed it (live eval
            # `file_roundtrip`: 40.7 s, verify=pass, output "(no output)"). The user
            # gets a bracketed nothing and the receipts claim success. Ship what
            # actually happened instead, and say it did not finish.
            empty_final = not (content or "").strip()
            if empty_final:
                final_output = _grounded_fallback(messages, n_tool_calls)
            else:
                final_output = (content or "").strip()
            if not sub and not empty_final:
                # Self-critique (local Chain-of-Thought Verification): one
                # bounded local pass over the draft for recomputed math,
                # missed constraints, invented details, and clarity — before
                # the deterministic verifier and before the user sees it.
                try:
                    from . import critique as _critique
                    if _critique.should_critique(ctx, task, final_output):
                        draft_pre = final_output
                        final_output = _critique.critique_answer(
                            ctx, final_output, task, emit)
                        # Pair only when LOCAL served the task: the critique pass
                        # itself is a local call, so for a cloud-served draft it
                        # would record "prefer the 3B's rewrite over the cloud
                        # answer" — the wrong direction for teaching bee4b.
                        if (name == "local"
                                and final_output.strip() != draft_pre.strip()):
                            # The critique rewrote the draft: a free preference
                            # pair (chosen=rewrite, rejected=draft) — the RLAIF
                            # corpus must not wait for hand-typed /correct.
                            from ..memory import ratings as _ratings
                            _ratings.record_pair(said, final_output, draft_pre,
                                                 source="critique", model=name)
                except Exception:
                    pass  # critique must never break the main flow
            if not sub:
                try:
                    vres = verifier.verify(task, final_output, ctx.workspace,
                                           episode.events if episode else [])
                    metrics.record("verify", verdict=vres["verdict"], findings=vres["findings"][:4])
                    emit({"type": "verify", **vres})
                except Exception:
                    vres = {"verdict": "warn", "findings": [{"check": "verifier", "detail": "verifier error"}]}
            if vres["verdict"] == "fail" and verify_rounds < MAX_VERIFY_FIXES and not sub:
                verify_rounds += 1
                # Never name the mechanism. This text used to open with an ALL-CAPS
                # status code followed by a dump of internal check names; the 3B model
                # made that phrase its SUBJECT and answered about function calls and
                # JSON formatting instead of the request (live eval `guard_blocked`,
                # 2026-10-10: tools=0, "To properly address the issue of
                # SELF-VERIFICATION_FAILED, we need to ensure that each function call
                # is correctly formatted with all required arguments included within a
                # JSON object…"). Plain words, and the request restated — the same
                # remedy the narration nudge above already uses.
                problems = "; ".join(
                    str(f.get("detail") or f.get("check") or "")
                    for f in vres["findings"])[:400].strip()
                if len(rejected_drafts) < 3:
                    rejected_drafts.append(final_output)
                messages.append({"role": "assistant", "content": final_output})
                messages.append({"role": "user", "content":
                    "What you just wrote describes something that did not happen. "
                    + (f"Here is what actually went wrong: {problems}. " if problems else
                       "Nothing in it is backed by a result you actually received. ")
                    + "Rewrite the answer using only what the results above show; if a "
                    "part could not be done, say that plainly. Do not talk about tools, "
                    f"checks or this message.\n\nRequest:\n{task[:600]}"})
                continue
            # A verifier-FAILED draft that the loop then fixed is a free
            # preference pair (chosen=shipped fix, rejected=the draft the
            # verifier caught) — machine-derived RLAIF (P0-4, 2026-10-17).
            if rejected_drafts and vres.get("verdict") != "fail" and (final_output or "").strip():
                try:
                    from ..memory import ratings as _ratings
                    for bad in rejected_drafts:
                        if (bad or "").strip() and bad.strip() != final_output.strip():
                            _ratings.record_pair(said, final_output, bad,
                                                 source="verify-fix", model=name)
                except Exception:
                    pass
            break

        # ------------------------------------------------------------ tool calls
        messages.append({"role": "assistant", "content": content or "", "tool_calls": [
            {"id": tc.get("id") or f"call_{n_tool_calls + i}", "type": "function",
             "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"])}}
            for i, tc in enumerate(tcs)
        ]})
        for i, tc in enumerate(tcs):
            if ev_cancel.is_set():
                cancelled = True
                break
            tname = tc["name"]
            args = _safe_args(tc.get("arguments"))
            n_tool_calls += 1
            emit({"type": "tool_start", "tool": tname, "args": args})
            t0 = time.time()
            res_v = None
            executed = False
            action = "allow"
            # Per-tool denial breaker, deliberately BEFORE the gate: a tool that
            # has already been refused twice in this task must not be re-consulted
            # (eval evidence: a 3B model asked for automation.manage 6x with
            # slightly different args, so the exact-args breakers never matched
            # and 12 of 25 iterations went to calls that could not run).
            if tools_locked:
                res_v = {"blocked": True,
                         "reason": "Too many actions were refused for this task; no more tools "
                                   "will run now. Give your complete final answer with what you "
                                   "already have, and state plainly what you could not do."}
                action = "lock"
            elif denials.get(tname, 0) >= 2:
                res_v = {"blocked": True,
                         "reason": f"{tname} was refused {denials[tname]}x in this task - stop "
                                   "calling it. Answer with what you have, or name the permission "
                                   "you need so the user can grant it."}
                action = "lock"
            elif failures.get(tname, 0) >= 3:
                res_v = {"blocked": True,
                         "reason": f"{tname} has failed {failures[tname]}x in this task - do not "
                                   "call it again. Report the failure and answer with what you "
                                   "already have."}
                action = "lock"
            elif attempts.get(tname, 0) >= TOOL_ATTEMPT_CAP:
                # Soft first, hard later: a nudge that does not execute and does not
                # count as a refusal (a legitimate 25-step task can call one tool six
                # times), but a model that ignores twelve of them is looping.
                if attempts[tname] >= TOOL_ATTEMPT_CAP * 2:
                    res_v = {"blocked": True,
                             "reason": f"{tname} was already called {attempts[tname]}x in this task. "
                                       "Further calls will not help: write your final answer now from "
                                       "the results you already have, and say plainly what is missing."}
                    action = "lock"
                else:
                    res_v = {"note": f"{tname} has been called {attempts[tname]}x in this task and "
                                     "was not run again. Stop looping on it: give your final answer "
                                     "from the results you already have, or say what is missing."}
            # Mechanical validation BEFORE the gate: unknown names and
            # missing required args are rejected here with a repair nudge, so
            # malformed calls cannot burn permission breakers or iterations.
            # Shaped as an error (like unknown-tool below): fail_streak counts
            # it, denial/failure breakers do not confuse it with a refusal.
            if res_v is None and tools:
                _bad = _validate_call(tname, args, meta)
                if _bad:
                    res_v = {"error": _bad}
            # Phase 3: capability gate — authorization is checked BEFORE
            # execution. Kernel-injected (ctx.capability_gate); legacy direct
            # run_agent paths without a kernel skip it. A denial feeds the
            # same blocked-result flow as the guard, so audit/episode/telemetry
            # and the model's 'explain the refusal' behavior all work.            # Phase 12 (N1 CRITICAL): the gate is the kernel's authorization
            # layer and MUST run even when the user toggles the interactive
            # command guard off (`/guard off`) — a REPL convenience flag can
            # never bypass capability authorization. The legacy command
            # guard below (line 605) is the one thing `guard_on` controls.
            if res_v is None and getattr(ctx, "capability_gate", None) is not None:
                gate_res = ctx.capability_gate.check(tname, args,
                                                     task_id=getattr(ctx, "current_task_id", ""),
                                                     untrusted_context=untrusted_active)
                if not gate_res.allowed:
                    action = "capability_deny"
                    emit({"type": "guard", "tool": tname, "action": "deny",
                          "reason": f"capability {gate_res.capability_id}: {gate_res.reason}"})
                    res_v = {"blocked": True,
                             "reason": (f"capability {gate_res.capability_id}: {gate_res.reason}. "
                                        f"Explain what you cannot do and why; do not retry the "
                                        f"same action.")}
            if res_v is None and tname in guard.EXEC_TOOLS and ctx.guard_on and cfg.guard.enabled:
                proceed, action, reason = guard.check(tname, args, True, ctx.guard_mode,
                                                      approver=on_ask)
                metrics.record("guard", tool=tname, action=action, reason=reason)
                emit({"type": "guard", "tool": tname, "action": action, "reason": reason})
                if not proceed:
                    res_v = {"blocked": True,
                             "reason": f"guard ({reason}): command not executed. Explain the risk to the "
                                       f"user and ask for approval, or choose a safer alternative."}
            if res_v is None:
                fkey = (tname, json.dumps(args, sort_keys=True, default=str))
                if tname in registry and fkey in seen_calls:
                    repeats[fkey] = repeats.get(fkey, 0) + 1
                    if repeats[fkey] >= 2:
                        # Live evidence (plan_complex): the model was told 'Do NOT run it
                        # again - use the cached result' and asked for the SAME call 21
                        # more times. Each repeat was served as a SUCCESS, so no breaker
                        # counted it and 21 of 24 iterations went to requests that could
                        # not add anything. A third identical ask is not a question, it is
                        # a loop: close the tools and make the model answer.
                        tools_locked = True
                        loop_closed = True
                        res_v = {"blocked": True,
                                 "reason": "This exact call was already made and you were "
                                           "told not to repeat it. Tools are closed for the "
                                           "rest of this task: write your complete final "
                                           "answer now from the results you already have."}
                        action = "lock"
                    else:
                        res_v = {"note": "You already ran this exact call earlier in this task. Do NOT run it "
                                         "again - use the cached result below and give your final answer now.",
                                 "cached_result": seen_calls[fkey]}
                elif fail_streak.get(fkey, 0) >= 2:
                    res_v = {"error": f"{tname} has already failed 2x with these exact arguments - "
                                      f"do NOT retry this call. Report the failure to the user and try "
                                      f"a different tool/approach, or answer without it."}
                elif tname in registry:
                    executed = True
                    attempts[tname] = attempts.get(tname, 0) + 1
                    # Acceptance audit P1-1: the ToolBus IS the execution
                    # dispatcher — one dispatch point, pre-call cancel check
                    # (stop_check), unified unknown-tool / malformed-args
                    # errors, and the bus's per-tool metadata. Legacy
                    # kernel-less direct run_agent falls back to the registry
                    # (identical handler set). Full contract:
                    # tool_dispatch.execute_tool.
                    res_v, _cancelled_call = _execute_tool(
                        ctx, tname, args, registry, ev_cancel.is_set)
                    if _cancelled_call:
                        ev_cancel.set()
                        cancelled = True
                        break
                    if isinstance(res_v, dict) and (res_v.get("error") or res_v.get("blocked")):
                        fail_streak[fkey] = fail_streak.get(fkey, 0) + 1
                    else:
                        fail_streak.pop(fkey, None)
                else:
                    res_v = {"error": f"unknown tool: {tname}. Available: {', '.join(sorted(registry))}"}
                    fail_streak[fkey] = fail_streak.get(fkey, 0) + 1
                    executed = False
            dt = time.time() - t0
            ok_flag = not (isinstance(res_v, dict) and (res_v.get("error") or res_v.get("blocked")))
            if isinstance(res_v, dict) and res_v.get("blocked"):
                denials[tname] = denials.get(tname, 0) + 1
                blocked_streak += 1
                if blocked_streak >= 3:
                    # three refusals in a row = the model cannot progress with
                    # tools on this task; lock so the rest of the budget goes to
                    # producing an honest answer instead of more denied calls
                    tools_locked = True
                    # A48: locking alone did not end the waste. Every later
                    # iteration still paid a full local-model round-trip to be
                    # handed another blocked note (live eval `file_roundtrip`:
                    # 25 iterations, 28 refused calls, 40.7 s to reach the answer
                    # it could have given at call 4). Reusing the repeat-abuse
                    # exit makes the lock a real stop, not a polite suggestion.
                    loop_closed = True
            elif isinstance(res_v, dict) and res_v.get("error"):
                failures[tname] = failures.get(tname, 0) + 1
            elif isinstance(res_v, dict) and res_v.get("exit_code") not in (None, 0):
                # A command that ran and returned a traceback / 'command not found'
                # is a FAILURE the model must be stopped from retrying, but the
                # transport succeeded, so ok_flag (and therefore the action receipt
                # the verifier trusts) stays True. Counting only `error` payloads
                # let a 3B model re-run broken code 48 times in one task.
                failures[tname] = failures.get(tname, 0) + 1
            elif ok_flag:
                blocked_streak = 0
                failures.pop(tname, None)
            _audit_record(tname, args, action, ok_flag, dt,
                          blocked=bool(isinstance(res_v, dict) and res_v.get("blocked")))
            if episode:
                episode.tool(tname, args, ok_flag, dt, res_v)
            metrics.record("tool", tool=tname, ok=ok_flag, seconds=round(dt, 2),
                           blocked=bool(isinstance(res_v, dict) and res_v.get("blocked")))
            if tname == "planner" and ok_flag and isinstance(res_v, dict):
                # Only when this result actually carries a plan: a repeat of the same
                # planner call is served the cached-note dict, whose .get('plan') is
                # empty, and that overwrote the real plan with '' — so the relay below
                # had nothing to show even though the planner had answered.
                p = str(res_v.get("plan") or "").strip()
                if p:
                    plan_text = p
            if (tname == "code_run" and ok_flag and isinstance(res_v, dict)
                    and res_v.get("exit_code") in (0, None)):
                ran_code = True
            text = _fmt_result_text(res_v)
            # prompt-injection boundary (audit item 5): external web content
            # is DATA, never instructions. (a) sentinel-wrap the model's view,
            # (b) mark the turn untrusted so the capability gate ESCALATES
            # state-changing actions proposed from here on, and (c) revoke
            # task-scoped capability grants issued BEFORE this ingestion — a
            # pre-injection approval must not cover post-injection actions.
            tm = meta.get(tname)
            if (tm is not None and getattr(tm, "untrusted_output", False)
                    and not (isinstance(res_v, dict) and res_v.get("error"))):
                if not (isinstance(res_v, dict) and res_v.get("untrusted")):
                    text = untrusted_fence(text, tname)
                untrusted_active = True
                gate = getattr(ctx, "capability_gate", None)
                if gate is not None:
                    try:
                        gate.store.end_task(getattr(ctx, "current_task_id", "") or "")
                    except Exception:
                        pass
            if executed:
                seen_calls[fkey] = text[:2000]
            if tname == "spawn_task" and isinstance(res_v, str):
                sub_results.append(res_v[:500])
            emit({"type": "tool_result", "tool": tname, "seconds": round(dt, 1),
                  "ok": ok_flag, "preview": text[:300]})
            messages.append({"role": "tool", "tool_call_id": tc.get("id") or f"call_{n_tool_calls}",
                             "name": tname, "content": text})
            if loop_closed:
                break
        if loop_closed:
            # The model kept asking for a call it had already been refused twice.
            # Another round-trip cannot add anything; fall straight through to the
            # no-tools answer pass below.
            break

    if cancelled:
        return _finish(ctx, task, episode, AgentResult(
            output="(stopped: cancelled by user)", model=name, iterations=iters,
            escalated=escalated, tool_calls=n_tool_calls, est_tokens=tokens,
            ok=False, error="cancelled"), start, emit, sub)

    wrapped = False
    # Two ways to end up with nothing but a complaint about plumbing: the budget
    # ran out, or the answer we are about to ship IS the plumbing talk. Either
    # way, one tools-disabled pass with the request restated is the difference
    # between an answer and a shrug. (It used to require n_tool_calls > 0, so the
    # common 3B failure — narrating a call, never making one — skipped it.)
    if (not cancelled and not sub
            and (iters >= max_iters or loop_closed
                 or (is_meta_ramble(final_output)
                     and not asks_about_tools(task)))):
        # tool budget exhausted: small models (3B) burn it all on tool calls and
        # end on an empty assistant message -> force ONE final-answer pass with
        # tools disabled; that answer becomes the task result
        try:
            messages.append({"role": "user", "content":
                _wrap_text("STOP: you are out of tool calls and the task is ending. "
                           "Do not call any tools.")})
            out = ctx.client.chat(name, messages, tools=None)
            fin = (out.get("content") or "").strip()
            if fin:
                final_output = fin
                wrapped = True
                tokens += int((out.get("usage") or {}).get("prompt", 0)) + \
                    int((out.get("usage") or {}).get("completion", 0))
                try:
                    vres = verifier.verify(task, final_output, ctx.workspace,
                                           episode.events if episode else [])
                    metrics.record("verify", verdict=vres["verdict"],
                                   findings=vres["findings"][:4])
                    emit({"type": "verify", **vres})
                except Exception:
                    pass
        except Exception:
            pass

    # A wrap pass that STILL talks about plumbing is the failure the live eval
    # showed (math_sieve, 39.9 s, tools=0): the shipped answer was a offer to help.
    # Replace it with what actually happened, and record the task as not done.
    degraded = False
    if (wrapped and not sub and is_meta_ramble(final_output)
            and not asks_about_tools(task)):
        final_output = _grounded_fallback(messages, n_tool_calls)
        degraded = True
        try:
            vres = verifier.verify(task, final_output, ctx.workspace,
                                   episode.events if episode else [])
            metrics.record("verify", verdict=vres["verdict"], degraded=True,
                           findings=vres["findings"][:4])
            emit({"type": "verify", **vres})
        except Exception:
            pass

    if iters >= max_iters and not wrapped:
        return _finish(ctx, task, episode, AgentResult(
            output=final_output or "(stopped: max iterations reached)", model=name,
            iterations=iters, escalated=escalated, tool_calls=n_tool_calls,
            est_tokens=tokens, ok=False, error="max iterations",
            verify=vres["verdict"], route_source=rinfo.get("source", "")), start, emit, sub)

    # Never ship code you did not run — full rationale and the execution
    # contract live in answer_postprocess.run_attached_snippet.
    if should_run_attached_code(task, final_output, ran_code=ran_code, sub=sub,
                                cancelled=cancelled):
        final_output, _snippet_calls = run_attached_snippet(
            ctx, cfg, task, final_output, on_ask=on_ask, emit=emit,
            episode=episode, messages=messages)
        n_tool_calls += _snippet_calls

    # A45b: a plan the model narrates instead of producing — rationale and the
    # planner contract live in answer_postprocess.relay_plan.
    if (not sub and not cancelled and not plan_text and final_output
            and wants_plan(task)):
        plan_text, _plan_calls = relay_plan(ctx, task, emit=emit, episode=episode)
        n_tool_calls += _plan_calls

    # A plan the model paraphrases is a plan the user cannot act on — the
    # attach rule lives in answer_postprocess.attach_plan.
    final_output = attach_plan(final_output, plan_text, task, sub)

    # A final answer that STILL asserts an action no tool performed must not
    # be delivered as plain success — annotation lives in
    # answer_postprocess.annotate_unverified_claim.
    final_output, claim_fail = annotate_unverified_claim(final_output, vres, sub)

    # A46: an empty answer is an unfinished task, never a verified one.
    if empty_final:
        vres = {"verdict": "fail",
                "findings": [{"check": "empty answer",
                              "detail": "the model returned no text for this task"}]}

    res = AgentResult(output=final_output, model=name, iterations=iters, escalated=escalated,
                      tool_calls=n_tool_calls, est_tokens=tokens, sub_results=sub_results,
                      ok=not (claim_fail or degraded or empty_final),
                      error=("unverified action claim" if claim_fail
                             else ("no answer after wrap" if degraded
                                   else ("empty answer" if empty_final else ""))),
                      verify=vres["verdict"], route_source=rinfo.get("source", ""))
    return _finish(ctx, task, episode, res, start, emit, sub, raw=said)
