"""BEE core agent loop — production edition (Phase 4).

Pipeline per task:
  route (explicit > deterministic > ML > heuristic)
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
import re
import threading
import time
from dataclasses import dataclass, field

from ..config import Config
from .client import LLMClient, LLMError
from .context import Context, build_sub_system, build_system_prompt, module_api_card
from .router import route as route_v2, strip_cloud_prefix, CLOUD_PREFIX

from .. import guard, privacy
from ..brain import rag as rag_mod
from ..brain import verifier
from ..episodes.logger import Episode
from ..monitor import metrics
from ..security import audit as audit_mod
from ..tools import tools_litellm, tools_by_name, tools_meta
from ..tools.base import untrusted_fence

MAX_OUTPUT_CHARS = 6000
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


@dataclass
class AgentResult:
    output: str
    model: str = ""
    iterations: int = 0
    escalated: bool = False
    tool_calls: int = 0
    ok: bool = True
    error: str = ""
    est_tokens: int = 0
    sub_results: list = field(default_factory=list)
    verify: str = ""
    route_source: str = ""


# --------------------------------------------------------------- helpers
def _safe_args(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        v = json.loads(raw) if isinstance(raw, str) else raw
        return v if isinstance(v, dict) else {"value": v}
    except Exception:
        return {"_raw": str(raw)}


def _fmt_result_text(res) -> str:
    if isinstance(res, dict):
        try:
            return json.dumps(res, ensure_ascii=False)[:MAX_OUTPUT_CHARS]
        except Exception:
            return str(res)[:MAX_OUTPUT_CHARS]
    return str(res)[:MAX_OUTPUT_CHARS]


def _diary(task: str, result: AgentResult) -> None:
    try:
        from ..memory.md import diary_add
        snippet = (result.output or result.error or "")[:400].replace("\n", " ")
        diary_add(f"task: {task[:200].replace(chr(10), ' ')}\nresult: {snippet}",
                  model=result.model, escalated=result.escalated)
    except Exception:
        pass


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


def _iter_json_blocks(c: str):
    """Yield each top-level {...} block (string/escape aware). Handles JSONL-style output."""
    i, n = 0, len(c)
    while i < n:
        if c[i] != "{":
            i += 1
            continue
        depth, in_str, esc = 0, False, False
        for j in range(i, n):
            ch = c[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        yield c[i:j + 1]
                        i = j + 1
                        break
        else:
            break


_TOOL_INTENT_RE = re.compile(
    r"\b(?:i\s+will|i'?ll|let\s+me|i\s+am\s+going\s+to|we\s+shall)\b"
    r"[^.\n]{0,60}\b(?:function|tool)\s*call", re.I)
# A 3B model that loses the plot answers the SYSTEM PROMPT instead of the user:
# "It seems there was an error… no function calls were provided for execution.
# The available functions are: …". That text is never an acceptable reply.
# …but a user who genuinely asks about the tool surface must get that answer.
# The exemption is about the QUESTION, not about the word 'tool' appearing in it:
# 'Use the planner tool' is an instruction, and the model's reply
# 'None of the provided functions seem to be used…' is the failure, not a
# legitimate answer about capabilities (live evidence: plan_complex).
# The planner produces user-facing text; relay it when the request asked for a plan.
_WANTS_PLAN = re.compile(r"\bplan(?:ning|ned)?\b|\broadmap\b|\bstep[- ]by[- ]step\b", re.I)

# 'compute … with a Python snippet' asks for a RESULT, not a sketch. When the answer
# carries a fenced block that never ran, the block is executed and its real output
# reported (dsa_lis / dsa_gcd_lcm / dsa_graph, live: tools=0, prose describing code).
_WANTS_PY = re.compile(
    r"\b(?:using|with|in|write|run|compute|show)\b[^.\n]{0,24}\bpython\b"
    r"|\bpython\b[^.\n]{0,24}\b(?:snippet|code|program|script)\b", re.I)
# Volunteering code for a question that asked for a VALUE is the same unverified
# claim, whatever the user happened to type: math_sieve, live, answered 'how many
# primes between 1 and 100' with a fenced `def count_primes_up_to…` block and no
# number, because the request never said the word 'python'.
_WANTS_RESULT = re.compile(
    r"\b(?:how many|how much|what is|what are|compute|calculate|evaluate|count|"
    r"find the value|which|list|print|output|result)\b", re.I)
_PY_FENCE = re.compile(r"```(?:python|py)?[ \t]*\r?\n(.*?)```", re.S | re.I)

# A45a: does this snippet produce output of its own? If not, running it verbatim
# yields empty stdout and there is nothing to verify against — the exact dead end
# `dsa_gcd_lcm` hit in the live eval (the displayed code computed gcd/lcm into
# variables and never printed them, so "I ran it; it prints:" came back blank).
_PRINTS_SRC = re.compile(
    r"\b(?:print|pprint)\s*\(|sys\.stdout|\.write\s*\(|\binput\s*\(", re.I)

# Appended ONLY when the snippet has no output statement, so a printing snippet
# still runs verbatim and nothing is ever executed twice. Bounded, and it prints
# the code's own computed values rather than guessing at them.
_VALUE_READOUT = """


