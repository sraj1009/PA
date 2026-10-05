"""automate — reusable Python automation recipes (safe, workspace-scoped).

Covers the common "just automate this" tasks a PA gets: directory inventory,
batch rename (dry-run default), CSV/JSONL/TSV conversion, line dedupe,
head/tail/sort/grep, and template placeholder fill. Every path is confined to
the workspace so the tool can never touch files outside BEE's sandbox.
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass
class T:
    name: str
    description: str
    parameters: dict
    handler: object


def _resolve(ctx, path: str) -> Path:
    """Confine a path to the workspace (reject escapes like ../../etc)."""
    base = Path(ctx.workspace).resolve()
    p = Path(path)
    if not p.is_absolute():
        p = base / p
    p = p.resolve()
    if p != base and base not in p.parents:
        raise ValueError(f"path escapes workspace: {path}")
    return p


def _inventory(ctx, path):
    root = _resolve(ctx, path)
    if not root.exists():
        return {"error": f"not found: {path}"}
    if root.is_file():
        return {"error": "inventory needs a directory, not a file"}
    files = [f for f in root.rglob("*") if f.is_file()]
    by_ext = Counter(f.suffix.lower() or "(none)" for f in files)
    total = sum(f.stat().st_size for f in files)
    largest = sorted(((f.stat().st_size, str(f.relative_to(root))) for f in files), reverse=True)[:10]
    return {"path": str(root), "file_count": len(files), "total_bytes": total,
            "total_mb": round(total / 1048576, 3), "by_extension": dict(by_ext.most_common()),
            "largest": [{"bytes": b, "rel": r} for b, r in largest]}


def _rename(ctx, path, pattern, replacement, use_regex=False, dry_run=True):
    root = _resolve(ctx, path)
    if not root.is_dir():
        return {"error": "rename needs a directory"}
    if use_regex:
        try:
            rx = re.compile(pattern)
        except re.error as e:
            return {"error": f"bad regex: {e}"}
    changed = []
    for f in sorted(root.iterdir()):
        if not f.is_file():
            continue
        new_name = rx.sub(replacement, f.name) if use_regex else f.name.replace(pattern, replacement)
        if new_name == f.name:
            continue
        if f.with_name(new_name).exists():
            changed.append({"skip": f.name, "reason": f"{new_name} already exists"})
            continue
        if dry_run:
            changed.append({"would": f"{f.name} -> {new_name}"})
        else:
            f.rename(f.with_name(new_name))
            changed.append({"did": f"{f.name} -> {new_name}"})
    return {"dry_run": bool(dry_run), "changed": len(changed), "detail": changed}


def _convert(ctx, path, from_format, to_format):
    p = _resolve(ctx, path)
    if not p.is_file():
        return {"error": "convert needs a file"}
    from_format = (from_format or p.suffix.lstrip(".")).lower()
    to_format = (to_format or "").lower()
    if from_format in ("csv",):
        data = list(csv.DictReader(open(p, newline="", encoding="utf-8-sig")))
    elif from_format in ("jsonl", "ndjson"):
        data = [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    elif from_format == "tsv":
        data = list(csv.DictReader(open(p, newline="", encoding="utf-8-sig"), delimiter="\t"))
    else:
        return {"error": f"unsupported from_format: {from_format}"}
    out = p.with_suffix("." + to_format)
    if to_format == "csv":
        with open(out, "w", newline="", encoding="utf-8") as fh:
            if data:
                w = csv.DictWriter(fh, fieldnames=list(data[0].keys())); w.writeheader(); w.writerows(data)
    elif to_format == "jsonl":
        out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in data), encoding="utf-8")
    elif to_format == "tsv":
        with open(out, "w", newline="", encoding="utf-8") as fh:
            if data:
                w = csv.DictWriter(fh, fieldnames=list(data[0].keys()), delimiter="\t"); w.writeheader(); w.writerows(data)
    else:
        return {"error": f"unsupported to_format: {to_format}"}
    return {"rows": len(data), "from": from_format, "to": to_format, "out": str(out)}


def _dedupe(ctx, path, in_place=False):
    p = _resolve(ctx, path)
    if not p.is_file():
        return {"error": "dedupe needs a file"}
    lines = p.read_text(encoding="utf-8").splitlines()
    seen, out = set(), []
    for ln in lines:
        if ln not in seen:
            seen.add(ln); out.append(ln)
    removed = len(lines) - len(out)
    target = p if in_place else p.with_name(p.stem + ".deduped" + p.suffix)
    target.write_text("\n".join(out) + ("\n" if out else ""), encoding="utf-8")
    return {"lines_in": len(lines), "lines_out": len(out), "removed": removed, "out": str(target)}


def _lines(ctx, path, head=None, tail=None, sort=False, unique=False, contains=None):
    p = _resolve(ctx, path)
    if not p.is_file():
        return {"error": "lines needs a file"}
    lines = p.read_text(encoding="utf-8").splitlines()
    if contains is not None:
        lines = [ln for ln in lines if contains in ln]
    if unique:
        lines = list(dict.fromkeys(lines))
    if sort:
        lines = sorted(lines)
    if tail is not None:
        n = int(tail); lines = lines[-n:] if n > 0 else []
    if head is not None:
        lines = lines[:int(head)]
    return {"count": len(lines), "lines": lines[:200], "truncated": len(lines) > 200}


def _fill(ctx, path, mapping, dry_run=True):
    p = _resolve(ctx, path)
    if not p.is_file():
        return {"error": "fill needs a file"}
    text = p.read_text(encoding="utf-8")
    for k, v in (mapping or {}).items():
        text = text.replace("{{" + str(k) + "}}", str(v)).replace("$" + str(k), str(v))
    if dry_run:
        return {"dry_run": True, "preview": text[:2000]}
    p.write_text(text, encoding="utf-8")
    return {"filled": True, "out": str(p)}


def _jsonq(ctx, path, jq):
    """Extract from a .json/.jsonl file by a jq-lite path: a.b[0].c  (* = all)."""
    p = _resolve(ctx, path)
    if not p.is_file():
        return {"error": "jsonq needs a file"}
    text = p.read_text(encoding="utf-8")
    stripped = text.lstrip()
    if p.suffix.lower() in (".jsonl", ".ndjson") or (stripped[:1] in "{[" and stripped.count("\n") > 0):
        roots = [json.loads(ln) for ln in text.splitlines() if ln.strip()]
    else:
        try:
            roots = [json.loads(text)]
        except json.JSONDecodeError as e:
            return {"error": f"bad json: {e}"}
    tokens = re.findall(r"[\w\-*]+|\[\d+\]", jq or "")
    if not tokens:
        return {"error": "jsonq needs a path like a.b[0].c"}

    def walk(node, toks):
        if not toks:
            return [node]
        t = toks[0]
        if t == "*":
            out = []
            seq = node if isinstance(node, list) else (list(node.values()) if isinstance(node, dict) else [])
            for it in seq:
                out += walk(it, toks[1:])
            return out
        if t.startswith("["):
            idx = int(t[1:-1])
            if isinstance(node, list) and -len(node) <= idx < len(node):
                return walk(node[idx], toks[1:])
            return []
        if isinstance(node, dict) and t in node:
            return walk(node[t], toks[1:])
        return []

    results = []
    for r in roots:
        results += walk(r, tokens)
    return {"matches": len(results), "values": results[:200], "truncated": len(results) > 200}


def _count(ctx, path, pattern=None, mode="lines"):
    p = _resolve(ctx, path)
    if not p.is_file():
        return {"error": "count needs a file"}
    text = p.read_text(encoding="utf-8", errors="replace")
    out = {"mode": mode}
    if mode == "pattern":
        if not pattern:
            return {"error": "pattern mode requires 'pattern'"}
        out["lines_matching"] = sum(1 for ln in text.splitlines() if pattern in ln)
        out["occurrences"] = text.count(pattern)
    else:
        out["lines"] = len(text.splitlines())
        out["words"] = len(text.split())
        out["chars"] = len(text)
        if pattern:
            out["lines_matching"] = sum(1 for ln in text.splitlines() if pattern in ln)
    return out


def _find(ctx, path, glob, contains=None, max_results=100):
    root = _resolve(ctx, path)
    if not root.is_dir():
        return {"error": "find needs a directory"}
    hits = []
    for f in root.rglob(glob or "*"):
        if not f.is_file():
            continue
        if contains is not None:
            try:
                if contains not in f.read_text(encoding="utf-8", errors="replace"):
                    continue
            except Exception:
                continue
        hits.append({"rel": str(f.relative_to(root)), "bytes": f.stat().st_size})
        if len(hits) >= max_results:
            break
    return {"count": len(hits), "truncated": len(hits) >= max_results, "files": hits}


def _zip(ctx, path, mode, archive=None):
    import zipfile
    p = _resolve(ctx, path)
    if mode == "create":
        if not p.exists():
            return {"error": "zip create needs an existing file/dir"}
        arc = _resolve(ctx, archive) if archive else p.with_name(p.name + ".zip")
        with zipfile.ZipFile(arc, "w", zipfile.ZIP_DEFLATED) as z:
            if p.is_file():
                z.write(p, p.name)
            else:
                for f in p.rglob("*"):
                    if f.is_file() and f != arc:  # never zip the archive into itself
                        z.write(f, str(f.relative_to(p.parent)))
        return {"created": str(arc), "bytes": arc.stat().st_size}
    if mode == "extract":
        if not p.is_file():
            return {"error": "zip extract needs an archive file"}
        dest = _resolve(ctx, archive) if archive else p.with_name(p.stem)
        dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(p) as z:
            for member in z.namelist():
                target = (dest / member).resolve()
                if dest != target and dest not in target.parents:
                    return {"error": f"unsafe member path (zip-slip): {member}"}
            z.extractall(dest)
        return {"extracted_to": str(dest)}
    return {"error": f"unknown zip mode: {mode}", "valid": ["create", "extract"]}


def _run(ctx, action, path=None, **kw):
    try:
        if action == "inventory":
            return _inventory(ctx, path)
        if action == "jsonq":
            return _jsonq(ctx, path, kw.get("jq", ""))
        if action == "count":
            return _count(ctx, path, kw.get("pattern"), kw.get("mode", "lines"))
        if action == "find":
            return _find(ctx, path, kw.get("glob", "*"), kw.get("contains"),
                         int(kw.get("max_results", 100)))
        if action == "zip":
            return _zip(ctx, path, kw.get("mode", "create"), kw.get("archive"))
        if action == "rename":
            return _rename(ctx, path, kw.get("pattern", ""), kw.get("replacement", ""),
                           bool(kw.get("use_regex")), bool(kw.get("dry_run", True)))
        if action == "convert":
            return _convert(ctx, path, kw.get("from_format"), kw.get("to_format"))
        if action == "dedupe":
            return _dedupe(ctx, path, bool(kw.get("in_place")))
        if action == "lines":
            return _lines(ctx, path, kw.get("head"), kw.get("tail"),
                          bool(kw.get("sort")), bool(kw.get("unique")), kw.get("contains"))
        if action == "fill":
            return _fill(ctx, path, kw.get("mapping"), bool(kw.get("dry_run", True)))
        return {"error": f"unknown action: {action}",
                "valid": ["inventory", "rename", "convert", "dedupe", "lines", "fill",
                          "jsonq", "count", "find", "zip"]}
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def automate_tools():
    props = {
        "action": {"type": "string", "enum": ["inventory", "rename", "convert", "dedupe", "lines", "fill", "jsonq", "count", "find", "zip"]},
        "path": {"type": "string", "description": "file or directory, relative to the workspace"},
        "pattern": {"type": "string", "description": "rename: text or regex to find"},
        "replacement": {"type": "string", "description": "rename: replacement text"},
        "use_regex": {"type": "boolean"},
        "dry_run": {"type": "boolean", "description": "default true for rename/fill"},
        "from_format": {"type": "string", "enum": ["csv", "jsonl", "tsv"]},
        "to_format": {"type": "string", "enum": ["csv", "jsonl", "tsv"]},
        "in_place": {"type": "boolean"},
        "head": {"type": "integer"},
        "tail": {"type": "integer"},
        "sort": {"type": "boolean"},
        "unique": {"type": "boolean"},
        "contains": {"type": "string"},
        "mapping": {"type": "object", "description": "fill: placeholder -> value"},
        "jq": {"type": "string", "description": "jsonq: jq-lite path, e.g. a.b[0].c (* = all)"},
        "mode": {"type": "string", "enum": ["lines", "pattern", "create", "extract"]},
        "glob": {"type": "string", "description": "find: filename glob (e.g. *.py)"},
        "max_results": {"type": "integer"},
        "archive": {"type": "string", "description": "zip: target archive/dest path"},
    }
    return [
        T("automate",
          "Run a reusable Python automation recipe (workspace-scoped & safe). "
          "inventory: directory stats (count, size, by-extension, largest files). "
          "rename: batch rename in a dir (pattern/replacement, optional regex; dry_run default true). "
          "convert: convert CSV<->JSONL<->TSV. dedupe: remove duplicate lines. "
          "lines: head/tail/sort/unique/contains(=grep) a file. "
           "fill: replace {{key}} or $key placeholders in a template (dry_run default true). "
           "jsonq: extract values from JSON/JSONL by a jq-lite path (a.b[0].c, * = all). "
           "count: line/word/char counts, or pattern occurrence/line counts (mode=pattern). "
           "find: list files by glob, optionally filtered by content (contains). "
           "zip: create or extract an archive (mode=create|extract; zip-slip guarded). "
           "Args: action (required), path (required), plus action-specific fields.",
          {"type": "object", "properties": props, "required": ["action", "path"]},
          _run),
    ]
