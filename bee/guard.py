"""Permission gates — classify tool calls before execution: allow | ask | deny.

Rules target the execution tools (shell, code_run, sandbox_run). Anything
destructive or state-erasing requires human approval; unattended mode
denies instead of asking. The guard is checked in the agent loop, so the
LLM cannot bypass it.
"""
from __future__ import annotations

import re

EXEC_TOOLS = {"shell", "code_run", "sandbox_run", "systemctl"}

# systemctl actions that change machine state significantly -> always ask
_SYSTEMCTL_ASK = {"lock": "lock PC", "sleep": "sleep PC"}

# (compiled pattern, action, reason)
DESTRUCTIVE = [
    (re.compile(r"\brm\s+(-[a-z]*\s+)*-[a-z]*r[a-z]*\s", re.I), "deny", "recursive rm"),
    (re.compile(r"\brm\s+(-[a-z]+\s+)*/\s*$", re.I), "deny", "rm at filesystem root"),
    (re.compile(r"\brm\s+(-[a-z]+\s+)*(~|\$HOME|C:\\Users|/mnt/[a-z]+/Users)\b", re.I), "deny", "rm in user home"),
    (re.compile(r"\b(rmdir|rd)\s+/s\b", re.I), "deny", "recursive rmdir"),
    (re.compile(r"\bformat\s+[a-z]:", re.I), "deny", "disk format"),
    (re.compile(r"\bmkfs\b|\bwipefs\b|\bdd\s+if=", re.I), "deny", "low-level disk write"),
    (re.compile(r"\bRemove-Item\b.*-\s*Recurse", re.I), "deny", "Remove-Item -Recurse"),
    (re.compile(r"\bdel\s+/s\b|\berase\s+/s\b", re.I), "deny", "recursive del"),
    (re.compile(r"\bdrop\s+(table|database|schema)\b", re.I), "deny", "SQL DROP"),
    (re.compile(r"\btruncate\s+table\b", re.I), "deny", "SQL TRUNCATE"),
    (re.compile(r"\bgit\s+push\s+(-f|--force)\b", re.I), "deny", "force push"),
    (re.compile(r"\bgit\s+reset\s+--hard\b", re.I), "ask", "git reset --hard"),
    (re.compile(r"\bgit\s+clean\s+-[a-z]*f", re.I), "ask", "git clean -f"),
    (re.compile(r"\b(shutdown|reboot)\b", re.I), "deny", "system power action"),
    (re.compile(r"\btaskkill\b|\bkill\s+-9\b|\bsystemctl\s+(stop|disable)\b|\bnet\s+stop\b", re.I), "ask", "service/process kill"),
    (re.compile(r"\breg\s+delete\b", re.I), "deny", "registry delete"),
    (re.compile(r"\bpip\s+uninstall\b|\buv\s+pip\s+uninstall\b", re.I), "ask", "package uninstall"),
    (re.compile(r"\bdocker\s+(system\s+prune|volume\s+rm|rm\s+-f)", re.I), "ask", "docker destructive"),
    (re.compile(r"\bchown\s+-r\b|\bchmod\s+(-r\s+)?777", re.I), "ask", "bulk permission change"),
    (re.compile(r"curl\s+[^|;&]*\|\s*(ba)?sh\b|wget\s+[^|;&]*\|\s*(ba)?sh\b", re.I), "deny", "pipe-download-to-shell"),
    (re.compile(r"\bshred\b", re.I), "deny", "secure erase"),
]

EXTERNAL = [
    (re.compile(r"\bgit\s+push\b", re.I), "ask", "pushes to remote"),
    (re.compile(r"\b(curl|wget)\b.*(-X\s*(POST|PUT|DELETE)|--data|--post-data|--post-file|--upload-file)", re.I), "ask", "sends data externally"),
    (re.compile(r"\bsmtp|sendmail|mail\s+-s\b|webhook|api\.twilio|whatsapp|telegram.*send", re.I), "ask", "external messaging"),
    (re.compile(r"\brequests\.(post|put|delete)\b|\bhttpx\.(post|put|delete)\b", re.I), "ask", "HTTP write in code"),
]


