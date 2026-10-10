"""code_run — execute Python in the host interpreter (workspace cwd).
For anything heavy/GPU/destructive use sandbox_run (Docker) instead.
"""
from __future__ import annotations

import os
import sys

from .. import paths
from .base import envelope, T
from .cancelable import run_cancelable

_PY = sys.executable


def _child_env() -> dict:
    """The snippet's interpreter: UTF-8 stdio, and BEE's own package importable.

    Piped, a Windows child writes stdout in cp1252, so `print('✓')` died with
    UnicodeEncodeError (exit 1) and any answer containing an arrow, a check
    mark or non-Latin text could not be computed at all. And `python -c` puts
    only the cwd on sys.path, so with any workspace but the project root
    `import bee.dsa` — which the skill index tells the model to use — failed.
    The root goes AFTER the user's own PYTHONPATH so it shadows nothing of theirs."""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    root = str(paths.PROJECT_ROOT)
    parts = [p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p]
    if root not in parts:
        env["PYTHONPATH"] = os.pathsep.join(parts + [root])
    return env


def code_tools():
    def h_code(ctx, code: str, timeout: int = 120):
        code = str(code or "")
        if not code.strip():
            return {"error": "empty code"}
        timeout = max(1, min(int(timeout or 120), 600))
        try:
            cancel = getattr(ctx, "cancel_event", None)
            src, out, err, kind = run_cancelable([_PY, "-c", code], ctx.workspace,
                                                 timeout, cancel, shell=False,
                                                 env=_child_env(), encoding="utf-8")
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
