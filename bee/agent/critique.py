"""Pre-finalize self-critique (Chain-of-Thought Verification) for local answers.

After the agent loop settles on a final answer but BEFORE it is verified and
shipped, the same local model re-reads its own draft against the request and
either approves it or returns a corrected full text. One bounded local call —
never a loop. Checked in order: recomputed math, every user constraint
addressed, no invented results, clear formatting.

Deliberately separate from the deterministic verifier (math recompute,
file-state, URL cross-check) and from post-task reflection (lessons for
tomorrow): this pass fixes THIS answer before the user sees it.
"""
from __future__ import annotations

import logging

log = logging.getLogger("bee.critique")

_PROMPT = (
    "You are checking your own draft answer before it is sent. Read the request, "
    "then the draft, and verify:\n"
    "1. Math: recompute every number. If any is wrong, fix it.\n"
    "2. Constraints: every explicit requirement in the request is addressed. "
    "If one was missed, add it.\n"
    "3. Honesty: nothing is claimed that the conversation did not establish. "
    "Remove or hedge invented details.\n"
    "4. Clarity: cut filler, keep structure tight.\n"
    "Reply with ONLY the corrected full answer — or the single word OK if the "
    "draft already passes all four checks. No explanation, no preamble.\n\n"
    "Request:\n{task}\n\nDraft:\n{draft}"
)


def should_critique(ctx, task: str, draft: str) -> bool:
    """Gate: operator flag, real (non-test) client, substantive draft."""
    from .client import LLMClient
    cfg = ctx.cfg
    learning = getattr(cfg, "learning", None)
    if learning is not None and not getattr(learning, "self_critique", True):
        return False
    if not isinstance(getattr(ctx, "client", None), LLMClient):
        return False  # scripted/test doubles must see an untouched call sequence
    if not (draft or "").strip():
        return False
    try:
        min_chars = int(getattr(learning, "critique_min_chars", 200) or 200)
    except Exception:
        min_chars = 200
    return len(draft) >= min_chars


def critique_answer(ctx, draft: str, task: str, emit=None) -> str:
    """One local pass. Returns the corrected answer, or the draft unchanged
    on approval, error, or any sanity-check failure (never ship a mangled
    rewrite — the draft is always the safe fallback)."""
    def _emit(ev: dict):
        if emit:
            try:
                emit(ev)
            except Exception:
                pass

    prompt = _PROMPT.format(task=(task or "")[:600], draft=draft[:4000])
    try:
        out = ctx.client.chat("local", [{"role": "user", "content": prompt}])
        text = ((out or {}).get("content") or "").strip()
    except Exception as e:
        log.debug("critique call failed, keeping draft: %s", e)
        return draft
    if not text or text.strip().lower() == "ok":
        _emit({"type": "critique", "applied": False})
        return draft
    lo, hi = int(len(draft) * 0.3), int(len(draft) * 3) + 500
    if not (lo <= len(text) <= hi):
        log.info("critique rewrite out of bounds (%d vs draft %d), keeping draft",
                 len(text), len(draft))
        _emit({"type": "critique", "applied": False, "reason": "length-bounds"})
        return draft
    _emit({"type": "critique", "applied": True})
    return text
