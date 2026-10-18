"""Per-turn context assembly: system prompt, skills index, memory pointers."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
import ast
import logging
import re

from .. import paths
from ..config import Config

log = logging.getLogger("bee.context")


@dataclass
class Context:
    cfg: Config
    workspace: Path = field(default=None)
    name: str = "BEE"
    client: object = None          # set by run_agent (LLMClient)
    model_note: str = ""           # set by run_agent (which LLM answered)
    model_override: str | None = None  # engine choice (local / cloud / raw model name)
    # Phase 4 controls (all default on; per-session overridable)
    cancel_event: object = None    # threading.Event — set to stop the loop
    guard_on: bool = True
    guard_mode: str = "cli"        # cli | unattended | always
    privacy_on: bool = True        # redact PII on cloud-bound payloads
    rag_on: bool = True            # auto memory-context on dangling references
    episodes_on: bool = True       # record episodes for the data pipeline
    kernel: object = None          # Phase 2: AgentKernel instance (set at launch;
                                   # commands use ctx.kernel.direct for LLM calls)
    capability_gate: object = None # Phase 3: CapabilityGate — checked BEFORE tool
                                    # execution (set by the kernel; legacy direct
                                    # run_agent paths without a kernel skip it)
    current_task_id: str = ""      # Phase 3: kernel task id for task-scoped grants
    # J2: skills force-included in the prompt for THIS context (the skill-gate
    # eval probe uses this to measure a candidate skill with it actually live)
    force_skills: set = field(default_factory=set)

    def __post_init__(self):
        if self.workspace is None:
            self.workspace = self.cfg.workspace


def create_context(cfg: Config, name: str = "BEE",
                   model_override: str | None = None,
                   guard_mode: str | None = None,
                   client: object | None = None) -> "Context":
    """Single application-context factory (Phase 1: replaces the 7+ duplicated
    bootstrap sites in cli / webapp / livekit).

    - attaches the LLM client (or an injected stand-in for tests)
    - applies the persisted engine choice unless an explicit override is given
    - applies the guard mode (config default, or e.g. 'unattended' for the
      LiveKit worker — passed EXPLICITLY, never by mutating the shared config)
    """
    from .client import LLMClient
    from . import engines
    ctx = Context(cfg, workspace=cfg.workspace, name=name)
    ctx.client = client if client is not None else LLMClient(cfg)
    ctx.guard_mode = guard_mode if guard_mode is not None else cfg.guard.mode
    if model_override is None:
        model_override = engines.override_for(engines.load_engine())
    ctx.model_override = model_override
    return ctx


def _read(p: Path, limit: int = 4000) -> str:
    if not p.exists():
        return ""
    try:
        t = p.read_text(encoding="utf-8", errors="ignore").strip()
    except Exception:
        return ""
    return t[:limit]


def skills_index(cfg: Config, force: "set | None" = None) -> str:
    """Index of SHIPPED skills only.

    J2: skills in `candidate` status (created/updated but not yet through the
    skill gate) are excluded — unproven instructions must not enter the
    prompt. Legacy skills without meta.json are treated as active. Names in
    `force` bypass the filter (the skill-gate eval probe)."""
    try:
        from ..evals.skillgate import read_meta
    except Exception:
        read_meta = None
    lines = []
    for md in sorted(paths.SKILLS_DIR.glob("*/SKILL.md")):
        name = md.parent.name
        if read_meta is not None and name not in (force or set()):
            try:
                if read_meta(name).get("status") == "candidate":
                    continue
            except Exception:
                pass
        try:
            body = md.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        first = body.split("\n", 1)[0].lstrip("# ").strip() or md.parent.name
        desc = ""
        for ln in body.splitlines():
            if ln.lower().startswith("description:"):
                desc = ln.split(":", 1)[1].strip()
                break
        lines.append(f"- {name}: {desc or first}{_module_hint(body, name)}")
    if not lines:
        return "(no skills indexed — use skill_create to distill novel solutions)"
    return "\n".join(lines[:60])


def _module_hint(body: str, name: str) -> str:
    """A45c: the index line used to carry only the description, so BEE knew a `dsa`
    skill existed but not what it imports — and in the live eval `dsa_graph`
    invented `bee_dsa` ('there is no module named bee_dsa available') when the real
    one is `bee.dsa.graphs`, whose name is written in that very skill's body. The
    names cost a few tokens and remove the guess; the full procedure stays behind
    `skill_get`, so the prompt budget is unchanged for everything else."""
    mods: list[str] = []
    for m in re.findall(r"^[ \t]*from[ \t]+([A-Za-z_][\w.]*)[ \t]+import", body, re.M):
        if m not in mods:
            mods.append(m)
        if len(mods) >= 3:
            break
    if not mods:
        return ""
    shown = ", ".join(m if len(m) <= 28 else m[:25] + "..." for m in mods)
    return f"  [imports: {shown}; call skill_get(\"{name}\") for the full procedure]"


# A50: knowing a module's NAME was not enough — the local model still wrote
# `Graph()` / `graph.add_edge()` for `bee.dsa.graphs` (~30 failed live runs of
# `dsa_graph`). When a request names one of BEE's own modules, the model gets the
# real public signatures, parsed from source with `ast` (the module never runs).
_DOTTED = re.compile(r"(?<![\w.])([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+)")
_CARD_MODULES = 2
_CARD_CHARS = 1500
_CARD_MAX_SRC = 300_000
_SELF_ARG = re.compile(r"^(?:self|cls)(?:,\s*)?")


def _module_source(dotted: str) -> "tuple[str, Path] | None":
    parts = dotted.split(".")
    root = paths.PROJECT_ROOT
    if not (root / parts[0] / "__init__.py").is_file():
        return None
    for n in range(len(parts), 1, -1):
        base = root.joinpath(*parts[:n])
        for f in (base.parent / f"{base.name}.py", base / "__init__.py"):
            if f.is_file():
                return ".".join(parts[:n]), f
    return None


def _sig(node, drop_self: bool = False) -> str:
    args = ast.unparse(node.args)
    if drop_self:
        args = _SELF_ARG.sub("", args)
    ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    pre = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
    return f"{pre}{node.name}({args}){ret}"


def _doc1(node) -> str:
    doc = (ast.get_docstring(node) or "").strip()
    return doc.split("\n", 1)[0][:120]


def _api_lines(tree: ast.Module) -> "tuple[list[str], list[str]]":
    fn = (ast.FunctionDef, ast.AsyncFunctionDef)
    names: list[str] = []
    out: list[str] = []
    for node in tree.body:
        if getattr(node, "name", "_").startswith("_"):
            continue
        if isinstance(node, fn):
            d = _doc1(node)
            names.append(node.name)
            out.append(f"- {_sig(node)}" + (f" — {d}" if d else ""))
        elif isinstance(node, ast.ClassDef):
            bases = ", ".join(ast.unparse(b) for b in node.bases)
            d = _doc1(node)
            names.append(node.name)
            out.append(f"- class {node.name}" + (f"({bases})" if bases else "")
                       + (f" — {d}" if d else ""))
            for m in node.body:
                if isinstance(m, fn) and (m.name == "__init__" or not m.name.startswith("_")):
                    out.append(f"    .{_sig(m, drop_self=True)}")
    return names, out


def module_api_card(text: str) -> str:
    cards: list[str] = []
    seen: set[str] = set()
    for m in _DOTTED.finditer(text or ""):
        hit = _module_source(m.group(1))
        if hit is None or hit[0] in seen:
            continue
        mod, src = hit
        seen.add(mod)
        try:
            if src.stat().st_size > _CARD_MAX_SRC:
                continue
            tree = ast.parse(src.read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError, ValueError):
            continue
        names, lines = _api_lines(tree)
        if not lines:
            continue
        head = (f"Real API of `{mod}` (read from its source; use only these names, "
                f"e.g. `from {mod} import {names[0]}`):")
        doc = " ".join((ast.get_docstring(tree) or "").split())[:300]
        body = [head] + ([doc] if doc else [])
        size = sum(len(x) + 1 for x in body)
        for ln in lines:
            if size + len(ln) + 1 > _CARD_CHARS:
                body.append("- …")
                break
            body.append(ln)
            size += len(ln) + 1
        cards.append("\n".join(body))
        if len(cards) >= _CARD_MODULES:
            break
    return "\n\n".join(cards)


def recent_lessons(cfg: Config, n: int = 3, lines: int = 12) -> str:
    files = sorted(paths.LESSONS_DIR.glob("*.md"), reverse=True)[:n]
    if not files:
        return ""
    out = []
    for f in files:
        txt = _read(f, limit=3000).splitlines()[:lines]
        out.append(f"### {f.name}\n" + "\n".join(txt))
    return "\n\n".join(out)


PERSONA = (
    "## Persona — BEE\n"
    "You are BEE, an elite executive & personal assistant: sharp, organized, proactive, direct, warm, energetic.\n"
    "- Begin with the answer or the action. No greetings, pleasantries, filler, or robotic setup.\n"
    "- Crisp and structured: short bullets, tables for comparisons, explicit owners and deadlines where relevant.\n"
    "- Be proactive: flag risks early, propose the next step, surface what the user will likely need next.\n"
    "- Errors: state what failed, why, and the exact fix. Never invent results or hide failures.\n"
    "- Spoken-friendly: keep the core of the reply under 4 sentences; depth goes in the written detail."
)


def build_system_prompt(ctx: Context) -> str:
    cfg = ctx.cfg
    # trimmed limits: smaller prefill = faster first token on the local 8B model
    base = _read(paths.SYSTEM_MD, limit=4000)
    profile = _read(paths.PROFILE_MD, limit=1500)
    longterm = _read(paths.LONGTERM_MD, limit=1500)
    skills = skills_index(cfg, force=getattr(ctx, "force_skills", None))
    lessons = recent_lessons(cfg)
    u = cfg.user
    interests = f" · interests: {', '.join(u.interests)}" if u.interests else ""
    region = f" · region: {u.region}" if getattr(u, "region", "") else ""
    user_block = (f"## Who I serve\n"
                  f"- Name: **{u.name}** — address them as \"{u.name}\" when natural (never as 'user').\n"
                  f"- Timezone: {u.timezone} (times/deadlines in local time)"
                  f"{region}{interests}.\n"
                  f"- **{u.name} created me** — if asked who made/built/created me, say {u.name} built me on this machine.\n")
    return f"""# {ctx.name} — {date.today().isoformat()}

