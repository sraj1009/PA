"""shell — run a command on the host (workspace cwd). Use sandbox_run for heavy/destructive work."""
from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass

from .base import envelope


@dataclass
class T:
    name: str
    description: str
    parameters: dict
    handler: object


def shell_tools():
    def h_shell(ctx, command: str, timeout: int = 120):
        if not command or not str(command).strip():
            return {"error": "empty command"}
        command = str(command)
        if timeout is None or timeout <= 0:
            timeout = 120
        timeout = max(1, min(int(timeout), 900))
        try:
            r = subprocess.run(command, shell=True, capture_output=True, text=True,
                               cwd=str(ctx.workspace), timeout=timeout)
            return envelope(command, r.returncode, r.stdout or "", r.stderr or "")
        except subprocess.TimeoutExpired:
            return envelope(command, 124, error=f"timeout after {timeout}s (killed)")
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