# --- appended by BEE: this snippet printed nothing, so report the values it computed
import types as _bee_types
_bee_rows = []
for _bee_k, _bee_v in list(globals().items()):
    if _bee_k.startswith("_") or isinstance(
            _bee_v, (_bee_types.ModuleType, _bee_types.FunctionType,
                    _bee_types.BuiltinFunctionType, type)):
        continue
    if isinstance(_bee_v, (int, float, str, bool, list, tuple, dict, set, frozenset)):
        _bee_rows.append((_bee_k, _bee_v))
for _bee_k, _bee_v in sorted(_bee_rows)[:12]:
    try:
        print(f"{_bee_k} = {repr(_bee_v)[:160]}")
    except Exception:
        pass
"""

_ABOUT_TOOLS_TASK = re.compile(
    r"\b(?:which|what|all)\s+(?:[a-z]+\s+){0,3}(?:tools?|functions?|capabilit\w+|"
    r"permissions?|integrat\w+)\b"
    r"|\b(?:tools?|functions?|capabilit\w+)\s+(?:do\s+you\s+(?:have|support)|"
    r"are\s+(?:available|listed|provided))"
    r"|\b(?:do\s+you|can\s+you)\s+(?:have|use|list|show(?:\s+me)?)\s+(?:any|the|your)\s+"
    r"(?:tools?|functions?|capabilit\w+)", re.I)
_META_RAMBLE_RE = re.compile(
    r"\b(?:no|without(?:\s+any)?)\s+(?:function|tool)\s*calls?\b"
    r"|\bno\s+(?:[a-z]+\s+){0,2}?(?:function|tool)\s*calls?\b"
    r"|\b(?:available|listed|provided)\s+(?:function|tool)s?\b"
    r"|\b(?:function|tool)s?\s+(?:were|was|are|is|were\s+not)\s+(?:not\s+)?(?:provided|available|given)\b"
    r"|\b(?:function|tool)s?\s+(?:provided|available|listed)\b"
    r"|\b(?:call|invoke)\s+(?:a|any|the)\s+(?:function|tool)\b"
    r"|\bmy\s+call\s+to\s+use\s+the\s+available\b"
    # dsa_lis, live: "…prior context to work with for the functions provided
    # earlier. Since no specific function call is mentioned, I can't provide
    # details on what action was intended." — none of the shapes above matched.
    r"|\b(?:didn'?t|did\s+not|haven'?t|have\s+not)\s+(?:receive|get|got)\b[^.\n]{0,48}"
    r"\b(?:function|tool|context)s?\b"
    r"|\bwhat\s+action\s+was\s+intended\b"
    # dsa_gcd_lcm, live (the last task still failing): '…the last message did not
    # contain any information to proceed with a function call. If you intended for me
    # to perform a specific action using one of these functions…'. Deliberately
    # tied to the asking-the-user-for-plumbing-input frame, so a legitimate answer
    # like 'the tool call failed with a timeout' is NOT treated as a ramble.
    r"|\b(?:proceed|continue|go\s+ahead)\b[^.\n]{0,32}\b(?:a|one|any|the)\s+(?:function|tool)s?\b"
    r"|\b(?:if\s+you\s+intended|please\s+provide\s+more\s+details|need\s+more\s+details)"
    r"[^.\n]{0,60}\b(?:function|tool)s?\b", re.I)


_ABOUT_REFUSAL = re.compile(
    r'"blocked"|too many actions|not allowed|denied|"error"|error":', re.I)
# Loop-control payloads: the repeat/cache breaker's own note, which is plumbing and
# not evidence of anything (live: the honest fallback quoted it as 'the last thing a
# tool actually returned').
_LOOP_CONTROL = re.compile(
    r'"note":\s*"(?:You already ran|.{0,60}has been called)', re.I)


def _grounded_fallback(messages: list, n_tool_calls: int) -> str:
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
        if c and not _ABOUT_REFUSAL.search(c) and not _LOOP_CONTROL.search(c):
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


def _extract_text_tool_calls(content: str) -> list:
    """Small local models sometimes emit tool calls as TEXT (JSON / JSONL / fenced).
    Recover them. Only dicts having both 'name' and 'arguments' are accepted."""
    if not content:
        return []
    c = content.strip()
    candidates = [c]
    m = re.search(r"```(?:json)?\s*([\[{].*?[\]}])\s*```", c, re.S)
    if m:
        candidates.append(m.group(1))
    for cand in candidates:
        try:
            data = json.loads(cand)
        except Exception:
            data = None
        if data is not None:
            items = data if isinstance(data, list) else [data]
            tcs = []
            for it in items:
                if isinstance(it, dict) and "name" in it and "arguments" in it:
                    args = it["arguments"]
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            args = {"_raw": args}
                    if not isinstance(args, dict):
                        args = {"value": args}
                    tcs.append({"id": f"call_{len(tcs)}", "name": str(it["name"]), "arguments": args})
            if tcs:
                return tcs
    blocks = []
    for block in _iter_json_blocks(c):
        try:
            it = json.loads(block)
        except Exception:
            continue
        if isinstance(it, dict) and "name" in it and "arguments" in it:
            blocks.append(it)
    if not blocks:
        return []
    tcs = []
    for it in blocks:
        args = it["arguments"]
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = {"_raw": args}
        if not isinstance(args, dict):
            args = {"value": args}
        tcs.append({"id": f"call_{len(tcs)}", "name": str(it["name"]), "arguments": args})
    return tcs


def _audit_record(tname: str, args, action: str, ok: bool, dt: float,
                  blocked: bool, source: str = "agent") -> None:
    """Persistent audit row for one tool call (redacted; never raises)."""
    try:
        decision = None
        if tname in guard.EXEC_TOOLS:
            from ..security import risk
            decision = risk.classify_risk(tname, args)
        audit_mod.record(tool=tname, args=args, decision=decision, action=action,
                         ok=ok, seconds=dt, blocked=blocked, source=source)
    except Exception:
        pass


def _offline_result(task: str, workspace) -> AgentResult:
    from .offline import run_offline
    out = run_offline(task, workspace)
    metrics.record("offline", task=task[:200])
    return AgentResult(output=out, model="offline-rules", ok=True, route_source="offline")


def _golden(task: str, res: AgentResult) -> None:
    """Teach-back: a successful CLOUD answer becomes training material for the
    local model (SFT pipeline) and skill distillation (nightly job)."""
    try:
        from .. import paths as _p, safeio as _safeio
        d = _p.TRAIN_DIR / "golden"
        d.mkdir(parents=True, exist_ok=True)
        _safeio.append_json(d / "cloud_golden.jsonl",
                            {"task": task[:500], "response": res.output[:4000],
                             "model": res.model, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")})
    except Exception:
        pass


def _finish(ctx, task, episode: Episode | None, res: AgentResult, start: float,
            emit, sub: bool) -> AgentResult:
    if episode:
        episode.finish(res.ok, res.output, error=res.error, escalated=res.escalated,
                       verify={"verdict": res.verify}, tokens=res.est_tokens)
    metrics.record("task", ok=res.ok, model=res.model, iters=res.iterations,
                   tools=res.tool_calls, seconds=round(time.time() - start, 1),
                   tokens=res.est_tokens, escalated=res.escalated,
                   verify=res.verify, source=res.route_source, error=res.error[:200])
    if not sub:
        _diary(task, res)
        if res.ok and res.escalated and (res.output or "").strip():
            _golden(task, res)
    emit({"type": "done", "output": res.output, "verify": res.verify})
    return res


def _run_fastpath(ctx, cfg, task: str, fp, m, episode, start: float, emit, sub: bool):
    """Execute one matched fast path. Returns an AgentResult, or None to fall
    through to the normal (model) pipeline when the handler declines/errors."""
    from . import fastpaths
    try:
        out = fp.handle(ctx, m)
    except Exception as e:
        emit({"type": "fastpath", "name": fp.name, "fell_through": str(e)[:120]})
        return None
    if out is None:
        return None
    if isinstance(out, fastpaths.FastExec):
        from ..tools import tools_by_name
        reg = {} if sub else tools_by_name()
        if out.tool not in reg:
            return None
        emit({"type": "fastpath", "name": fp.name, "tool": out.tool})
        proceed, action, reason = True, "allow", "not needed"
        if out.tool in guard.EXEC_TOOLS and ctx.guard_on and cfg.guard.enabled:
            proceed, action, reason = guard.check(out.tool, out.args, True, ctx.guard_mode)
            metrics.record("guard", tool=out.tool, action=action, reason=reason)
            emit({"type": "guard", "tool": out.tool, "action": action, "reason": reason})
        if not proceed:
            _audit_record(out.tool, out.args, action, False, 0.0, blocked=True, source="fastpath")
            text = out.blocked(reason) if callable(out.blocked) else str(out.blocked)
            n_tools = 0
        else:
            emit({"type": "tool_start", "tool": out.tool, "args": out.args})
            t0 = time.time()
            try:
                res_v = reg[out.tool](ctx, **out.args)
            except Exception as e:
                res_v = {"error": str(e)}
            ok_v = not (isinstance(res_v, dict) and (res_v.get("error") or res_v.get("blocked")))
            dt = round(time.time() - t0, 1)
            _audit_record(out.tool, out.args, action, ok_v, dt,
                          blocked=bool(isinstance(res_v, dict) and res_v.get("blocked")),
                          source="fastpath")
            metrics.record("tool", tool=out.tool, ok=ok_v, seconds=dt)
            emit({"type": "tool_result", "tool": out.tool, "ok": ok_v, "seconds": dt,
                  "preview": str(res_v)[:120]})
            text = out.reply(res_v) if callable(out.reply) else str(out.reply)
            n_tools = 1
        res = AgentResult(output=text, model="deterministic", ok=True, verify="pass",
                          route_source="fastpath", tool_calls=n_tools)
        metrics.record("route", task=task[:200], route="fastpath", source=fp.name)
        return _finish(ctx, task, episode, res, start, emit, sub)
    res = AgentResult(output=str(out), model="deterministic", ok=True, verify="pass",
                      route_source="fastpath")
    metrics.record("route", task=task[:200], route="fastpath", source=fp.name)
    return _finish(ctx, task, episode, res, start, emit, sub)


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
    # P0 (audit): the ToolBus is now the single dispatcher for EVERY
    # tool-capable route, including deterministic fast paths. The bus consults
    # ctx.approver for its guard 'ask' path — bind it to this run's on_ask so
    # the kernel's WAITING_FOR_PERMISSION flow is identical whether the call
    # came from the model loop or a 0 ms shortcut. Restored on exit so a
    # nested/sub run never leaks its approver into an outer one.
    _prev_approver = getattr(ctx, "approver", None)
    ctx.approver = on_ask
    try:
        return _run_agent_inner(ctx, task, on_event, model, max_iters, system, sub,
                                on_ask, on_token, route_text)
    finally:
        ctx.approver = _prev_approver


def _run_agent_inner(ctx: Context, task: str, on_event=None, model: str | None = None,
                     max_iters: int = 25, system: str | None = None, sub: bool = False,
                     on_ask=None, on_token=None, route_text: str | None = None) -> AgentResult:
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
    rinfo = route_v2(said, cfg, model)
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

    # ------------------------------------ tier 0: fast paths (pure Python, no LLM)
    # explicit model hints ('cloud: ...' / 'local: ...') always win over fast paths
    if rinfo.get("source") != "explicit":
        from . import fastpaths
        hit = fastpaths.match(said)
        if hit is not None:
            done = _run_fastpath(ctx, cfg, said, hit[0], hit[1], episode, start, emit, sub)
            if done is not None:
                return done

    # ------------------------------------------------- availability / fallback chain
    local_up = ctx.client.ollama_up()      # public provider API (Phase 6)
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
    messages: list[dict] = [{"role": "system", "content": system}, {"role": "user", "content": user_content}]
    tools = None if sub else tools_litellm()
    registry = tools_by_name() if tools else {}
    meta = tools_meta() if tools else {}

    def llm_call(cur_name: str):
        if cur_name != "local" and cfg.privacy.redact_cloud and ctx.privacy_on:
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
                                                 tools=tools)
                except LLMError:
                    out = ctx.client.chat(cur_name, msgs, tools=tools)  # one fallback
            else:
                out = ctx.client.chat(cur_name, msgs, tools=tools)
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
    n_tool_calls = 0
    tokens = 0
    sub_results: list[str] = []
    verify_rounds = 0
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
    # the planner tool's own numbered steps, kept so the user can be given the plan
    # rather than the model's vague paraphrase of it
    plan_text = ""
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
            if txt and not sub and not narration_nudged and _TOOL_INTENT_RE.search(txt):
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
                    and not _ABOUT_TOOLS_TASK.search(task or "")
                    and _META_RAMBLE_RE.search(txt)):
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
                messages.append({"role": "assistant", "content": final_output})
                messages.append({"role": "user", "content":
                    "What you just wrote describes something that did not happen. "
                    + (f"Here is what actually went wrong: {problems}. " if problems else
                       "Nothing in it is backed by a result you actually received. ")
                    + "Rewrite the answer using only what the results above show; if a "
                    "part could not be done, say that plainly. Do not talk about tools, "
                    f"checks or this message.\n\nRequest:\n{task[:600]}"})
                continue
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
            # Phase 3: capability gate — authorization is checked BEFORE
            # execution. Kernel-injected (ctx.capability_gate); legacy direct
            # run_agent paths without a kernel skip it. A denial feeds the
            # same blocked-result flow as the guard, so audit/episode/telemetry
            # and the model's 'explain the refusal' behavior all work.
            # Phase 12 (N1 CRITICAL): the gate is the kernel's authorization
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
                    # dispatcher. Kernel-backed runs execute through
                    # bus.call — one dispatch point, pre-call cancel check
                    # (stop_check), unified unknown-tool / malformed-args
                    # errors, and the bus's per-tool metadata. Legacy
                    # kernel-less direct run_agent falls back to the
                    # registry (identical handler set).
                    bus = getattr(getattr(ctx, "kernel", None), "bus", None)
                    try:
                        if bus is not None:
                            res_v, _bdt, _bok, _bmeta = bus.call(
                                ctx, tname, args, stop_check=ev_cancel.is_set)
                        else:
                            res_v = registry[tname](ctx, **args)
                    except PermissionError as e:
                        # bus.call raises PermissionError("cancelled before
                        # execution") when stop_check() fires. A PermissionError
                        # from the handler itself (e.g. workspace jail) is an
                        # ERROR for this call, not a task cancellation.
                        if "cancelled" in str(e):
                            ev_cancel.set()
                            cancelled = True
                            break
                        res_v = {"error": f"{tname} raised PermissionError: {e}"}
                    except TypeError as e:
                        # The ToolBus already phrases this as
                        # 'bad arguments for <tool>: …'; wrapping it again produced
                        # 'bad arguments for scheduler: bad arguments for scheduler: …'
                        # in front of the model and in the receipts (live probe).
                        msg = str(e)
                        res_v = {"error": msg if msg.startswith("bad arguments for")
                                 else f"bad arguments for {tname}: {msg}"}
                    except KeyboardInterrupt:
                        ev_cancel.set()
                        cancelled = True
                        break
                    except Exception as e:
                        res_v = {"error": f"{tname} raised {type(e).__name__}: {e}"}
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
                 or (_META_RAMBLE_RE.search(final_output or "")
                     and not _ABOUT_TOOLS_TASK.search(task or "")))):
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
    if (wrapped and not sub and _META_RAMBLE_RE.search(final_output or "")
            and not _ABOUT_TOOLS_TASK.search(task or "")):
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

    # Never ship code you did not run. Three eval tasks ask for a computation 'with a
    # short Python snippet'; the 3B model returns the snippet plus prose with tools=0,
    # so the number it states is its own arithmetic. Execute the block it presented —
    # through the capability gate and the guard, exactly like any other tool call — and
    # report the real output, or say plainly that nothing was verified.
    if (not sub and not cancelled and not ran_code and final_output
            and (_WANTS_PY.search(task or "")
                 or (_WANTS_RESULT.search(task or "") and _PY_FENCE.search(final_output)))
            and not _META_RAMBLE_RE.search(final_output)):
        fm = _PY_FENCE.search(final_output)
        snippet = (fm.group(1).strip() if fm else "")
        if 8 <= len(snippet) <= 4000:
            from ..tools import tools_by_name as _tbn
            # What the gate authorizes, the guard checks and the interpreter runs
            # must be the SAME text — otherwise a read-out appended after
            # approval would run unreviewed.
            echoed = not _PRINTS_SRC.search(snippet)
            run_src = snippet + _VALUE_READOUT if echoed else snippet
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
            else:
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
                n_tool_calls += 1
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
                                 "name": "code_run", "content": _fmt_result_text(rv)})
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

    # A45b: a plan the model narrates instead of producing. `plan_complex` asked
    # for a plan "using the planner tool", the 3B model answered "I would follow
    # these steps: 1. Loading…" and never called the planner — so the relay below
    # had nothing to relay and the answer lost the library names the planner does
    # produce. The planner is risk-LOW and needs no capability, so asking it is
    # not a new permission surface; it is the tool the user named.
    if (not sub and not cancelled and not plan_text and final_output
            and _WANTS_PLAN.search(task or "")):
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
        n_tool_calls += 1 if okp else 0
        emit({"type": "tool_start", "tool": "planner", "args": {"task": task[:120]}})
        emit({"type": "tool_result", "tool": "planner", "seconds": round(dtp, 1),
              "ok": okp, "preview": (ptxt or str(pv.get("error") or ""))[:300]})
        if episode:
            episode.tool("planner", {"task": task}, okp, dtp, pv)
        metrics.record("tool", tool="planner", ok=okp, seconds=round(dtp, 2), blocked=False)
        if okp:
            plan_text = ptxt

    # A plan the model paraphrases is a plan the user cannot act on. Asked to plan a
    # CSV analysis with the planner tool, the reply was 'we would need to load the
    # data, which may take some time' — the planner's own numbered steps named the
    # libraries, and they were dropped on the way to the user.
    if (not sub and plan_text and final_output and _WANTS_PLAN.search(task or "")
            and plan_text.splitlines()[0][:40] not in final_output):
        final_output = (final_output.rstrip()
                        + "\n\nPlan as produced:\n" + plan_text[:2000])

    # A final answer that STILL asserts an action no tool performed must not be
    # delivered as plain success. Verification already failed once and the model
    # repeated the claim (live evidence: 'I executed git reset --hard HEAD~1'
    # after 16 unrelated tool calls) — the user would read a destructive action
    # into their own repository history. Say plainly that it is unverified.
    claim_fail = (not sub and vres.get("verdict") == "fail"
                  and any(f.get("check") == "claim" for f in vres.get("findings") or []))
    if claim_fail:
        final_output = ((final_output or "").rstrip() +
                        "\n\n⚠ I could not verify that this actually ran — no tool "
                        "result backs it up. Please treat the action as NOT done.")

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
    return _finish(ctx, task, episode, res, start, emit, sub)
