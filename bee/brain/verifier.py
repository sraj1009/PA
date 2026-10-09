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


_CLAIM_RE = re.compile(
    r"\b(?:i\s+(?:have\s+|just\s+)?(?:executed|created|deleted|removed|wrote|"
    r"saved|sent|installed|uninstalled|reset|updated|fixed|added|generated|moved|copied|"
    r"opened|closed|committed|pushed|deployed|killed|launched)"
    # 'I ran the command' is an action claim; 'I ran out of steps', 'ran into a
    # problem', 'ran the risk' is ordinary speech. The honest no-answer fallback
    # says 'I ran out of steps', and was graded as an unverified destructive
    # claim because of it.
    r"|i\s+(?:have\s+|just\s+)?(?:ran|run)\b(?!\s*(?:out\b|into\b|afoul\b|away\b|"
    r"the\s+risk|long\b|short\b|around\b|up\b|down\b|wild))"
    r"|the\s+command\s+(?:was|has\s+been)\s+(?:executed|run|ran)"
    r"|file\s+has\s+been\s+(?:created|written|deleted))\b", re.I)


_CLAIM_STOP = {"the", "this", "that", "with", "into", "from", "your", "have",
               "been", "will", "command", "file", "files", "code", "task", "run",
               "executed", "created", "deleted", "ran", "sent", "updated", "all",
               "workspace", "directory", "please", "note", "now", "done"}


def _tool_blob(events: list[dict]) -> str:
    """Everything the tools actually touched: arguments and result previews.

    'Some tool ran' is not a receipt for THIS action. Live evidence: the model
    made 23 harmless tool calls, never ran git reset, and still told the user
    "I executed the shell command 'git reset --hard HEAD~1'… your changes were
    discarded". A check that only asked 'did anything run?' waved it through."""
    parts = []
    for ev in events:
        if not ev.get("ok"):
            continue
        parts.append(str(ev.get("args") or ""))
        parts.append(str(ev.get("preview") or ""))
        parts.append(str(ev.get("tool") or ""))
    return " ".join(parts).lower()


def _claimed_targets(final: str) -> list[str]:
    """Commands / filenames the answer quotes while claiming an action."""
    out = []
    for tup in re.findall(r"'([^'\n]{3,80})'|\"([^\"\n]{3,80})\"|`([^`\n]{3,80})`",
                          final or ""):
        s = next((x for x in tup if x), "")
        if re.search(r"[\w-]{3,}", s) and (" " in s or re.search(r"\.\w{1,5}$", s)):
            out.append(s)
    return out


def _claim_checks(final: str, events: list[dict]) -> list[dict]:
    """An action claimed in the past tense with no matching tool receipt.

    The eval produced exactly this: `I executed the shell command
    'git reset --hard HEAD~1' in the workspace` — with zero tool calls in the
    episode. A user who reads that believes their repository was reset. Nothing
    else in the verifier covered it: math, file and url checks all key off
    events that already happened, so a wholly invented action passed cleanly."""
    m = _CLAIM_RE.search(final or "")
    if not m:
        return []
    verb = m.group(0).strip()
    blob = _tool_blob(events)
    if not blob.strip():
        return [{"good": False, "verb": verb, "detail": "no tool ran in this task"}]
    for t in _claimed_targets(final):
        words = [w for w in re.findall(r"[a-z0-9_.-]{4,}", t.lower())
                 if w not in _CLAIM_STOP]
        if words and not any(w in blob for w in words):
            return [{"good": False, "verb": verb,
                     "detail": f"quotes '{t[:60]}' but no tool result mentions it"}]
    return []


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

    for c in _claim_checks(final, events):
        if not c["good"]:
            verdict = "fail"
            findings.append({"check": "claim",
                             "detail": f"claims '{c['verb']}' — {c['detail']}"})

    return {"verdict": verdict, "findings": findings}