def classify(tool: str, args: dict) -> tuple[str, str]:
    """Returns (action, reason) where action in allow|ask|deny."""
    if tool not in EXEC_TOOLS:
        return "allow", ""
    if tool == "systemctl":
        a = str(args.get("action") or "").lower().strip()
        if a in _SYSTEMCTL_ASK:
            return "ask", _SYSTEMCTL_ASK[a]
        return "allow", ""
    text = str(args.get("command") or args.get("code") or "")
    for pat, action, reason in DESTRUCTIVE:
        if pat.search(text):
            return action, reason
    for pat, action, reason in EXTERNAL:
        if pat.search(text):
            return action, reason
    return "allow", ""


_PREVIEW_KEYS = ("command", "code", "url", "path", "file", "task", "message",
                 "query", "pattern", "text", "content", "action", "op", "kind")


def preview_call(tool: str, args: dict | None, limit: int = 300) -> str:
    """One line saying what the user is actually being asked to allow.

    The prompt used to print only `args['command'] or args['code']`, so for every
    non-shell tool it rendered an empty string: `file_write` onto `~/.ssh/id_rsa`
    and `automation_job(op=rules, …)` — a rule that could zip Documents and POST
    them out — both asked permission while showing nothing about the action.
    Consent without information is not consent, so the preview is built from the
    arguments that carry meaning, redacted like anything else leaving the process.
    """
    a = dict(args or {})
    if tool == "systemctl":
        out = f"{a.get('action')} {a.get('value') or ''}".strip()
    elif a.get("command") or a.get("code"):
        out = str(a.get("command") or a.get("code"))     # as the shell prompt read
    else:
        bits, used = [], 0
        for k in _PREVIEW_KEYS:
            v = a.get(k)
            if v in (None, "", [], {}):
                continue
            piece = f"{k}={str(v)[:120]}"
            bits.append(piece)
            used += len(piece)
            if used >= limit:
                break
        if not bits and a:      # unknown shape: the key names still tell the user
            bits = [f"{k}={str(v)[:60]}" for k, v in list(a.items())[:6]]
        out = " ".join(bits)
    try:
        from . import privacy
        out, _n = privacy.redact(out)
    except Exception:
        pass
    return " ".join(str(out).split())[:limit]


def make_approver(mode: str = "cli"):
    """mode: cli (prompt), unattended (auto-deny), always (auto-approve, unsafe)."""
    if mode == "unattended":
        return lambda tool, args, reason: False
    if mode == "always":
        return lambda tool, args, reason: True
    def cli_approver(tool, args, reason) -> bool:
        preview = preview_call(tool, args)
        if not preview and "pending:" not in str(reason):
            # a capability ask already names the call inside `reason`; saying
            # "(no arguments)" on top of that is noise, not information
            preview = "(no arguments)"
        line = f"  ⚠ GUARD [{reason}] {tool}" + (f": {preview}" if preview else "")
        try:
            ans = input(f"{line}\n    allow? [y/N] ").strip().lower()
            return ans in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False
    return cli_approver


def check(tool: str, args: dict, enabled: bool = True, mode: str = "cli",
          approver=None) -> tuple[bool, str, str]:
    """Full gate. Returns (proceed, action, reason). ask → consults the approver.

    Layers: (1) the shell regex table above (classify), (2) for execution
    tools the AST-based risk classifier (bee.security.risk) which catches
    Python payloads the shell regexes cannot see (shutil.rmtree, os.remove,
    Path.unlink, subprocess, ...). The strictest layer wins. `classify`
    itself stays pure-regex — it is pinned by the verify suite.

    Phase 2: `approver` — optional (tool, args, reason) -> bool injected by
    the kernel (so WAITING_FOR_PERMISSION is a real, observable state). When
    None, the mode's built-in approver is used (back-compat).
    """
    if not enabled:
        return True, "allow", ""
    action, reason = classify(tool, args)
    if action == "allow" and tool in EXEC_TOOLS:
        from .security import risk as _risk
        d = _risk.classify_risk(tool, args)
        if d.action == "deny":
            action, reason = "deny", d.reason
        elif d.action == "ask":
            action, reason = "ask", d.reason
    if action == "allow":
        return True, "allow", ""
    if action == "deny":
        return False, "deny", reason
    ask = approver if approver is not None else make_approver(mode)
    ok = ask(tool, args, reason)
    return bool(ok), "ask" if ok else "deny", reason
