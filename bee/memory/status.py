"""`python -m bee.cli memory status` / `/mem status` — memory index status.

Read-only: chunk counts per source group (the same enumeration the index
builds from), log entries the transcript filter excludes, vector-index age +
row count, and the dirty-queue length. Opens LanceDB read-only; never embeds,
never starts anything, never writes.
"""
from __future__ import annotations

import time
from pathlib import Path

from .. import paths
from . import md


def _human_age(seconds: float) -> str:
    if seconds < 120:
        return f"{int(seconds)} s"
    if seconds < 7200:
        return f"{seconds / 60:.1f} m"
    if seconds < 48 * 3600:
        return f"{seconds / 3600:.1f} h"
    return f"{seconds / 86400:.1f} d"


def _age_s(d: Path):
    try:
        if d.exists():
            newest = max((p.stat().st_mtime for p in d.iterdir()), default=None)
            if newest is not None:
                return max(0.0, time.time() - newest)
    except Exception:
        pass
    return None


def _sources() -> dict[str, list[Path]]:
    def glob(d: Path, pat: str = "*.md") -> list[Path]:
        try:
            return sorted(d.glob(pat))
        except Exception:
            return []
    return {
        "diary": glob(paths.DIARY_DIR),
        "lessons": glob(paths.LESSONS_DIR),
        "profile": [paths.PROFILE_MD],
        "longterm": [paths.LONGTERM_MD],
        "wins": [paths.MEMORY_DIR / "wins.md"],
        "skills": glob(paths.SKILLS_DIR, "*/SKILL.md"),
    }


def collect() -> dict:
    out: dict = {"sources": {}, "dropped_logs": 0, "index_age_s": _age_s(paths.VECTOR_DIR),
                 "index_rows": None, "dirty": None}
    groups = _sources()
    for name, files in groups.items():
        files_n = chunks_n = 0
        for f in files:
            try:
                if f.exists():
                    files_n += 1
                    chunks_n += len(md.chunk_md(f))
            except Exception:
                continue
        out["sources"][name] = {"files": files_n, "chunks": chunks_n}
    # Transcript sections excluded from the index (diary is the only log stream;
    # same predicate chunk_md drops, so the count matches what is NOT indexed).
    try:
        for f in groups["diary"]:
            txt = f.read_text(encoding="utf-8", errors="ignore")
            out["dropped_logs"] += sum(1 for s in md._sections(txt) if md.is_transcript(s))
    except Exception:
        pass
    # Vector-index rows: open the LanceDB table directly — no client, no embedding.
    try:
        import lancedb
        db = lancedb.connect(str(paths.VECTOR_DIR))
        if "bee_memory" in db.list_tables().tables:
            out["index_rows"] = db.open_table("bee_memory").count_rows()
    except Exception:
        pass
    try:
        from . import search
        out["dirty"] = len(search.pending_paths())
    except Exception:
        pass
    return out


def render(s: dict) -> str:
    lines = ["== memory status ==", ""]
    for name, g in (s.get("sources") or {}).items():
        lines.append(f"  {name:<9} {g['files']} file(s) · {g['chunks']} chunk(s)")
    lines.append("")
    age = s.get("index_age_s")
    rows = s.get("index_rows")
    age_s = f"{_human_age(age)} old" if isinstance(age, (int, float)) else "n/a"
    rows_s = f", {rows} rows" if isinstance(rows, int) else ""
    lines.append(f"  vector index  {age_s}{rows_s}  ({paths.VECTOR_DIR})")
    dq = s.get("dirty")
    lines.append(f"  dirty queue   {dq if isinstance(dq, int) else 'n/a'} file(s) pending embed")
    lines.append(f"  logs dropped  {s.get('dropped_logs', 0)} transcript entr(ies) "
                 f"excluded from the index")
    return "\n".join(lines)


def run(argv=None) -> int:
    """CLI `python -m bee.cli memory status` (the only subcommand today)."""
    args = [a for a in (argv or []) if a and not a.startswith("-")]
    if args and args[0] != "status":
        print("usage: python -m bee.cli memory status")
        return 2
    print(render(collect()))
    return 0
