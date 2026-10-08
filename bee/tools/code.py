"""code_run — execute Python in the host interpreter (workspace cwd).
For anything heavy/GPU/destructive use sandbox_run (Docker) instead.
"""
from __future__ import annotations

import sys

from .base import envelope, T
from .cancelable import run_cancelable

_PY = sys.executable

def code_tools():
    def h_code(ctx, code: str, timeout: int = 120):
        code = str(code or "")
        if not code.strip():
            return {"error": "empty code"}
        timeout = max(1, min(int(timeout or 120), 600))
        try:
            cancel = getattr(ctx, "cancel_event", None)
            src, out, err, kind = run_cancelable([_PY, "-c", code], ctx.workspace,
                                                 timeout, cancel, shell=False)
            if kind == "cancelled":
                return envelope("python", src, out,
                                (err + "\n[cancelled: process killed]").strip())
            if kind == "timeout":
                return envelope("python", 124, out,
                                (err + f"\n[timeout after {timeout}s: process killed]").strip())
            return envelope("python", src, out, err)
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
