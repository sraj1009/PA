"""Tool risk classification — the Policy/Permissions foundation.

Layering (each layer is independent; the strictest wins):
  1. static profile  — per-tool base risk + capability set (this module)
  2. shell rules     — bee.guard.classify regexes (pinned by the 4,204-check
                       verify suite; DO NOT change their behavior here)
  3. Python AST      — analyze_python() parses `code_run` payloads so
                       shutil.rmtree / os.remove / Path.unlink / subprocess
                       can no longer slip past shell-oriented regexes
  4. fail-closed     — a code_run payload that does not parse as Python is
                       ESCALATED (ask), never silently allowed

Severity model (mirrors the guard's allow/ask/deny philosophy):
  deny  — irreversible destruction, arbitrary exec, network escape,
         deserialization, code injection (eval/exec/compile)
  ask   — state-changing but reviewable (file writes, moves, process
         control, imports of state-access modules)

`guard.classify` stays pure-regex for compatibility; `guard.check` adds the
AST escalation, and the agent loop records every decision in
bee.security.audit.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from enum import IntEnum


class RiskLevel(IntEnum):
    NONE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


# capability constants (string IDs — stable across processes, logs, future bus)
CAP_FS_READ = "fs.read"
CAP_FS_WRITE = "fs.write"
CAP_EXEC = "exec"
CAP_NETWORK = "network"
CAP_SYSTEM = "system"
CAP_SCHEDULE = "schedule"


@dataclass(frozen=True)
class RiskDecision:
    """Outcome of risk classification for ONE tool call."""
    level: RiskLevel
    action: str                 # allow | ask | deny  (guard-compatible)
    reason: str
    capabilities: frozenset = frozenset()
    require_approval: bool = False

    def __str__(self) -> str:
        return f"{self.level.name}/{self.action} ({self.reason or 'ok'})"


# --------------------------------------------------------------- static map
# tool -> (base level, capabilities). Dynamic args escalate via rules below.
_TOOL_PROFILES: dict[str, tuple[RiskLevel, frozenset]] = {
    # execution
    "shell":        (RiskLevel.MEDIUM, frozenset({CAP_EXEC, CAP_FS_WRITE, CAP_NETWORK})),
    "code_run":     (RiskLevel.MEDIUM, frozenset({CAP_EXEC, CAP_FS_WRITE, CAP_NETWORK})),
    "sandbox_run":  (RiskLevel.MEDIUM, frozenset({CAP_EXEC, CAP_FS_WRITE, CAP_NETWORK})),
    "systemctl":    (RiskLevel.MEDIUM, frozenset({CAP_SYSTEM})),
    # files (workspace-jailed by tools/files.resolve)
    "file_read":    (RiskLevel.LOW, frozenset({CAP_FS_READ})),
    "file_write":   (RiskLevel.MEDIUM, frozenset({CAP_FS_WRITE})),
    "file_edit":    (RiskLevel.MEDIUM, frozenset({CAP_FS_WRITE})),
    "file_list":    (RiskLevel.LOW, frozenset({CAP_FS_READ})),
    # network
    "web_fetch":    (RiskLevel.LOW, frozenset({CAP_NETWORK, CAP_FS_READ})),
    "web_search":   (RiskLevel.LOW, frozenset({CAP_NETWORK})),
    "automate":     (RiskLevel.MEDIUM, frozenset({CAP_NETWORK, CAP_EXEC})),
    # memory / knowledge
    "memory_search":  (RiskLevel.LOW, frozenset({CAP_FS_READ})),
    "memory_longterm": (RiskLevel.MEDIUM, frozenset({CAP_FS_WRITE})),
    "diary_add":      (RiskLevel.MEDIUM, frozenset({CAP_FS_WRITE})),
    "profile_add":    (RiskLevel.MEDIUM, frozenset({CAP_FS_WRITE})),
    # orchestration
    "planner":      (RiskLevel.LOW, frozenset()),
    "spawn_task":   (RiskLevel.LOW, frozenset()),
    "skill_get":    (RiskLevel.LOW, frozenset({CAP_FS_READ})),
    "skill_list":   (RiskLevel.LOW, frozenset({CAP_FS_READ})),
    "skill_search": (RiskLevel.LOW, frozenset({CAP_FS_READ})),
    "skill_create": (RiskLevel.MEDIUM, frozenset({CAP_FS_WRITE})),
    "scheduler":    (RiskLevel.MEDIUM, frozenset({CAP_SCHEDULE})),
    "system_health": (RiskLevel.LOW, frozenset({CAP_SYSTEM})),
    "calculator":   (RiskLevel.LOW, frozenset()),
}
_DEFAULT_PROFILE = (RiskLevel.LOW, frozenset())

# systemctl actions that change machine state (mirrors guard._SYSTEMCTL_ASK)
_SYSTEMCTL_ASK = {"lock", "sleep"}


# --------------------------------------------------------------- Python AST
# import → deny (arbitrary exec / network / binary escape surface)
_DENY_IMPORTS = {"subprocess", "socket", "ctypes"}
# import → ask (state access, review-worthy)
_ASK_IMPORTS = {"os", "sys", "importlib", "pickle", "shutil", "signal", "multiprocessing"}
# (module, attr) -> action — for `mod.attr(...)` calls
_DENY_CALLS: dict[tuple[str, str], str] = {
    ("os", "system"): "deny", ("os", "popen"): "deny",
    ("os", "execv"): "deny", ("os", "execve"): "deny", ("os", "execvp"): "deny",
    ("os", "execl"): "deny", ("os", "execlp"): "deny",
    ("os", "spawnl"): "deny", ("os", "spawnle"): "deny",
    ("os", "remove"): "deny", ("os", "unlink"): "deny", ("os", "rmdir"): "deny",
    ("shutil", "rmtree"): "deny",
    ("socket", "socket"): "deny", ("socket", "create_connection"): "deny",
    ("ctypes", "CDLL"): "deny", ("ctypes", "cdll"): "deny",
    ("pickle", "load"): "deny", ("pickle", "loads"): "deny",
    ("subprocess", "run"): "deny", ("subprocess", "Popen"): "deny",
    ("subprocess", "call"): "deny", ("subprocess", "check_output"): "deny",
    ("subprocess", "check_call"): "deny",
}
_ASK_CALLS: dict[tuple[str, str], str] = {
    ("os", "chmod"): "ask", ("os", "chown"): "ask",
    ("os", "kill"): "ask", ("os", "killpg"): "ask",
    ("os", "rename"): "ask", ("os", "replace"): "ask",
    ("shutil", "move"): "ask", ("shutil", "copy"): "ask",
    ("signal", "signal"): "ask",
}
# bare builtins — always deny when called (code injection / dynamic imports)
_DENY_NAMES = {"eval", "exec", "compile", "__import__"}
# method names on ANY object that imply irreversible file destruction
_DENY_METHODS = {"unlink", "rmdir"}
# open() modes that mutate
_WRITE_MODE_CHARS = set("wax+")


def _module_for_attr(f: ast.Attribute) -> tuple[str, str]:
    """(module, attr) for a direct `mod.attr` call func; ('', attr) otherwise."""
    if isinstance(f.value, ast.Name):
        return f.value.id, f.attr
    return "", f.attr


def _open_write_mode(node: ast.Call) -> str:
    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
        return str(node.args[1].value)
    for k in node.keywords:
        if k.arg == "mode" and isinstance(k.value, ast.Constant):
            return str(k.value.value)
    return ""


def analyze_python(code: str, *, fail_closed: bool = True) -> list[tuple[str, str]]:
    """Analyze a Python payload. Returns [(action, detail), ...] with action
    in {'deny','ask'}; empty list = nothing suspicious.

    fail_closed=True (code_run): unparseable code → one 'ask' finding
      (a python -c payload that isn't valid python is suspicious).
    fail_closed=False (shell `python -c` extraction): unparseable → []
      (the shell regex layer still applies; don't false-positive on
      shell-quoted fragments).
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return [("ask", "unparseable python (manual review before exec)")] if fail_closed else []

    findings: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(action: str, detail: str):
        key = detail.lower()
        if key not in seen:
            seen.add(key)
            findings.append((action, detail))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                top = a.name.split(".")[0]
                if top in _DENY_IMPORTS:
                    add("deny", f"import {top}")
                elif top in _ASK_IMPORTS:
                    add("ask", f"import {top}")
        elif isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            if top in _DENY_IMPORTS:
                add("deny", f"from {node.module} import")
            elif top in _ASK_IMPORTS:
                add("ask", f"from {node.module} import")
        elif isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                if f.id in _DENY_NAMES:
                    add("deny", f"call to {f.id}()")
                elif f.id == "open":
                    mode = _open_write_mode(node)
                    if any(c in _WRITE_MODE_CHARS for c in mode):
                        add("ask", f"open() with write/truncate mode {mode!r}")
            elif isinstance(f, ast.Attribute):
                mod, attr = _module_for_attr(f)
                if (mod, attr) in _DENY_CALLS:
                    add("deny", f"{mod}.{attr}()")
                elif (mod, attr) in _ASK_CALLS:
                    add("ask", f"{mod}.{attr}()")
                elif attr in _DENY_METHODS:
                    owner = f.value.id if isinstance(f.value, ast.Name) else "obj"
                    add("deny", f"{owner}.{attr}() (file destruction)")
    return findings


# ---------------------------------------------------------------- classifier
def _escalate(level: RiskLevel, action: str, reason: str) -> tuple[RiskLevel, str, str]:
    if action == "deny":
        return RiskLevel.CRITICAL, "deny", reason
    if action == "ask" and level < RiskLevel.HIGH:
        return RiskLevel.HIGH, "ask", reason
    return level, action, reason


def classify_risk(tool: str, args: dict) -> RiskDecision:
    """Full classification for one tool call. Combines the static profile,
    the guard's shell rules, and Python AST analysis. Never weaker than any
    single layer."""
    args = args or {}
    base_level, caps = _TOOL_PROFILES.get(tool, _DEFAULT_PROFILE)
    level, action, reason = base_level, "allow", ""

    if tool in ("shell", "code_run", "sandbox_run", "systemctl"):
        if tool == "systemctl":
            a = str(args.get("action") or "").lower().strip()
            if a in _SYSTEMCTL_ASK:
                level, action, reason = RiskLevel.HIGH, "ask", f"systemctl {a}"
        text = str(args.get("command") or args.get("code") or "")
        if text:
            from .. import guard  # local import: guard must stay import-light
            g_action, g_reason = guard.classify(tool, {"command": text, "code": text})
            if g_action != "allow":
                level, action, reason = _escalate(level, g_action, g_reason)
        # Python AST layer — the regex layer alone misses Python idioms
        code = str(args.get("code") or "")
        if tool == "code_run" and code.strip():
            for a, d in analyze_python(code, fail_closed=True):
                if a == "deny":
                    level, action, reason = RiskLevel.CRITICAL, "deny", f"python: {d}"
                    break
                if a == "ask" and action == "allow":
                    level, action, reason = RiskLevel.HIGH, "ask", f"python: {d}"
        elif tool == "shell":
            import re as _re
            m = _re.search(r"\bpython\d?\s+(?:-[A-Za-z]+\s+)*-c\s+(.*)$", text)
            if m:
                frag = m.group(1).strip().strip("'\"")
                if frag:
                    for a, d in analyze_python(frag, fail_closed=False):
                        if a == "deny":
                            level, action, reason = RiskLevel.CRITICAL, "deny", f"python -c: {d}"
                            break
                        if a == "ask" and action == "allow":
                            level, action, reason = RiskLevel.HIGH, "ask", f"python -c: {d}"

    require_approval = action in ("ask", "deny")
    return RiskDecision(level=level, action=action, reason=reason,
                        capabilities=caps, require_approval=require_approval)