{PERSONA}

{base}

## Environment
- Workspace: {ctx.workspace}  (all file/shell/code operations stay here)
- Local model: {cfg.ollama.model} @ {cfg.ollama.base_url}
- Cloud model: {cfg.cloud.llm or '(not configured)'} — auto-escalation on complex tasks
- Sandbox: docker image '{cfg.sandbox.image}' (if available)
- **Act, don't refuse:** for action tasks (open/launch/visit/check/compute), call a tool immediately — never reply that you cannot do it. If a tool fails, report the failure and the next step.
- **Shell 'start' needs full URLs:** to open a site in the browser use `start "" "https://domain"` — a bare domain will fail. If you must type into a web app, say you can open the page but cannot operate its UI.

{user_block}
## User profile
{profile or '(empty — fill via memory tool as you learn the user)'}

## Long-term memory
{longterm or '(empty)'}

## Skills available (load with the skill tool; distill new ones after novel successes)
{skills}

## Recent lessons (from past tasks)
{lessons or '(none yet)'}
"""


def build_sub_system(ctx: Context) -> str:
    return (
        f"# {ctx.name} — sub-agent\n"
        f"You are a focused worker. Complete the task with the available tools. "
        f"Workspace: {ctx.workspace}. Return only a concise final answer/report. "
        f"Do not ask questions; make reasonable assumptions."
    )


def canonical_system_prompt(cfg: Config | None = None) -> str:
    """Stable counterpart of `build_system_prompt` for SFT/inference parity (P1).

    Training rows used to be user-first with NONE of what inference carries (the
    system prompt + tool surface, ~8k est tokens), so the model never saw the
    frame it actually answers in. This renders the same STRUCTURE with
    context-independent content: identity/persona, the environment rules, and
    the tool surface the local route advertises (name + one-line description
    from the P0-1 fitted subset). The full JSON schemas are deliberately NOT
    inlined here: measured 8,330 chars ~= 2.1k tokens for the subset alone,
    which does not fit this box's training budget (seq 2048/4096), while the
    call FORMAT is already taught by the tool-call examples. The vocabulary and
    the behavioral frame are what training was missing.
    """
    if cfg is None:
        try:
            from ..config import load_config
            cfg = load_config()
        except Exception:
            cfg = None
    u = getattr(cfg, "user", None)
    who = ""
    if u is not None and getattr(u, "name", ""):
        region = f" · region: {u.region}" if getattr(u, "region", "") else ""
        who = (f"\n## Who I serve\n- Name: **{u.name}** — address them as \"{u.name}\" "
               f"when natural (never as 'user'). Timezone: {u.timezone}{region}.\n")
    try:
        from ..tools import LOCAL_TOOL_NAMES, build_default_tools
        lines = []
        for t in build_default_tools():
            if t.name in LOCAL_TOOL_NAMES:
                d = (t.description or "").strip().split("\n")[0]
                lines.append(f"- {t.name} — {d[:90]}")
        tool_block = "\n".join(lines) or "(no tools)"
    except Exception:
        tool_block = "(tool list unavailable)"
    return f"""# BEE

