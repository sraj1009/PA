"""shell — run a command on the host (workspace cwd). Use sandbox_run for heavy/destructive work."""
from __future__ import annotations

import shlex

from .base import envelope, T
from .cancelable import run_cancelable

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
            if kind == "cancelled":
                return envelope(command, code, out,
                                (err + "\n[cancelled: process tree killed]").strip())
            if kind == "timeout":
                return envelope(command, 124, out,
                                (err + f"\n[timeout after {timeout}s: process tree killed]").strip())
            return envelope(command, code, out, err)
        except Exception as e:
            return envelope(command, 1, error=str(e))

    return [
        T("shell",
          "Run a shell command (PowerShell on Windows, bash elsewhere) with cwd=workspace. "
          "Good for: git, pip, file ops, quick scripts. Destructive? Prefer sandbox_run. "
          "Args: command (string), timeout (seconds, default 120, max 900).",
          {"type": "object", "properties": {
              "command": {"type": "string"}, "timeout": {"type": "integer"}}, "required": ["command"]},
          h_shell),
    ]
