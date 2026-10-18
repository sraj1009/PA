"""Memory tools: diary (episodic), longterm (durable facts), profile, search.

P1-7: writes executed while `ctx.untrusted_active` (external content ingested
this turn) are provenance-tagged `[source: untrusted-turn]`, may not update or
wipe existing memory (`add_facts(protect=True)`), and record a `memory_write`
metrics row. The diary is deliberately left untagged: it is never indexed for
recall.
"""
from __future__ import annotations

from datetime import datetime
from .base import T

def memory_tools():
    def h_diary(ctx, message: str, model: str = "", escalated: bool = False):
        from .. import paths
        msg = str(message or "").strip()
        if not msg:
            return {"error": "empty message"}
        day = paths.DIARY_DIR / f"{datetime.now():%Y-%m-%d}.md"
        day.parent.mkdir(parents=True, exist_ok=True)
        extra = f" [model={model}{'|cloud' if escalated else ''}]" if model else ""
        from .. import safeio
        safeio.append_text(day, f"\n## {datetime.now():%H:%M:%S}{extra}\n{msg}\n")
        return {"ok": True, "file": str(day), "chars": len(msg)}

    def h_longterm(ctx, text: str, append: bool = True):
        from .. import paths
        from ..memory import md
        t = str(text or "").strip()
        if not t:
            return {"error": "empty text"}
        untrusted = bool(getattr(ctx, "untrusted_active", False))
        if untrusted and not append:
            # P1-7: a wipe proposed while untrusted content is in play is the
            # tamest-looking way to destroy memory — refuse outright, don't
            # tag what should not happen at all.
            from ..monitor import metrics
            metrics.record("memory_write", file=str(paths.LONGTERM_MD),
                           untrusted=True, refused="wipe")
            return {"ok": False, "file": str(paths.LONGTERM_MD),
                    "error": "refused: wiping memory while untrusted content is "
                             "active — ask the user in a fresh turn"}
        if not append:
            paths.LONGTERM_MD.write_text("# Long-term memory\n", encoding="utf-8")
        if untrusted:
            t = f"{t} {md.UNTRUSTED_TAG}"
        out = md.add_facts(paths.LONGTERM_MD, t, protect=untrusted)
        if untrusted:
            from ..monitor import metrics
            metrics.record("memory_write", file=str(paths.LONGTERM_MD),
                           untrusted=True, added=out["added"],
                           updated=out["updated"], skipped=out["skipped"])
        res = {"ok": True, "file": str(paths.LONGTERM_MD),
               "added": out["added"], "updated": out["updated"],
               "already_there": out["duplicates"]}
        if untrusted:
            res["skipped"] = out["skipped"]
        return res

    def h_profile(ctx, text: str):
        from .. import paths
        from ..memory import md
        t = str(text or "").strip()
        if not t:
            return {"error": "empty text"}
        untrusted = bool(getattr(ctx, "untrusted_active", False))
        if untrusted:
            t = f"{t} {md.UNTRUSTED_TAG}"
        out = md.add_facts(paths.PROFILE_MD, t, protect=untrusted)
        if untrusted:
            from ..monitor import metrics
            metrics.record("memory_write", file=str(paths.PROFILE_MD),
                           untrusted=True, added=out["added"],
                           updated=out["updated"], skipped=out["skipped"])
        res = {"ok": True, "file": str(paths.PROFILE_MD),
               "added": out["added"], "updated": out["updated"],
               "already_there": out["duplicates"]}
        if untrusted:
            res["skipped"] = out["skipped"]
        return res

    def h_search(ctx, query: str, k: int = 6):
        from ..memory import md
        q = str(query or "").strip()
        if not q:
            return {"error": "empty query"}
        k = max(1, min(int(k or 6), 15))
        rows = []
        for r in md.memory_search(ctx, q, k=k):
            text, flagged = md.mark_untrusted_lines(r.get("text", ""))
            row = {**r, "text": text}
            if flagged:
                row["untrusted_origin"] = True
            rows.append(row)
        return {"query": q, "results": rows}

    return [
        T("diary_add", "Append a timestamped episodic note to today's diary (memory/diary/YYYY-MM-DD.md). "
                      "Use after finishing tasks or when the user says 'remember X'. Args: message, model (optional note).",
          {"type": "object", "properties": {"message": {"type": "string"}, "model": {"type": "string"}},
           "required": ["message"]}, h_diary),
        T("memory_longterm", "Add a Durable fact to long-term memory (memory/longterm.md). Use for decisions, preferences, "
                             "credentials-of-use, project facts that must survive across sessions. Args: text, append (default true).",
          {"type": "object", "properties": {"text": {"type": "string"}, "append": {"type": "boolean"}},
           "required": ["text"]}, h_longterm),
        T("profile_add", "Record a user-preference/profile fact (memory/profile.md). Args: text.",
          {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}, h_profile),
        T("memory_search", "Search all memory (diary, lessons, profile, longterm) for a query. Returns ranked chunks. "
                           "Args: query, k (default 6).",
          {"type": "object", "properties": {"query": {"type": "string"}, "k": {"type": "integer"}},
           "required": ["query"]}, h_search),
    ]
