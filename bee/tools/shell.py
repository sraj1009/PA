"""shell — run a command on the host (workspace cwd). Use sandbox_run for heavy/destructive work."""
from __future__ import annotations

import re
import sys

from .base import envelope, T
from .cancelable import run_cancelable

_NOT_CMD = re.compile(r"^'([^'\r\n]+)' is not recognized as an internal or external command", re.M)
_CHAINED = re.compile(r"&|\|\|")


def _powershell_retry(command: str, err: str) -> bool:
    """cmd.exe refused the FIRST word, so nothing ran — PowerShell may know it.

    `shell=True` on Windows is cmd.exe; the model writes PowerShell cmdlets
    (episode store: `Get-Date`, `pwd` both failed 'not recognized'). Only the
    first word: if a later part failed, earlier parts already ran and a retry
    would run them twice. No `&`/`||` chains for the same reason."""
    if not sys.platform.startswith("win"):
        return False
    m = _NOT_CMD.search(err or "")
    words = command.split()
    return bool(m and words and m.group(1) == words[0] and not _CHAINED.search(command))


def shell_tools():
    def h_shell(ctx, command: str, timeout: int = 120):
        if not command or not str(command).strip():
            return {"error": "empty command"}
        command = str(command)
        if timeout is None or timeout <= 0:
            timeout = 120
        timeout = max(1, min(int(timeout), 900))
        try:
            cancel = getattr(ctx, "cancel_event", None)
            code, out, err, kind = run_cancelable(command, ctx.workspace,
                                                  timeout, cancel, shell=True)
            ran_in = ""
            if kind == "ok" and code != 0 and _powershell_retry(command, err):
                code, out, err, kind = run_cancelable(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                    ctx.workspace, timeout, cancel, shell=False)
                ran_in = "powershell"
            if kind == "cancelled":
                return envelope(command, code, out,
                                (err + "\n[cancelled: process tree killed]").strip())
            if kind == "timeout":
                return envelope(command, 124, out,
                                (err + f"\n[timeout after {timeout}s: process tree killed]").strip())
            res = envelope(command, code, out, err)
            if ran_in:
                res["shell"] = ran_in
            return res
        except Exception as e:
            return envelope(command, 1, error=str(e))

    return [
        T("shell",
          "Run a shell command with cwd=workspace: cmd.exe on Windows (`&&` chains work; a "
          "command cmd does not know, such as a PowerShell cmdlet like Get-Date, is retried "
          "once in PowerShell), sh elsewhere. "
          "Good for: git, pip, file ops, quick scripts. Destructive? Prefer sandbox_run. "
          "Args: command (string), timeout (seconds, default 120, max 900).",
          {"type": "object", "properties": {
              "command": {"type": "string"}, "timeout": {"type": "integer"}}, "required": ["command"]},
          h_shell),
    ]
