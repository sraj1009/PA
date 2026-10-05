"""calculator — safe expression evaluation (AST whitelist, no imports)."""
from __future__ import annotations

from dataclasses import dataclass

from .base import eval_safe


@dataclass
class T:
    name: str
    description: str
    parameters: dict
    handler: object


def calc_tools():
    def h_calc(ctx, expression: str):
        expression = str(expression or "").strip()
        if not expression:
            return {"error": "empty expression"}
        try:
            return {"expression": expression, "result": eval_safe(expression)}
        except Exception as e:
            return {"error": f"cannot evaluate: {e}", "hint": "python math only; no imports/assignments. For real computation use code_run."}

    return [
        T("calculator",
          "Evaluate a math expression safely: numbers, +-*/**%, comparisons, lists/dicts, "
          "min/max/sum/sorted/len, math functions (sqrt, log, sin, cos, factorial, gcd...). "
          "Example: 'sum([1,2,3]) + sqrt(16)'. Args: expression.",
          {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]},
          h_calc),
    ]
