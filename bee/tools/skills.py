"""Skill library (Voyager-style): skills/<name>/SKILL.md + optional script.py.

The agent distills novel solutions into skills; the skill index is in the
system prompt, full content is loaded on demand via skill_get.
"""
from __future__ import annotations

import re
from pathlib import Path
from .base import T

from .. import paths

def _skill_dir(name: str) -> Path:
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", str(name or "").strip())
    if not name:
        raise ValueError("skill name required")
    d = paths.SKILLS_DIR / name
    if not d.exists() and not d.parent.exists():
        raise ValueError(f"unknown skill: {name}")
    return d

TEMPLATE = """# {name}

description: {description}

## When to use
{description}

## How
1. (steps — be concrete; include commands/code the agent can run as-is)

## Gotchas
- (pitfalls, VRAM/time limits, edge cases)
"""

def skill_tools():
    def h_list(ctx):
        out = []
        for md in sorted(paths.SKILLS_DIR.glob("*/SKILL.md")):
            body = md.read_text(encoding="utf-8", errors="ignore")
            desc = ""
            for ln in body.splitlines():
                if ln.lower().startswith("description:"):
                    desc = ln.split(":", 1)[1].strip()
                    break
            files = [p.name for p in md.parent.iterdir() if p.is_file() and p.name != "meta.json"]
            out.append({"name": md.parent.name, "description": desc, "files": files,
                        **_meta_brief(md.parent.name)})
        return {"skills": out}

    def _meta_brief(name: str) -> dict:
        try:
            from ..evals.skillgate import read_meta
            m = read_meta(name)
            return {"version": m.get("version", 1), "status": m.get("status", "active")}
        except Exception:
            return {"version": 1, "status": "active"}

    def h_get(ctx, name: str):
        try:
            d = _skill_dir(name)
        except ValueError as e:
            return {"error": str(e)}
        md = d / "SKILL.md"
        if not md.exists():
            return {"error": f"{name} has no SKILL.md"}
        extra = []
        for p in d.iterdir():
            if p.is_file() and p.name not in ("SKILL.md", "meta.json"):
                extra.append(p.name)
        return {"name": d.name, "content": md.read_text(encoding="utf-8", errors="ignore")[:12000],
                "other_files": extra, "path": str(d), **_meta_brief(d.name)}

    def h_create(ctx, name: str, description: str, content: str = "", script: str = ""):
        try:
            d = _skill_dir(name)
        except ValueError as e:
            return {"error": str(e)}
        d.mkdir(parents=True, exist_ok=True)
        md = d / "SKILL.md"
        if content:
            md.write_text(str(content), encoding="utf-8")
        elif not md.exists():
            md.write_text(TEMPLATE.format(name=name, description=description or name), encoding="utf-8")
        if script:
            (d / "script.py").write_text(str(script), encoding="utf-8")
        # J2: every create/update bumps the version and marks the skill
        # CANDIDATE — it ships (enters the prompt) only after the gate
        # (structural check + eval probe) passes, via the nightly skill_gate
        # job or `/skillgate`.
        try:
            from ..evals.skillgate import bump_skill
            meta = bump_skill(d.name, source="agent")
            return {"ok": True, "path": str(d), "skill": d.name,
                    "version": meta["version"], "status": "candidate",
                    "note": "candidate — hidden from the prompt until it passes the skill gate"}
        except Exception:
            return {"ok": True, "path": str(d), "skill": d.name}

    def h_search(ctx, query: str):
        q = str(query or "").lower()
        out = []
        for md in paths.SKILLS_DIR.glob("*/SKILL.md"):
            body = md.read_text(encoding="utf-8", errors="ignore").lower()
            score = body.count(q) * 2 + sum(body.split() and 0 for _ in [])
            if any(t in body for t in q.split()):
                score += len([t for t in q.split() if t in body])
            if score > 0:
                out.append({"name": md.parent.name, "score": score})
        out.sort(key=lambda x: -x["score"])
        return {"query": query, "matches": out[:10]}

    return [
        T("skill_list", "List all available skills with descriptions and files.",
          {"type": "object", "properties": {}, "required": []}, h_list),
        T("skill_get", "Load a skill's full SKILL.md content by name. Use after seeing the skill index in your system prompt.",
          {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}, h_get),
        T("skill_create", "Create or update a skill (SKILL.md + optional script.py). Distill NOVEL, reusable solutions into skills — "
                          "this is how BEE gets permanently better. Each create/update bumps the skill version; new/changed skills are "
                          "CANDIDATEs (hidden from the prompt) until they pass the skill gate (structural check + eval probe, nightly or /skillgate). "
                          "Args: name, description, content (full markdown with a 'description:' line and ## sections, optional), script (optional python that must compile).",
          {"type": "object", "properties": {
              "name": {"type": "string"}, "description": {"type": "string"},
              "content": {"type": "string"}, "script": {"type": "string"}},
           "required": ["name", "description"]}, h_create),
        T("skill_search", "Find skills matching a query. Args: query.",
          {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}, h_search),
    ]
