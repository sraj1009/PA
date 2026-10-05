"""/summarize — articles, papers, reports → executive summary + dense bullets + table.

Usage:
  /summarize <url>            fetch and summarize (HTML stripped client-side)
  /summarize file <path>      summarize a local file (md/txt/csv/code/log)
  /summarize <text…>          summarize inline text (paste)

Output: TL;DR → dense bullets → comparative markdown table (when entities/numbers
are present). LLM-driven when reachable; extractive frequency ranking as floor.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import date
from pathlib import Path

from . import register

STOP = set("a an the and or but if then else of to in on at by for with about into over under per via is are was were be been being this that these those it its as not no yes we you they he she i our your their can will would could should may might must do does did have has had so than too very just".split())
SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
TAG_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
HTML_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def _fetch_url(url: str) -> str:
    import httpx
    r = httpx.get(url, follow_redirects=True, timeout=20,
                  headers={"User-Agent": "Mozilla/5.0 (BEE local assistant)"})
    r.raise_for_status()
    t = TAG_RE.sub(" ", r.text)
    t = HTML_RE.sub(" ", t)
    return WS_RE.sub(" ", t).strip()[:12000]


def _read_file(p: str) -> str:
    fp = Path(p)
    if not fp.is_absolute():
        from .. import paths
        fp = paths.WORKSPACE / fp
    fp = fp.resolve()
    return fp.read_text(encoding="utf-8", errors="ignore")[:12000]


def _sentences(text: str) -> list[str]:
    parts = [s.strip() for s in SENT_RE.split(text.strip())]
    return [s for s in parts if len(s) > 25][:200]


def _extractive(text: str, n: int = 8) -> tuple[str, list[str]]:
    sents = _sentences(text)
    words = Counter(w.lower() for w in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{3,}", text) if w.lower() not in STOP)
    if not words or not sents:
        return text[:200], []
    def score(s):
        ws = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{3,}", s)
        return sum(words[w.lower()] for w in ws) / (len(ws) ** 0.5 or 1)
    ranked = sorted(enumerate(sents), key=lambda p: -score(p[1]))[:n]
    bullets = [sents[i] for i, _ in sorted(ranked)]
    tldr = sents[0][:220]
    return tldr, bullets


def _table(text: str) -> str:
    """Comparative table of entity→number pairs (metrics, prices, versions)."""
    pairs: list[tuple[str, str]] = []
    for m in re.finditer(r"([A-Za-z][A-Za-z0-9_ ./-]{1,40}?)\s*[:\-–]?\s*(\d+(?:[.,]\d+)*(?:\s?(?:%|x|gb|mb|tb|k|mn|usd|€|£|days|weeks|months|hours|tok/s|rps))?)\b", text, re.I):
        key = m.group(1).strip(" .-")
        if key.lower() in STOP or len(key) < 3:
            continue
        pairs.append((key, m.group(2).strip()))
    seen, rows = set(), []
    for k, v in pairs:
        if k.lower() in seen or len(v) > 20:
            continue
        seen.add(k.lower())
        rows.append(f"| {k} | {v} |")
    if len(rows) < 2:
        return ""
    return "### Key figures\n\n| Item | Value |\n|---|---|\n" + "\n".join(rows[:12])


def _llm(ctx, prompt: str, max_tokens: int = 1000) -> str | None:
    # Phase 2: commands execute LLM work through the SAME kernel as main tasks
    # (provider routing, receipts, events, telemetry). The fallback keeps bare
    # ctx objects working (tests without a kernel).
    kernel = getattr(ctx, "kernel", None)
    if kernel is not None:
        try:
            return kernel.direct("summarize", prompt, max_tokens=max_tokens)
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


@register("summarize", "/summarize <url | file <path> | text…>",
          "dense bullets + executive summary + comparative table (articles, papers, reports)")
def summarize(ctx, arg: str) -> str:
    try:
        arg = arg.strip()
        if not arg:
            return "ERROR: /summarize <url | file <path> | pasted text>"
        source = arg
        if arg.lower().startswith(("http://", "https://")):
            text = _fetch_url(arg)
            source = arg[:90]
        elif arg.split(None, 1)[0].lower() == "file":
            p = arg.split(None, 1)[1].strip() if " " in arg else ""
            text = _read_file(p)
            source = p
        else:
            text = arg
            source = f"inline text ({len(arg)} chars)"
        text = re.sub(r"\s+", " ", text)
        if len(text) < 40:
            return "ERROR: input too short to summarize (need ≥40 chars)"
        llm = _llm(ctx, "Summarize the content below. Output EXACTLY this markdown structure, no preamble:\n"
                        "## TL;DR\n<one dense sentence>\n## Key points\n<5-9 bullets, highest signal first, keep numbers/names>\n"
                        "## Comparative table\n| dimension | a | b |\n<only if ≥2 comparable entities/numbers exist; else 'n/a'>\n\n---\nCONTENT:\n"
                        + text[:8000])
        if llm:
            body = llm
        else:
            tldr, bullets = _extractive(text)
            body = ("## TL;DR\n" + tldr + "\n\n## Key points\n"
                    + "\n".join(f"- {b[:220]}" for b in bullets) + "\n\n## Comparative table\n"
                    + (_table(text) or "_no comparable figures detected_"))
        d = Path(__import__("bee", fromlist=["paths"]).paths.WORKSPACE / "sums")
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"{date.today().isoformat()}.md"
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(f"\n---\n### {source}\n\n{body}\n")
        return f"_(source: {source} · appended → sums/{f.name})_\n\n{body}"
    except Exception as e:
        return f"ERROR: /summarize failed safely: {type(e).__name__}: {e}"
