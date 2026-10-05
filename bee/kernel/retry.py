"""Structured retry policy (Phase 2).

Failure kinds are classified BEFORE any retry decision, and destructive work
is NEVER auto-retried — a failed `rm`-class operation must be reported, not
re-run. The planner (kernel) consults this policy; it does not decide on its
own.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import FailureKind

_DESTRUCTIVE_TOOLS = {"shell", "code_run", "sandbox_run", "systemctl"}
# state-erasing OR externally-visible side effects — re-running these blind
# would double-act (double push, double send, double install...).
_NON_RETRYABLE_RE = re.compile(
    r"\b(rm\b|del\b|erase\b|remove-item\b|shutil\.rmtree|os\.(remove|unlink)|format\s+[a-z]:|"
    r"drop\s+(table|database)|git\s+(push|commit|reset|clean)|git\s+remote|"
    r"shutdown|reboot|taskkill|chown|chmod|pip\s+install|pip\s+uninstall|uv\s+pip\s+(install|uninstall)|"
    r"npm\s+(install|publish)|docker\s+(run|build|push|rm|system)|curl\s+.*(-X\s*(POST|PUT|DELETE)|--data)|"
    r"wget|smtp|sendmail|webhook|requests\.(post|put|delete)|httpx\.(post|put|delete)|"
    r"send|publish|deploy|email)\b", re.I)


@dataclass
class RetryPolicy:
    max_attempts: int = 2                     # total attempts (1 = no retry)
    retryable: set = field(default_factory=lambda: {
        FailureKind.TRANSIENT, FailureKind.PROVIDER, FailureKind.TOOL,
        FailureKind.VERIFICATION})
    never_retry_destructive: bool = True
    backoff_seconds: float = 0.0               # kernel applies sleep between attempts

    def classify(self, error: str, tool: str | None = None,
                 blocked: bool = False) -> FailureKind:
        e = (error or "").lower()
        if blocked or re.search(r"\bdenied|guard|not executed|blocked\b", e):
            return FailureKind.PERMISSION
        if re.search(r"unknown tool|bad arguments|typeerror|invalid (arg|input)", e):
            return FailureKind.INVALID_INPUT
        if re.search(r"llm error|unreachable|connect|quota|rate.?limit|429|timeout|timed out|"
                     r"api key|auth|503|502|server error", e):
            # provider-side OR transport blip — both may recover
            return FailureKind.PROVIDER if re.search(
                r"llm error|quota|rate.?limit|429|api key|auth|503|502|server error", e) \
                else FailureKind.TRANSIENT
        if re.search(r"verification|not (?:created|found|verif)|effect", e):
            return FailureKind.VERIFICATION
        if tool and tool in _DESTRUCTIVE_TOOLS:
            return FailureKind.TOOL
        if e:
            return FailureKind.TOOL
        return FailureKind.UNRECOVERABLE

    def is_destructive(self, tool: str | None, args: dict | None) -> bool:
        """True when a blind re-run could double-act. Read-only exec (ls/cat/
        echo/python print) is not — those may be retried."""
        if not tool or tool not in _DESTRUCTIVE_TOOLS:
            return False
        if not self.never_retry_destructive:
            return False
        text = str((args or {}).get("command") or (args or {}).get("code") or "")
        if not text:
            return True  # unknown exec payload -> treat as destructive
        return bool(_NON_RETRYABLE_RE.search(text))

    def should_retry(self, kind: FailureKind, attempt: int,
                     tool: str | None = None, args: dict | None = None) -> bool:
        if kind not in self.retryable:
            return False
        if kind == FailureKind.PERMISSION:
            return False            # explicit: a denial is a decision, not a blip
        if attempt >= self.max_attempts:
            return False
        if kind in (FailureKind.TOOL, FailureKind.VERIFICATION) and \
                self.is_destructive(tool, args):
            return False
        return True
