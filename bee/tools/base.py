"""Shared helpers for tools: output envelopes, safe eval, subprocess, truncation."""
from __future__ import annotations

import ast
import json
import operator
import subprocess
import sys
from pathlib import Path

MAX_CHARS = 12000


def truncate(s: str, limit: int = MAX_CHARS) -> str:
    s = str(s)
    if len(s) <= limit:
        return s
    keep = limit // 2
    return s[:keep] + f"\n...[truncated {len(s) - 2 * keep} chars]...\n" + s[-keep:]


def envelope(command: str | None = None, exit_code: int = 0, output: str = "", error: str = "") -> dict:
    d = {}
    if command:
        d["command"] = command
    d["exit_code"] = exit_code  # always present — missing keys read as "unknown" by models/validators
    if output:
        d["output"] = truncate(output)
    if error:
        d["error"] = truncate(error, 4000)
    if not d:
        d["output"] = "ok"
    return d


def run_subprocess(cmd, workspace: Path, timeout: int = 120) -> dict:
    if isinstance(cmd, str):
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           cwd=str(workspace), timeout=timeout)
    else:
        p = subprocess.run(cmd, capture_output=True, text=True, cwd=str(workspace), timeout=timeout)
    return {"exit_code": p.returncode, "stdout": p.stdout or "", "stderr": p.stderr or ""}


# --------------------------------------------------------------- safe eval
_ALLOWED_FUNCS = {
    "abs": abs, "round": round, "min": min, "max": max, "sum": sum, "len": len,
    "int": int, "float": float, "str": str, "list": list, "dict": dict, "set": set,
    "tuple": tuple, "pow": pow, "divmod": divmod, "sorted": sorted, "enumerate": enumerate,
    "range": range, "zip": zip, "map": map, "filter": filter, "any": any, "all": all,
    "isinstance": isinstance, "type": type, "repr": repr, "bin": bin, "hex": hex,
    "oct": oct, "chr": chr, "ord": ord, "reversed": reversed, "frozenset": frozenset,
    "bool": bool, "bytes": bytes, "complex": complex,
}
import math
import random
_ALLOWED_FUNCS.update({k: getattr(math, k) for k in (
    "sin", "cos", "tan", "asin", "acos", "atan", "atan2", "sqrt", "log", "log2", "log10",
    "exp", "floor", "ceil", "pi", "e", "factorial", "gcd", "lcm", "hypot", "degrees", "radians")
    if not isinstance(getattr(math, k, None), type)})

_BIN_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
    ast.Pow: pow,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_CMPS = {
    ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt, ast.LtE: operator.le,
    ast.Gt: operator.gt, ast.GtE: operator.ge,
}


def _ev(node, env):
    if isinstance(node, ast.Expression):
        return _ev(node.body, env)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in env:
            return env[node.id]
        if node.id in _ALLOWED_FUNCS:
            return _ALLOWED_FUNCS[node.id]
        raise ValueError(f"name not allowed: {node.id}")
    if isinstance(node, (ast.Tuple, ast.List)):
        return [_ev(e, env) for e in node.elts]
    if isinstance(node, ast.Dict):
        return {_ev(k, env): _ev(v, env) for k, v in zip(node.keys, node.values)}
    if isinstance(node, ast.Set):
        return {_ev(e, env) for e in node.elts}
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        return _BIN_OPS[type(node.op)](_ev(node.left, env), _ev(node.right, env))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_ev(node.operand, env))
    if isinstance(node, ast.BoolOp):
        vals = [_ev(v, env) for v in node.values]
        return all(vals) if isinstance(node.op, ast.And) else any(vals)
    if isinstance(node, ast.Compare):
        left = _ev(node.left, env)
        for op, comp in zip(node.ops, node.comparators):
            right = _ev(comp, env)
            if type(op) not in _CMPS or not _CMPS[type(op)](left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.Call):
        func = _ev(node.func, env)
        args = [_ev(a, env) for a in node.args]
        kwargs = {kw.arg: _ev(kw.value, env) for kw in node.keywords if kw.arg}
        return func(*args, **kwargs)
    if isinstance(node, ast.Subscript):
        val = _ev(node.value, env)
        sl = node.slice
        if isinstance(sl, ast.Slice):
            return val[_ev(sl.lower, env) if sl.lower else None:
                       _ev(sl.upper, env) if sl.upper else None:
                       _ev(sl.step, env) if sl.step else None]
        return val[_ev(sl, env)]
    if isinstance(node, ast.Attribute):
        val = _ev(node.value, env)
        if node.attr.startswith("_"):
            raise ValueError("attribute not allowed")
        return getattr(val, node.attr)
    if isinstance(node, ast.IfExp):
        return _ev(node.body, env) if _ev(node.test, env) else _ev(node.orelse, env)
    if isinstance(node, ast.JoinedStr):
        return "".join(_ev(v, env) for v in node.values)
    if isinstance(node, ast.FormattedValue):
        return format(_ev(node.value, env), node.conversion and "?" or "")
    raise ValueError(f"unsupported expression node: {type(node).__name__}")


def eval_safe(expression: str) -> str:
    """Evaluate a math/data expression safely (no imports, no statements)."""
    tree = ast.parse(expression, mode="eval")
    val = _ev(tree, {})
    s = str(val)
    return truncate(s, 4000)
