"""Capability-based authorization (Phase 3, Part A/B).

Capabilities are coarse grants checked BEFORE tool execution; the guard
(bee/guard.py) remains the fine-grained per-command layer underneath.
Layering:  CapabilityGate (is this KIND of action permitted at all?)
           -> guard.check (is THIS specific command safe?)
           -> tool executes

Rules implemented here:
- dangerous capabilities are DENIED by default (system control, financial,
  purchase, camera);
- every capability has: identifier, description, risk level (R0..R5),
  default policy, confirmation policy;
- policies: always_allow | ask | task | deny;
- confirmation policies: none | on_ask | always (deleting/purchasing/shutting
  down confirm EVEN when the policy is always_allow, unless the user
  explicitly sets confirm: never);
- task-scoped grants: answering 'yes' to an ask grants the capability for the
  CURRENT TASK ONLY (allow-during-current-task) — a grant on one task is
  never inferred for another task, and a FILES_WRITE grant never satisfies
  FILES_DELETE or PURCHASE (grants are keyed (task, capability)).

User configuration: config/capabilities.yaml (see config/capabilities.example.yaml)
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path


class Risk(IntEnum):
    R0 = 0  # information only
    R1 = 1  # local read
    R2 = 2  # local modification
    R3 = 3  # external side effect
    R4 = 4  # destructive / system-critical
    R5 = 5  # financial / security-critical


RISK_LABEL = {Risk.R0: "information only", Risk.R1: "local read",
              Risk.R2: "local modification", Risk.R3: "external side effect",
              Risk.R4: "destructive/system-critical", Risk.R5: "financial/security-critical"}

ALLOW, ASK, TASK, DENY = "always_allow", "ask", "task", "deny"
CONF_NONE, CONF_ON_ASK, CONF_ALWAYS = "none", "on_ask", "always"


@dataclass(frozen=True)
class Capability:
    id: str
    name: str
    description: str
    risk: Risk
    default_policy: str          # ALLOW | ASK | TASK | DENY
    confirmation: str            # CONF_NONE | CONF_ON_ASK | CONF_ALWAYS


CAPABILITIES: dict[str, Capability] = {c.id: c for c in [
    Capability("files.read", "Read local files", "Read files inside the workspace.",
               Risk.R1, ALLOW, CONF_NONE),
    Capability("files.write", "Create or modify local files", "Write/edit files inside the workspace.",
               Risk.R2, ALLOW, CONF_NONE),
    Capability("files.delete", "Delete local files", "Remove files or directories from the workspace.",
               Risk.R4, ASK, CONF_ALWAYS),
    Capability("shell.execute", "Run shell commands", "Execute OS commands (guard refines per command).",
               Risk.R3, ALLOW, CONF_ON_ASK),
    Capability("python.execute", "Run Python code", "Execute Python (code_run / python -c).",
               Risk.R3, ALLOW, CONF_ON_ASK),
    Capability("browser.read", "Read browser pages", "Open and read pages in the automation browser.",
               Risk.R1, ALLOW, CONF_NONE),
    Capability("browser.interact", "Interact with the browser", "Click/type/submit in the automation browser.",
               Risk.R3, ASK, CONF_ON_ASK),
    Capability("network.read", "Fetch from the network", "HTTP(S) fetches of external content (untrusted).",
               Risk.R1, ALLOW, CONF_NONE),
    Capability("system.control", "Control the system", "Shutdown, reboot, service control, force-kill.",
               Risk.R4, DENY, CONF_ALWAYS),
    Capability("messaging.draft", "Draft messages", "Compose chat/email message text (no send).",
               Risk.R2, ALLOW, CONF_NONE),
    Capability("messaging.send", "Send messages", "Send a message to a third party (chat/SMS/WhatsApp).",
               Risk.R3, ASK, CONF_ON_ASK),
    Capability("email.draft", "Draft emails", "Compose email text (no send).",
               Risk.R2, ALLOW, CONF_NONE),
    Capability("email.send", "Send email", "Send an email (external side effect).",
               Risk.R3, ASK, CONF_ON_ASK),
    Capability("calendar.read", "Read calendar", "List/read calendar events.",
               Risk.R1, ALLOW, CONF_NONE),
    Capability("calendar.write", "Modify calendar", "Create/update calendar events.",
               Risk.R2, ALLOW, CONF_NONE),
    Capability("financial.action", "Financial action", "Move money, pay, bill, transfer.",
               Risk.R5, DENY, CONF_ALWAYS),
    Capability("purchase", "Purchase", "Buy something or place an order.",
               Risk.R5, DENY, CONF_ALWAYS),
    Capability("camera.access", "Use the camera", "Access the local camera.",
               Risk.R3, DENY, CONF_ON_ASK),
    Capability("microphone.access", "Use the microphone", "Capture audio from the mic.",
               Risk.R2, ALLOW, CONF_NONE),
]}

# ------------------------------------------------------------- tool mapping
# base capability per tool (by name — future tools are mapped here too)
_TOOL_CAPS: dict[str, list[str]] = {
    "file_read": ["files.read"],
    "file_list": ["files.read"],
    "file_write": ["files.write"],
    "file_edit": ["files.write"],
    "shell": ["shell.execute"],
    "code_run": ["python.execute"],
    "sandbox_run": ["python.execute"],
    "systemctl": ["system.control"],
    "automate": ["browser.interact"],
    "web_fetch": ["network.read"],
    "web_search": ["network.read"],
    "memory_search": ["files.read"],
    "memory_longterm": ["files.write"],
    "diary_add": ["files.write"],
    "profile_add": ["files.write"],
    "email_send": ["email.send"],          # future tool — mapped now
    "message_send": ["messaging.send"],    # future tool — mapped now
    "calendar_read": ["calendar.read"],    # future tool
    "calendar_add": ["calendar.write"],    # future tool
    "purchase": ["purchase"],              # future tool
    "pay": ["financial.action"],           # future tool
    "camera_snap": ["camera.access"],      # future tool
    "mic_record": ["microphone.access"],   # future tool
}
# escalations applied to exec tools based on argument content
_ESCALATE = [
    (re.compile(r"\b(rm\b|del\b|erase\b|remove-item\b|unlink\b|rmtree\b|os\.(remove|unlink)|"
               r"shutil\.move\b|format\s+[a-z]:)", re.I), "files.delete"),
    (re.compile(r"\b(shutdown|reboot|taskkill|powercfg|systemctl\s+(stop|poweroff|reboot))\b", re.I),
     "system.control"),
    (re.compile(r"\b(curl|wget|requests\.(get|post|put)|urllib|httpx)\b", re.I), "network.read"),
    (re.compile(r"^\s*python\d?\b", re.I), "python.execute"),
    (re.compile(r"\b(buy|purchase|checkout|place.*order)\b", re.I), "purchase"),
]

_EXEC_TOOLS = {"shell", "code_run", "sandbox_run"}


def capabilities_for(tool: str, args: dict) -> list[Capability]:
    """Capabilities required to run `tool` with these args (base + escalation)."""
    ids = list(_TOOL_CAPS.get(tool, []))
    if tool in _EXEC_TOOLS:
        text = str((args or {}).get("command") or (args or {}).get("code") or "")
        for rx, cap in _ESCALATE:
            if cap not in ids and rx.search(text):
                ids.append(cap)
    out, seen = [], set()
    for i in ids:
        c = CAPABILITIES.get(i)
        if c and c.id not in seen:
            out.append(c)
            seen.add(i)
    return out


# ------------------------------------------------------------------- store
@dataclass
class _Entry:
    policy: str
    confirm: str = "default"   # default | always | never


class CapabilityStore:
    """User-configurable policies. File format (config/capabilities.yaml):

        files.delete:
          policy: ask
          confirm: always        # (default for R4/R5 — shown for clarity)
        email.send:
          policy: always_allow
          confirm: never
    """

    def __init__(self, config_path: str | Path | None = None):
        self.config_path = Path(config_path) if config_path else None
        self._entries: dict[str, _Entry] = {}
        self._task_grants: dict[str, set[str]] = {}
        self._load()

    def _load(self):
        if self.config_path and self.config_path.exists():
            try:
                import yaml
                raw = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
                for cap_id, e in raw.items():
                    if cap_id not in CAPABILITIES:
                        continue
                    e = e or {}
                    self._entries[cap_id] = _Entry(
                        policy=str(e.get("policy", "default")),
                        confirm=str(e.get("confirm", "default")))
            except Exception:
                pass  # malformed config -> defaults (logged by caller if desired)

    def entry(self, cap_id: str) -> _Entry:
        return self._entries.get(cap_id) or _Entry(policy=CAPABILITIES[cap_id].default_policy)

    # task-scoped grants ----------------------------------------------------
    def grant_for_task(self, task_id: str, cap_id: str):
        if task_id:
            self._task_grants.setdefault(task_id, set()).add(cap_id)

    def granted_in_task(self, task_id: str, cap_id: str) -> bool:
        return cap_id in self._task_grants.get(task_id, set())

    def end_task(self, task_id: str):
        """Task-scoped grants die with the task — never carried over."""
        self._task_grants.pop(task_id, None)

    def all_grants(self) -> dict[str, set[str]]:
        return {k: set(v) for k, v in self._task_grants.items()}


# ------------------------------------------------------------------- gate
@dataclass
class GateDecision:
    allowed: bool
    capability_id: str = ""
    reason: str = ""
    policy: str = ""
    confirmed: bool = False


class CapabilityGate:
    """Pre-execution authorization. `confirmer(capability, reason) -> bool`
    is the human (or test) consult; the gate never stores what the confirmer
    saw, and never re-asks within a task after a grant."""

    def __init__(self, store: CapabilityStore | None = None,
                 config_path: str | Path | None = None, confirmer=None):
        self.store = store or CapabilityStore(config_path)
        self.confirmer = confirmer   # set by the kernel per application/session

    def required_for(self, tool: str, args: dict) -> list[Capability]:
        return capabilities_for(tool, args)

    def check(self, tool: str, args: dict, task_id: str = "",
              confirmer=None) -> GateDecision:
        conf = confirmer if confirmer is not None else self.confirmer
        confirmed = False
        policies: set[str] = set()
        worst_id, worst_risk = "", -1
        for cap in self.required_for(tool, args):
            d = self._check_one(cap, task_id, conf)
            if not d.allowed:
                return d
            policies.add(d.policy)
            if d.confirmed:
                confirmed = True
            if int(cap.risk) > worst_risk:
                worst_risk, worst_id = int(cap.risk), cap.id
        if not policies:
            return GateDecision(True, "", "no capability required", "allow")
        agg = "allow"
        for p in ("deny", "ask", "task"):
            if p in policies:
                agg = p
                break
        return GateDecision(True, worst_id, "all capabilities permitted", agg,
                            confirmed=confirmed)

    def _check_one(self, cap: Capability, task_id: str, confirmer) -> GateDecision:
        entry = self.store.entry(cap.id)
        policy = entry.policy
        if policy == DENY:
            return GateDecision(False, cap.id, f"capability policy is DENY ({cap.description})", policy)
        if policy == ALLOW:
            need_confirm = (cap.confirmation == CONF_ALWAYS and entry.confirm != "never")
            if need_confirm:
                return self._ask(cap, task_id, confirmer,
                                 f"{cap.name}: {cap.description} [always-confirm]")
            return GateDecision(True, cap.id, "allowed", policy, confirmed=False)
        if policy == TASK:
            if self.store.granted_in_task(task_id, cap.id):
                return GateDecision(True, cap.id, "granted for this task", policy)
            return self._ask(cap, task_id, confirmer,
                             f"{cap.name}: {cap.description} [task-scoped: allowed only while this task is active]")
        # policy == ASK (default for most R3/R4)
        if self.store.granted_in_task(task_id, cap.id):
            return GateDecision(True, cap.id, "granted earlier in this task", policy, confirmed=True)
        return self._ask(cap, task_id, confirmer, f"{cap.name}: {cap.description}")

    def _ask(self, cap: Capability, task_id: str, confirmer, reason: str) -> GateDecision:
        if confirmer is None:
            # unattended: fail closed for anything that asks
            return GateDecision(False, cap.id, f"{reason} — no approver available (auto-denied)")
        try:
            ok = bool(confirmer(cap, reason))
        except Exception:
            ok = False
        if ok:
            self.store.grant_for_task(task_id, cap.id)   # allow during CURRENT task only
            return GateDecision(True, cap.id, f"confirmed by user; granted for current task",
                                "ask", confirmed=True)
        return GateDecision(False, cap.id, f"confirmation refused: {reason}", "ask")
