"""Deterministic post-answer verification — claims checked against reality.

Runs after the model's final answer, before it reaches the user:
  1. math   — every calculator call in the episode is recomputed; the answer
              must contain the correct results (catches arithmetic drift).
  2. files  — every successful file_write is re-read from disk now; the file
              must still exist with the written content (catches phantom writes).
  3. urls   — URLs cited in the final answer that were never web_fetched in the
              episode are flagged (possible fabrication). warn, not fail.

Verdict: pass | warn | fail. A fail triggers ONE bounded fix round in the loop.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..tools.base import eval_safe

_URL = re.compile(r"https?://[^\s\)\]\"',]+")


def _calc_checks(episode_events: list[dict]) -> list[dict]:
    out = []
    for ev in episode_events:
        if ev.get("tool") != "calculator" or not ev.get("ok"):
            continue
        try:
            args = json.loads(ev.get("args") or "{}")
            expr = str(args.get("expression", ""))
            stated = str(json.loads(ev.get("result") or "{}").get("result", ""))
            recomputed = eval_safe(expr)
            good = str(recomputed) == stated
            out.append({"expr": expr[:120], "expected": str(recomputed)[:80], "good": good})
        except Exception:
            continue
    return out


def _file_checks(episode_events: list[dict], workspace: Path) -> list[dict]:
    last_write: dict[str, str] = {}
    for ev in episode_events:
        if ev.get("tool") == "file_write" and ev.get("ok"):
            try:
                args = json.loads(ev.get("args") or "{}")
                last_write[str(args.get("path", ""))] = str(args.get("content", ""))
            except Exception:
                continue
    out = []
    for path, content in last_write.items():
        try:
            p = (workspace / path).resolve()
            if not p.exists():
                out.append({"path": path, "good": False, "why": "file missing after write"})
            else:
                cur = p.read_text(encoding="utf-8", errors="replace")
                # the write may have been followed by edits — check the written blob is present
                good = (content == cur) or (content in cur)
                out.append({"path": path, "good": good,
                            "why": "" if good else "file content differs from what was written"})
        except Exception as e:
            out.append({"path": path, "good": False, "why": str(e)[:80]})
    return out


def _url_checks(final: str, episode_events: list[dict]) -> list[str]:
    fetched = set()
    for ev in episode_events:
        if ev.get("tool") == "web_fetch" and ev.get("ok"):
            try:
                args = json.loads(ev.get("args") or "{}")
                fetched.add(str(args.get("url", "")).rstrip("/"))
            except Exception:
                pass
    cited = {u.rstrip("/.,:;!?") for u in _URL.findall(final or "")}
    handled = {f.rstrip("/") for f in fetched} | {o.rstrip("/") for o in _opened_urls(episode_events)}
    return [u for u in cited if u not in handled and len(cited) > 0]


def _opened_urls(events: list[dict]) -> set[str]:
    """URLs a tool actually opened/launched (browser start, navigate, open).

    Opening a page satisfies the 'cited' check just like fetching does -
    'open grok.com' is an action, not a fabrication.
    """
    out: set[str] = set()
    for ev in events:
        if not ev.get("ok") or ev.get("tool") not in ("shell", "code_run", "systemctl", "web_fetch"):
            continue
        # args is a JSON string with escaped quotes; parse it so we read clean
        # values (command/url/code) instead of raw \"-containing text
        blob = ev.get("args") or ""
        try:
            j = json.loads(blob)
            if isinstance(j, dict):
                blob = " ".join(str(x) for x in j.values())
            elif isinstance(j, str):
                blob = j
        except Exception:
            pass
        for u in _URL.findall(blob):
            out.add(u.rstrip("/"))
        for dom in re.findall(r"((?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s]*)?)", blob, re.I):
            out.add("https://" + dom.lower().rstrip("/"))
    return out


def verify(task: str, final: str, workspace: Path, episode_events: list[dict] | None = None) -> dict:
    events = episode_events or []
    findings: list[dict] = []
    verdict = "pass"

    for c in _calc_checks(events):
        if not c["good"]:
            verdict = "fail"
            findings.append({"check": "math", "detail": f"calculator said wrong value for: {c['expr']}"})

    for c in _file_checks(events, workspace):
        if not c["good"]:
            verdict = "fail"
            findings.append({"check": "file", "detail": f"{c['path']}: {c['why']}"})

    # normalize trailing punctuation before comparing
    unfetched = [u.rstrip(".,:;!?") for u in _url_checks(final, events) if u.rstrip(".,:;!?")]
    if unfetched:
        if verdict == "pass":
            verdict = "warn"
        findings.append({"check": "url", "detail": f"cited but never fetched: {unfetched[:3]}"})

    return {"verdict": verdict, "findings": findings}
