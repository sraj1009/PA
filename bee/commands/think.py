"""/think — stress-test ideas, trade-offs, pros/cons matrices, strategic alternatives.

Usage:
  /think <idea or decision…>
  /think alternatives <idea…>   focus on strategic alternatives (3+ paths)

Output: verdict up front → pre-mortem → trade-off table → pros/cons matrix →
recommendation. LLM deepens it when reachable; a structured deterministic
pass always produces the skeleton analysis.
"""
from __future__ import annotations

import re
from datetime import date

from . import register


def _llm(ctx, prompt: str, max_tokens: int = 1100) -> str | None:
    # Phase 2: commands execute LLM work through the SAME kernel as main tasks
    # (provider routing, receipts, events, telemetry). The fallback keeps bare
    # ctx objects working (tests without a kernel).
    kernel = getattr(ctx, "kernel", None)
    if kernel is not None:
        try:
            return kernel.direct("think", prompt, max_tokens=max_tokens)
        except Exception:
            pass
    if ctx is None or ctx.client is None:
        return None
    try:
        out = ctx.client.chat("local", [{"role": "user", "content": prompt}], max_tokens=max_tokens)
        c = (out.get("content") or "").strip()
        return c or None
    except Exception:
        return None


def _facts(text: str) -> list[str]:
    """Pull claim-ish fragments (numbers, named risks, constraints) for the deterministic pass."""
    out = []
    for m in re.finditer(r"[\w$./%+-]{2,}[^\n.]{0,80}?\d+[^\n.]{0,40}\.", text):
        out.append(m.group(0).strip()[:120])
    for kw in ("risk", "cost", "delay", "depend", "constraint", "budget", "deadline", "scale", "legal", "compliance"):
        for m in re.finditer(rf"[^\n.]*(?:{kw})[^\n.]*\.", text, re.I):
            out.append(m.group(0).strip()[:120])
    return list(dict.fromkeys(out))[:6]


def _deterministic(idea: str, alt_mode: bool) -> str:
    idea = re.sub(r"\s+", " ", idea.strip())
    facts = _facts(idea)
    L = ["## Stress test — " + idea[:100], ""]
    L += ["### Verdict", "- **Unverified** — no model reachable; below is the analysis scaffold with every claim extracted from your input. Re-run when Ollama is up for a true stress test.", ""]
    L += ["### What must be true (kill criteria)",
          "- State the 3 assumptions this idea depends on — if any is false, the idea fails.",
          "- Cheapest test for each: one number, one conversation, one prototype ≤ 4h.", ""]
    L += ["### Pre-mortem (it failed 6 months from now)",
          "- Most likely: execution, not concept (scope creep / integration / ownership).",
          "- Second: the constraint you didn't state above (budget, time, people).", ""]
    L += ["### Trade-offs", "| if you proceed | if you don't |", "|---|---|",
          "| opportunity cost: time/effort spent here | alternative paths stay open |",
          "| sunk cost risk | status-quo cost keeps accruing |", ""]
    L += ["### Pros / cons", "| Pros | Cons |", "|---|---|",
          "| (list only claims you can defend with a fact) | (same standard) |", ""]
    if facts:
        L += ["", "### Claims extracted from your input", ""] + [f"- {f}" for f in facts]
    if alt_mode:
        L += ["", "### Strategic alternatives (build the real choice set)",
              "1. **Do it now, small** — smallest version that tests the kill criteria.",
              "2. **Defer + option** — buy a 2-week option (research/prototype) with a decision date.",
              "3. **Do not, but capture** — park the idea; assign a trigger that would re-open it.",
              "4. **Swap** — same objective, different mechanism (what would a competitor do?)."]
    L += ["", "### Recommendation", "- Default: run the **cheapest kill-criteria test** before committing real resources."]
    return "\n".join(L)


def _save(text: str):
    from .. import paths
    d = paths.WORKSPACE / "thoughts"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{date.today().isoformat()}.md"
    from .. import safeio
    safeio.append_text(f, "\n" + text + "\n")
    return f"thoughts/{f.name}"


@register("think", "/think <idea…>   ·   /think alternatives <idea…>",
          "stress-test: pre-mortem, trade-off table, pros/cons matrix, strategic alternatives")
def think(ctx, arg: str) -> str:
    try:
        arg = arg.strip()
        if not arg:
            return "ERROR: /think <idea or decision>   (add 'alternatives' first for strategy focus)"
        alt_mode = arg.lower().startswith("alternatives")
        idea = arg[len("alternatives"):].strip() if alt_mode else arg
        if len(idea) < 12:
            return "ERROR: give the idea at least a sentence of substance (≥12 chars)"
        llm = _llm(ctx, ("Act as a demanding chief of staff. Stress-test this idea/decision. "
                         "Structure: '## Verdict' (one sharp sentence + confidence %), "
                         "'### Kill criteria' (max 3 falsifiable assumptions + cheapest test each), "
                         "'### Pre-mortem' (2-3 concrete failure stories), "
                         "'### Trade-offs' (| if proceed | if not | table), "
                         "'### Pros / cons' (| pros | cons | table, 3 rows max, no filler), "
                         + ("'### Strategic alternatives' (numbered, each with effort/risk/exit cost), " if alt_mode else "")
                         + "'### Recommendation' (what to do this week). "
                         "Be direct; disagree when the idea is weak. No praise.\n\nIDEA:\n" + idea[:6000]))
        text = llm or _deterministic(idea, alt_mode)
        return "_(saved → " + _save(text) + ")_\n\n" + text
    except Exception as e:
        return f"ERROR: /think failed safely: {type(e).__name__}: {e}"
