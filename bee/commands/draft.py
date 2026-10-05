"""/draft — emails, memos, outreach, proposals, reports + note extraction.

Usage:
  /draft email <content…> [tone: formal|friendly|assertive|apologetic]
  /draft memo    <content…>  [tone: …]
  /draft outreach <content…> [tone: …]
  /draft proposal <content…> [tone: …]
  /draft report  <content…>  [tone: …]
  /draft extract <messy notes or transcript…>

Extract finds: key decisions, action items, owners, follow-ups (dates/next steps).
LLM rewrites when reachable; a deterministic template floor always works.
Output persists to drafts/.
"""
from __future__ import annotations

import re
from datetime import date

from . import register

KINDS = ("email", "memo", "outreach", "proposal", "report", "extract")
TONE_RE = re.compile(r"\[?tone\s*:\s*([a-z]+)\]?\s*$", re.I)
TONE_DEF = {
    "email": "professional, crisp, one page max",
    "memo": "internal, structured, decision-first",
    "outreach": "warm but concise, value-first, soft CTA",
    "proposal": "confident, structured, benefit-led, clear ask",
    "report": "factual, dense, numbers up front, no adjectives",
}
OWNER_RE = re.compile(r"\b([A-Z][a-z]{2,}(?:\s[A-Z][a-z]{2,})?)\s+(?:to\s|will\s|owns?|is (?:owning|handling)|needs (?:to|to))", )
DECISION_RE = re.compile(r"\b(decided|agreed|settled on|go(ing)? with|approved|rejected|locked|final(ized)?)\b", re.I)
ACTION_RE = re.compile(r"\b((?:need|must|should|have to|going to|will)\s|todo|action|next step|follow.?up|send|email|call|schedule|prepare|review|submit)\b", re.I)
FOLLOWUP_RE = re.compile(r"\b(follow.?up|next (?:step|call|meeting)|by (?:end of|eod|tomorrow|friday|monday|\w+day)?\s*\w+|next week|tomorrow|tuesday|wednesday|thursday|friday|eod|co[wv])\b", re.I)


def _llm(ctx, prompt: str, max_tokens: int = 900) -> str | None:
    # Phase 2: commands execute LLM work through the SAME kernel as main tasks
    # (provider routing, receipts, events, telemetry). The fallback keeps bare
    # ctx objects working (tests without a kernel).
    kernel = getattr(ctx, "kernel", None)
    if kernel is not None:
        try:
            return kernel.direct("draft", prompt, max_tokens=max_tokens)
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


def _split(arg: str) -> tuple[str, str, str]:
    """-> (kind, body, tone). Kind = first word if it is a known kind."""
    m = TONE_RE.search(arg)
    tone = m.group(1).lower() if m else "professional"
    body = arg[: m.start()].strip() if m else arg.strip()
    first = body.split(None, 1)
    if first and first[0].lower() in KINDS:
        return first[0].lower(), (first[1].strip() if len(first) > 1 else ""), tone
    return "email", body, tone


def _deterministic(kind: str, body: str, tone: str) -> str:
    body = body.strip()
    if kind == "extract":
        return _extract_fallback(body)
    if kind == "email":
        subj = re.sub(r"\s+", " ", body.splitlines()[0][:80]) if body else "Re: —"
        return (
            f"**Subject:** {subj}\n\n"
            f"Hi [name],\n\n{body}\n\n"
            f"Next step: confirm by end of week.\n\n"
            f"Best regards,\n[signature]\n\n---\n_tone: {tone} — deterministic template (no model reachable). Paste this into any editor._"
        )
    if kind == "memo":
        return (f"## MEMO — {date.today().isoformat()}\n\n**To:** [team]  **From:** [you]  **Re:** {body.splitlines()[0][:70] if body else '—'}\n\n"
                f"**Decision:** {body.splitlines()[0] if body else '—'}\n\n**Context**\n{body}\n\n"
                f"**Asks**\n- [ ] Owners confirm by EOD")
    if kind == "outreach":
        return (f"**Subject:** {body.splitlines()[0][:70] if body else 'Quick question'}\n\n"
                f"Hi [first name],\n\n{body}\n\n"
                f"Worth a 15-minute call? Happy to work around your schedule.\n\n[signature]")
    if kind == "proposal":
        return (f"## Proposal — {body.splitlines()[0][:80] if body else 'Untitled'}\n\n"
                f"### 1. Problem\n{body}\n\n### 2. Proposed approach\n[2–4 numbered steps]\n\n"
                f"### 3. Benefits\n- [quantified where possible]\n\n### 4. Ask / next step\n[decision requested + date]")
    # report
    return (f"## Report — {date.today().isoformat()}\n\n**TL;DR:** {body.splitlines()[0][:120] if body else '—'}\n\n"
            f"### Findings\n{body}\n\n### Recommendations\n1. [highest-impact action]")


def _extract_fallback(body: str) -> str:
    decisions, actions, owners, followups = [], [], [], []
    for ln in re.split(r"[\n.;]+", body):
        ln = ln.strip()
        if len(ln) < 6:
            continue
        low = ln.lower()
        if DECISION_RE.search(ln) and "decision:" not in low:
            decisions.append(ln)
        if ACTION_RE.search(ln):
            actions.append(ln)
        m = OWNER_RE.search(ln)
        if m and (ACTION_RE.search(ln) or "owner" in low):
            owners.append(f"**{m.group(1)}** — {ln[:110]}")
        if FOLLOWUP_RE.search(ln):
            followups.append(ln)
    def section(title, items, fallback):
        return f"### {title}\n" + ("\n".join(f"- {i[:160]}" for i in dict.fromkeys(items[:15])) if items else f"- {fallback}")
    return (f"## Extracted from notes ({date.today().isoformat()})\n\n"
            + section("Key decisions", decisions, "none detected") + "\n\n"
            + section("Action items", actions, "none detected") + "\n\n"
            + section("Owners", owners, "none detected") + "\n\n"
            + section("Follow-ups", followups, "none detected"))


@register("draft", "/draft <email|memo|outreach|proposal|report|extract> <content…> [tone: X]",
          "write in the requested tone; extract decisions/actions/owners/follow-ups from messy notes")
def draft(ctx, arg: str) -> str:
    try:
        kind, body, tone = _split(arg)
        if not body:
            return "ERROR: /draft <email|memo|outreach|proposal|report|extract> <content> [tone: X]"
        if kind == "extract":
            text = _llm(ctx, "Extract from these raw meeting notes/transcript. Return ONLY markdown with four "
                             "sections: '### Key decisions', '### Action items' (verb-first), '### Owners' "
                             "(bold name — item), '### Follow-ups' (with dates). Be faithful; do not invent.\n\n"
                             f"{body[:6000]}")
        else:
            text = _llm(ctx, f"Write a {kind} in a {tone} tone ({TONE_DEF[kind]}). Use only facts present in the "
                             f"input; placeholders like [name] for unknowns. No preamble, no 'here is your email'. "
                             f"Markdown.\n\nInput:\n{body[:6000]}")
        text = text or _deterministic(kind, body, tone)
        # persist
        from .. import paths
        d = paths.WORKSPACE / "drafts"
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"{date.today().isoformat()}-{kind}.md"
        n = 1
        while f.exists():
            f = d / f"{date.today().isoformat()}-{kind}-{n}.md"
            n += 1
        f.write_text(text, encoding="utf-8")
        return f"_(saved → drafts/{f.name})_\n\n{text}"
    except Exception as e:
        return f"ERROR: /draft failed safely: {type(e).__name__}: {e}"
