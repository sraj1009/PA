"""Episode logger — persist complete task episodes for the data pipeline.

Each episode (one JSONL row per day file) captures:
  task, model, route, every tool call (name, args, ok, seconds, truncated result),
  final output, ok, verification verdict, duration, est tokens.

These episodes feed:
  - pipeline/validate.py   (verifiable-success filter)
  - pipeline/build_sft.py  (SFT data with loss masking)
  - pipeline/train_router.py (route classifier labels)

Storage is bounded: args/results truncated to 4000 chars each, 200 events max.
"""
from __future__ import annotations

import json
import time
from datetime import date

from .. import paths, privacy

MAX_EVENT_CHARS = 4000
MAX_EVENTS = 200


def _short(v, limit: int = MAX_EVENT_CHARS) -> str:
    """Serialize + REDACT before persistence. Episodes feed SFT builds and
    cloud teach-back — they are generated files and must never become a
    secret/PII sink (Phase 1 security)."""
    try:
        s = json.dumps(v, ensure_ascii=False, default=str)
    except Exception:
        s = str(v)
    s, _n = privacy.redact(s)
    return s[:limit]


class Episode:
    def __init__(self, task: str, model: str = ""):
        self.task = task
        self.model = model
        self.escalated = False
        self.t0 = time.time()
        self.events: list[dict] = []
        self.tokens = 0
        self.ok = False
        self.output = ""
        self.error = ""
        self.verify: dict = {}

    def tool(self, name: str, args, ok: bool, seconds: float, result) -> None:
        if len(self.events) >= MAX_EVENTS:
            return
        self.events.append({
            "tool": name, "args": _short(args), "ok": ok,
            "seconds": round(seconds, 2), "result": _short(result),
        })

    def finish(self, ok: bool, output: str = "", error: str = "",
               escalated: bool = False, verify: dict | None = None,
               tokens: int = 0) -> dict:
        self.ok = ok
        self.output = privacy.redact((output or ""))[0][:8000]
        self.error = privacy.redact((error or ""))[0][:1000]
        self.escalated = escalated
        self.verify = verify or {}
        self.tokens = tokens
        row = {
            "ts": round(self.t0, 1),
            "date": date.today().isoformat(),
            "task": privacy.redact(self.task)[0][:4000],
            "model": self.model,
            "escalated": self.escalated,
            "ok": ok,
            "error": self.error,
            "output": self.output,
            "verify": self.verify,
            "tokens": tokens,
            "seconds": round(time.time() - self.t0, 1),
            "n_tools": len(self.events),
            "events": self.events,
        }
        try:
            paths.EPISODES_DIR.mkdir(parents=True, exist_ok=True)
            p = paths.EPISODES_DIR / f"{row['date']}.jsonl"
            from ..monitor.rotate import rotate_if_needed
            rotate_if_needed(p, 5_000_000, 1)               # M13: bounded
            with p.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except Exception:
            pass
        return row

    # ------------------------------------------------------------ SFT export
    def to_messages(self) -> list[dict] | None:
        """Qwen3/OpenAI chat format with `loss` flag for masking tool/user turns.
        Returns None if the episode is not SFT-usable (failed / no final)."""
        if not self.ok or not self.output:
            return None
        msgs: list[dict] = [{"role": "user", "content": self.task, "loss": False}]
        for ev in self.events:
            try:
                args = json.loads(ev["args"])
            except Exception:
                args = {}
            msgs.append({
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": ev["tool"], "arguments": ev["args"]}}],
                "loss": True,
            })
            try:
                res = json.loads(ev["result"])
            except Exception:
                res = ev["result"]
            msgs.append({"role": "tool", "content": _short(res, 2000), "name": ev["tool"], "loss": False})
        msgs.append({"role": "assistant", "content": self.output, "loss": True})
        return msgs
