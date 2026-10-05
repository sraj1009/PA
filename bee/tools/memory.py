"""Memory tools: diary (episodic), longterm (durable facts), profile, search."""
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
        with day.open("a", encoding="utf-8") as f:
            f.write(f"\n## {datetime.now():%H:%M:%S}{extra}\n{msg}\n")
        return {"ok": True, "file": str(day), "chars": len(msg)}

    def h_longterm(ctx, text: str, append: bool = True):
        from .. import paths
        t = str(text or "").strip()
        if not t:
            return {"error": "empty text"}
        p = paths.LONGTERM_MD
        if append and p.exists():
            cur = p.read_text(encoding="utf-8").rstrip()
            p.write_text(cur + f"\n\n- {t}\n", encoding="utf-8")
        else:
            p.write_text(f"# Long-term memory\n\n- {t}\n", encoding="utf-8")
        return {"ok": True, "file": str(p)}

    def h_profile(ctx, text: str):
        from .. import paths
        t = str(text or "").strip()
        if not t:
            return {"error": "empty text"}
        p = paths.PROFILE_MD
        cur = p.read_text(encoding="utf-8") if p.exists() else ""
        p.write_text(cur.rstrip() + f"\n- {t}\n", encoding="utf-8")
        return {"ok": True, "file": str(p)}

    def h_search(ctx, query: str, k: int = 6):
        from ..memory import md
        q = str(query or "").strip()
        if not q:
            return {"error": "empty query"}
        k = max(1, min(int(k or 6), 15))
        return {"query": q, "results": md.memory_search(ctx, q, k=k)}

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
