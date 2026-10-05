"""Filesystem tools: file_read, file_write, file_list, file_edit."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .base import envelope, truncate


def resolve(root: Path, p: str | None) -> Path:
    root = root.resolve()
    if not p:
        return root
    q = Path(p)
    target = (root / q).resolve() if not q.is_absolute() else q.resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"path escapes workspace: {p}")
    return target


def _read_file(root: Path, path: str, start: int = 0, end: int = 0, limit: int = 120000) -> dict:
    try:
        f = resolve(root, path)
    except ValueError as e:
        return {"error": str(e)}
    if not f.exists():
        return {"error": f"not found: {path}"}
    if f.is_dir():
        return {"error": f"is a directory: {path} — use file_list"}
    try:
        raw = f.read_bytes()
    except Exception as e:
        return {"error": f"read failed: {e}"}
    if not raw[:4].isascii() or b"\x00" in raw[:4096]:
        return {"error": f"binary file ({f.suffix or 'unknown'}) — use shell tools, e.g. python"}
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    total = len(lines)
    s, e2 = max(0, start), (end if end else total)
    chunk = "\n".join(lines[s:e2])
    return {"path": str(f.relative_to(root)) if root in f.parents else str(f),
            "total_lines": total, "lines": f"{s + 1}-{min(e2, total)}",
            "chars": len(chunk), "content": truncate(chunk, limit)}


def _write_file(root: Path, path: str, content: str, append: bool = False, create_dirs: bool = True) -> dict:
    try:
        f = resolve(root, path)
    except ValueError as e:
        return {"error": str(e)}
    try:
        if create_dirs:
            f.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with f.open(mode, encoding="utf-8") as fh:
            fh.write(content)
        return {"path": str(f), "chars": len(content), "mode": mode}
    except Exception as e:
        return {"error": f"write failed: {e}"}


def _file_list(root: Path, path: str = ".", max_entries: int = 300) -> dict:
    try:
        f = resolve(root, path)
    except ValueError as e:
        return {"error": str(e)}
    if not f.exists():
        return {"error": f"not found: {path}"}
    out = []
    try:
        for i, child in enumerate(sorted(f.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))):
            if i >= max_entries:
                out.append(f"... (truncated at {max_entries})")
                break
            kind = "d" if child.is_dir() else "f"
            size = "" if child.is_dir() else str(child.stat().st_size)
            out.append(f"{kind}\t{child.name}\t{size}")
    except Exception as e:
        return {"error": str(e)}
    return {"path": str(f), "entries": out}


def _edit_file(root: Path, path: str, old: str, new: str, replace_all: bool = False) -> dict:
    try:
        f = resolve(root, path)
        text = f.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"error": f"edit failed to read: {e}"}
    count = text.count(old)
    if count == 0:
        return {"error": "old_string not found (must match exactly, incl. whitespace)"}
    if count > 1 and not replace_all:
        return {"error": f"old_string found {count} times — provide more context or set replace_all=true"}
    text2 = text.replace(old, new) if replace_all else text.replace(old, new, 1)
    try:
        f.write_text(text2, encoding="utf-8")
        return {"path": str(f), "replacements": count if replace_all else 1}
    except Exception as e:
        return {"error": f"edit write failed: {e}"}


def file_tools():
    @dataclass
    class _T:
        name: str
        description: str
        parameters: dict
        handler: Callable

    def h_read(ctx, path: str = "", start: int = 0, end: int = 0, limit: int = 120000):
        return _read_file(ctx.workspace, path, start, end, limit)

    def h_write(ctx, path: str, content: str, append: bool = False, create_dirs: bool = True):
        return _write_file(ctx.workspace, path, content, append, create_dirs)

    def h_list(ctx, path: str = ".", max_entries: int = 300):
        return _file_list(ctx.workspace, path, max_entries)

    def h_edit(ctx, path: str, old: str, new: str, replace_all: bool = False):
        return _edit_file(ctx.workspace, path, old, new, replace_all)

    return [
        _T("file_read", "Read a text file from the workspace. Returns numbered-free raw content with line range. Args: path (relative to workspace), start/end (1-based line bounds), limit (max chars, default 120000).",
           {"type": "object", "properties": {
               "path": {"type": "string"}, "start": {"type": "integer"}, "end": {"type": "integer"},
               "limit": {"type": "integer"}}, "required": ["path"]}, h_read),
        _T("file_write", "Write (overwrite) or append text to a file in the workspace. Creates parent dirs. Args: path, content, append (default false), create_dirs (default true).",
           {"type": "object", "properties": {
               "path": {"type": "string"}, "content": {"type": "string"},
               "append": {"type": "boolean"}, "create_dirs": {"type": "boolean"}}, "required": ["path", "content"]}, h_write),
        _T("file_list", "List directory entries (dirs first, then files, with sizes). Args: path (default '.'), max_entries.",
           {"type": "object", "properties": {"path": {"type": "string"}, "max_entries": {"type": "integer"}}, "required": []}, h_list),
        _T("file_edit", "Exact string replacement in a file (safer/faster than rewrite). old must match exactly; if it occurs multiple times, use replace_all or more context.",
           {"type": "object", "properties": {
               "path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"},
               "replace_all": {"type": "boolean"}}, "required": ["path", "old", "new"]}, h_edit),
    ]
