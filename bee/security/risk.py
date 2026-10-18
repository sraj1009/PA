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
import os
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
CAP_DESKTOP = "desktop"
CAP_AUTOMATION = "automation"


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
    # computer use (Phase 5 — safe set only; the session adds budget,
    # provenance and post-action verification on top of this layer)
    "computer_observe":   (RiskLevel.LOW, frozenset({CAP_DESKTOP})),
    "computer_window":    (RiskLevel.MEDIUM, frozenset({CAP_DESKTOP})),
    "computer_input":     (RiskLevel.MEDIUM, frozenset({CAP_DESKTOP})),
    "computer_clipboard": (RiskLevel.LOW, frozenset({CAP_DESKTOP})),
    "computer_stop":      (RiskLevel.LOW, frozenset()),
    # Phase 6 — durable automation: managing scheduled/proactive behavior is
    # a state change with future side effects (MEDIUM); the capability gate
    # (automation.manage, ASK) is the authorization layer on top.
    "automation_job":   (RiskLevel.MEDIUM, frozenset({CAP_AUTOMATION})),
}
_DEFAULT_PROFILE = (RiskLevel.LOW, frozenset())

# systemctl actions that change machine state (mirrors guard._SYSTEMCTL_ASK)
_SYSTEMCTL_ASK = {"lock", "sleep"}


# --------------------------------------------------------------- Python AST
# import → deny (arbitrary exec / network / binary escape surface)
_DENY_IMPORTS = {"subprocess", "socket", "ctypes"}
# import → ask (state access, review-worthy)
_ASK_IMPORTS = {"os", "sys", "importlib", "pickle", "shutil", "signal", "multiprocessing",
                # network clients: egress from code_run needs approval
                "requests", "httpx", "urllib", "aiohttp", "urllib3", "http"}
# (module, attr) -> action — for `mod.attr(...)` calls
_DENY_CALLS: dict[tuple[str, str], str] = {
    ("os", "system"): "deny", ("os", "popen"): "deny",
    ("os", "execv"): "deny", ("os", "execve"): "deny", ("os", "execvp"): "deny",
    ("os", "execl"): "deny", ("os", "execlp"): "deny",
    ("os", "spawnl"): "deny", ("os", "spawnle"): "deny",
    ("os", "remove"): "deny", ("os", "unlink"): "deny", ("os", "rmdir"): "deny",
    ("os", "removedirs"): "deny", ("os", "truncate"): "deny",
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
    ("shutil", "copy2"): "ask", ("shutil", "copytree"): "ask",
    ("os", "mkdir"): "ask", ("os", "makedirs"): "ask", ("os", "symlink"): "ask",
    ("signal", "signal"): "ask",
}
# bare builtins — always deny when called (code injection / dynamic imports)
_DENY_NAMES = {"eval", "exec", "compile", "__import__"}
# method names on ANY object that imply irreversible file destruction
_DENY_METHODS = {"unlink", "rmdir"}
# open() modes that mutate
_WRITE_MODE_CHARS = set("wax+")
# H1+ (2026-10-18): network-client modules/calls — egress from code_run needs
# approval; a non-public literal target (localhost/RFC1918/metadata) is
# denied offline (no DNS at classification time). Raw `socket`/`ctypes`
# imports stay outright deny (_DENY_IMPORTS).
_NET_MODULES = {"requests", "httpx", "urllib", "aiohttp", "urllib3", "http"}
_NET_CALLS = {"get", "post", "put", "delete", "patch", "head", "request",
              "urlopen", "urlretrieve", "Session", "Client",
              "HTTPConnection", "HTTPSConnection"}
# pathlib/Path write + state methods (path-aware, mirroring the open() rules)
_PATH_WRITE_METHODS = {"write_text", "write_bytes"}
_PATH_STATE_METHODS = {"mkdir", "makedirs", "touch"}


