"""Per-turn context assembly: system prompt, skills index, memory pointers."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .. import paths
from ..config import Config


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


def skills_index(cfg: Config) -> str:
    lines = []
    for md in sorted(paths.SKILLS_DIR.glob("*/SKILL.md")):
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
        lines.append(f"- {md.parent.name}: {desc or first}")
    if not lines:
        return "(no skills indexed — use skill_create to distill novel solutions)"
    return "\n".join(lines[:60])


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
    skills = skills_index(cfg)
    lessons = recent_lessons(cfg)
    u = cfg.user
    interests = f" · interests: {', '.join(u.interests)}" if u.interests else ""
    user_block = (f"## Who I serve\n"
                  f"- Name: **{u.name}** — address them as \"{u.name}\" when natural (never as 'user').\n"
                  f"- Timezone: {u.timezone} (times/deadlines in local time)"
                  f"{interests}.\n"
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
