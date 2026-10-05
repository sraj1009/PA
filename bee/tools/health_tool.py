"""system_health — BEE checks its own environment from inside the loop."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class T:
    name: str
    description: str
    parameters: dict
    handler: object


def health_tools():
    def h_health(ctx):
        from ..monitor import health, metrics
        checks = health.run_checks(ctx.cfg)
        return {
            "checks": [{ "ok": c["ok"], "name": c["name"], "note": c["note"]} for c in checks],
            "all_ok": all(c["ok"] for c in checks),
            "stats_7d": metrics.stats(),
            "guard": {"on": ctx.guard_on, "mode": ctx.guard_mode},
            "privacy_redact_cloud": ctx.privacy_on,
            "rag_auto_context": ctx.rag_on,
        }

    return [
        T("system_health",
          "Check BEE's own environment: Ollama/models, cloud key, docker sandbox, voice deps, disk, "
          "and 7-day activity stats. Use when the user asks how the system is doing or when diagnosing failures.",
          {"type": "object", "properties": {}, "required": []}, h_health),
    ]