{PERSONA}

## Environment
- Workspace: the session workspace — all file/shell/code operations stay inside it.
- Local model via Ollama; a cloud model is used for harder tasks when configured.
- **Act, don't refuse:** for action tasks (open/launch/visit/check/compute), call a tool immediately — never reply that you cannot do it. If a tool fails, report the failure and the next step.
- **Shell 'start' needs full URLs:** to open a site in the browser use `start "" "https://domain"`.
{who}
## Tools available (call them with JSON arguments)
{tool_block}
"""


def _token_estimate(messages: list[dict], tools: list | None) -> int:
    """Cheap prompt-size estimator used for history budgeting.

    A59 showed `chars/4` under-counts real BEE turns by ~22% against the model's
    tokenizer, so the estimate is scaled up. It only has to be directionally
    correct to choose which *old* message pairs to drop first.
    """
    n = 0
    for m in messages:
        n += len(m.get("content") or "") // 4
        for tc in m.get("tool_calls") or []:
            fn = tc.get("function") or {}
            args = fn.get("arguments") or ""
            n += (len(fn.get("name", "")) + len(args if isinstance(args, str) else str(args))) // 4
            n += 4   # id / type / overhead
    if tools:
        for t in tools:
            n += len(str(t)) // 4 + 4
    return int(n * 1.3) + len(messages) * 2


def compact_messages(messages: list[dict], tools: list | None, num_ctx: int,
                     completion_reserve: int = 1024,
                     min_recent_pairs: int = 2) -> tuple[list[dict], dict]:
    """Drop oldest tool-history pairs before the model drops them for us.

    Ollama silently truncates to roughly `num_ctx / 2` when a prompt does not
    fit (A59). This is *intentional* compaction of old history so the most
    recent system/task/tool results are preserved, and so the event is logged
    rather than hidden inside the server's KV cache math.

    The first two messages (system + task) are never dropped. From the rest we
    drop the oldest `assistant tool_call` + `tool result` pairs, but always keep
    the most recent `min_recent_pairs` pairs so the model still has evidence of
    what just happened.
    """
    if not num_ctx or len(messages) <= 2:
        return messages, {"compacted": False}
    budget = max(1024, num_ctx - completion_reserve)
    before = _token_estimate(messages, tools)
    if before <= budget:
        return messages, {"compacted": False, "estimate": before,
                          "budget": budget, "fits": True}

    def count_pairs(msgs):
        return sum(1 for j in range(2, len(msgs) - 1)
                   if msgs[j].get("role") == "assistant" and msgs[j].get("tool_calls")
                   and msgs[j + 1].get("role") == "tool")

    kept = list(messages)
    removed = 0
    i = 2
    while i < len(kept) - 1 and _token_estimate(kept, tools) > budget:
        # assistant tool-call turn followed by its tool result
        if (kept[i].get("role") == "assistant" and kept[i].get("tool_calls")
                and kept[i + 1].get("role") == "tool"):
            if count_pairs(kept) <= min_recent_pairs:
                break
            del kept[i:i + 2]
            removed += 2
        # any orphaned tool result older than recent history
        elif kept[i].get("role") == "tool":
            del kept[i]
            removed += 1
        else:
            i += 1

    after = _token_estimate(kept, tools)
    fits = after <= budget
    if removed:
        # `fits is False` is the honest case, not a contradiction: dropping more
        # would remove the last recent pairs, and a live `web_search_tool` turn
        # measured exactly this (8434 est tokens against a 7168 budget).
        log.warning("compacted prompt history: dropped %d messages (%d -> %d est tokens, "
                    "budget %d, %s)", removed, before, after, budget,
                    "fits" if fits else "STILL OVER BUDGET - Ollama will truncate")
        return kept, {"compacted": True, "removed": removed,
                      "estimate_before": before, "estimate_after": after,
                      "budget": budget, "fits": fits}
    if not fits:
        log.warning("prompt over local context budget and nothing left to compact "
                    "(%d est tokens, budget %d) - Ollama will truncate", before, budget)
    return messages, {"compacted": False, "estimate": before, "budget": budget,
                      "fits": fits}
