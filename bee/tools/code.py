"""code_run — execute Python in the host interpreter (workspace cwd).
For anything heavy/GPU/destructive use sandbox_run (Docker) instead.
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass

from .base import envelope

_PY = sys.executable


@dataclass
class T:
    name: str
    description: str
    parameters: dict
    handler: object


def code_tools():
    def h_code(ctx, code: str, timeout: int = 120):
        code = str(code or "")
        if not code.strip():
            return {"error": "empty code"}
        timeout = max(1, min(int(timeout or 120), 600))
        try:
            r = subprocess.run([_PY, "-c", code], capture_output=True, text=True,
                               cwd=str(ctx.workspace), timeout=timeout)
            return envelope("python", r.returncode, r.stdout or "", r.stderr or "")
        except subprocess.TimeoutExpired:
            return envelope("python", 124, error=f"timeout after {timeout}s")
        except Exception as e:
            return envelope("python", 1, error=str(e))

    return [
        T("code_run",
          "Run a Python snippet in the workspace directory (host interpreter, no network sandbox). "
          "Great for data wrangling, math, quick ML inference with installed libs, file processing. "
          "For GPU training / destructive work use sandbox_run. Args: code (python string), timeout (s, default 120, max 600). "
          "Print your final answer; it is captured as stdout.",
          {"type": "object", "properties": {"code": {"type": "string"}, "timeout": {"type": "integer"}},
           "required": ["code"]}, h_code),
    ]