def _attr_chain(f: ast.Attribute, mod_alias: dict) -> tuple[str, str]:
    """(module, dotted-attr) for `mod.a.b` targets, alias-aware; ('', attr)
    when the root is not a plain name (e.g. a call result like Path('x'))."""
    parts: list[str] = []
    v: ast.expr = f
    while isinstance(v, ast.Attribute):
        parts.append(v.attr)
        v = v.value
    attr = ".".join(reversed(parts))
    if isinstance(v, ast.Name):
        return mod_alias.get(v.id, v.id), attr
    return "", attr


def _import_aliases(tree: ast.AST) -> tuple[dict, dict]:
    """Local-name maps so aliasing cannot hide a destructive call:
       `import shutil as sh`       -> {'sh': 'shutil'}
       `from os import system as s` -> {'s': ('os', 'system')}
    """
    mod_alias: dict[str, str] = {}
    from_alias: dict[str, tuple[str, str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    mod_alias[a.asname] = a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            for a in node.names:
                from_alias[a.asname or a.name] = (top, a.name)
    return mod_alias, from_alias


def _literal_str_arg(node: ast.Call) -> str:
    """First positional string-literal argument, else ''."""
    for a in node.args:
        if isinstance(a, ast.Constant) and isinstance(a.value, str):
            return a.value
        break
    return ""


def _ws_roots() -> list[str]:
    """Accepted write roots: runtime workspace, project checkout, OS temp."""
    roots: list[str] = []
    try:
        from .. import paths as _paths
        roots.extend([str(_paths.WORKSPACE), str(_paths.PROJECT_ROOT)])
    except Exception:
        pass
    try:
        import tempfile
        roots.append(tempfile.gettempdir())
    except Exception:
        pass
    return roots


def _under_any(path: str, roots: list[str]) -> bool:
    try:
        n = os.path.normcase(os.path.abspath(path))
    except Exception:
        return False
    for r in roots:
        try:
            rn = os.path.normcase(os.path.abspath(str(r))).rstrip("\\/")
        except Exception:
            continue
        if n == rn or n.startswith(rn + os.sep):
            return True
    return False


def _outside_workspace(p: str) -> bool | None:
    """True only when a LITERAL path clearly escapes workspace+project+temp.
    None/False = inside, plain relative, or undecidable — dynamic and
    in-tree writes keep the ordinary 'ask' behavior, never less."""
    s = str(p or "").strip()
    if not s:
        return None
    if s.startswith("~"):
        s = os.path.expanduser(s)
    roots = _ws_roots()
    if not roots:
        return None
    drive = len(s) > 1 and s[1] == ":"
    if os.path.isabs(s) or drive or s.startswith("\\\\"):
        return not _under_any(s, roots)
    if ".." in s.replace("\\", "/").split("/"):
        for base in roots[:2]:
            if _under_any(os.path.join(base, s), roots):
                return None          # escaping one base can stay inside another
        return True
    return None


def _url_risk(node: ast.Call) -> str:
    """Offline (no DNS) SSRF check for a literal URL argument."""
    u = _literal_str_arg(node)
    if not u or "://" not in u:
        return ""
    try:
        from . import netguard
        reason = netguard.validate_url(u, resolver=lambda _h: [])
    except Exception:
        return ""
    if reason.startswith("IP ") or reason.startswith("blocked hostname"):
        return reason
    return ""


def _classify_call(mod: str, attr: str, node: ast.Call, add) -> bool:
    """Table lookup for a resolved call target. True = a rule matched."""
    last = attr.rsplit(".", 1)[-1] if attr else ""
    if (mod, attr) in _DENY_CALLS:
        add("deny", f"{mod}.{attr}()")
        return True
    if (mod, attr) in _ASK_CALLS:
        add("ask", f"{mod}.{attr}()")
        return True
    if mod in _NET_MODULES and last in _NET_CALLS:
        bad = _url_risk(node)
        if bad:
            add("deny", f"{mod}.{attr}() -> non-public target ({bad})")
        else:
            add("ask", f"{mod}.{attr}() (network egress; no host allowlist)")
        return True
    return False


def _path_owner_literal(f: ast.Attribute) -> str:
    """Literal path of a `Path('x').write_text(...)` owner, else ''."""
    v = f.value
    if isinstance(v, ast.Call) and isinstance(v.func, ast.Name) \
            and v.func.id in ("Path", "PurePath", "PurePosixPath", "PureWindowsPath"):
        return _literal_str_arg(v)
    return ""


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

    Alias-aware (`import shutil as sh`, `from os import system`), path-aware
    for writes (a write-mode open / Path.write_text on a LITERAL path that
    escapes workspace+project+temp → deny), and offline SSRF-aware for
    literal URLs (no DNS here; localhost/RFC1918/link-local targets deny).

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

    mod_alias, from_alias = _import_aliases(tree)

    def do_call(node: ast.Call):
        f = node.func
        if isinstance(f, ast.Name):
            if f.id in _DENY_NAMES:
                add("deny", f"call to {f.id}()")
            elif f.id == "open":
                mode = _open_write_mode(node)
                if any(c in _WRITE_MODE_CHARS for c in mode):
                    p = _literal_str_arg(node)
                    if p and _outside_workspace(p) is True:
                        add("deny", f"open() write outside the workspace: {p}")
                    else:
                        add("ask", f"open() with write/truncate mode {mode!r}")
            elif f.id == "getattr" and len(node.args) >= 2:
                m, a = node.args[0], node.args[1]
                if isinstance(m, ast.Name) and isinstance(a, ast.Constant) \
                        and isinstance(a.value, str):
                    mod = mod_alias.get(m.id, m.id)
                    if (mod, a.value) in _DENY_CALLS:
                        add("deny", f"getattr({mod}, {a.value!r})")
                    elif (mod, a.value) in _ASK_CALLS:
                        add("ask", f"getattr({mod}, {a.value!r})")
            elif f.id in from_alias:
                mod, attr = from_alias[f.id]
                _classify_call(mod, attr, node, add)
        elif isinstance(f, ast.Attribute):
            mod, attr = _attr_chain(f, mod_alias)
            last = attr.rsplit(".", 1)[-1] if attr else ""
            if _classify_call(mod, attr, node, add):
                return
            if last in _DENY_METHODS:
                owner = f.value.id if isinstance(f.value, ast.Name) else "obj"
                add("deny", f"{owner}.{last}() (file destruction)")
            elif last in _PATH_WRITE_METHODS:
                p = _path_owner_literal(f)
                if p and _outside_workspace(p) is True:
                    add("deny", f"{last}() write outside the workspace: {p}")
                else:
                    add("ask", f"{last}() write")
            elif last in _PATH_STATE_METHODS:
                add("ask", f"{last}() (state change)")

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
            do_call(node)
        elif isinstance(node, ast.Attribute):
            # deny-listed function merely REFERENCED (f = os.system) — the
            # call branch reports the same detail; the seen-set dedupes.
            mod, attr = _attr_chain(node, mod_alias)
            if (mod, attr) in _DENY_CALLS:
                add("deny", f"{mod}.{attr}()")
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

    if tool == "computer_input":
        # Phase 5: never trust coordinates blindly + keyboard input is a
        # user-visible side effect -> explicit confirmation, not just grant
        a = str(args.get("action") or "").lower().strip()
        if a == "type_text":
            level, action, reason = RiskLevel.HIGH, "ask", \
                "type_text (keyboard input into the user's session)"
        if a in ("click", "double_click") \
                and str(args.get("coordinate_source") or "") == "model_raw":
            level, action, reason = RiskLevel.HIGH, "ask", \
                "click with unproven coordinates (model_raw)"

    require_approval = action in ("ask", "deny")
    return RiskDecision(level=level, action=action, reason=reason,
                        capabilities=caps, require_approval=require_approval)
