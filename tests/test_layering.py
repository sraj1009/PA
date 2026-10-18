"""Layering contract: bee.tools must not statically depend on bee.agent.

History: the knowledge graph reported a 4-file cycle
  bee/agent/loop.py -> bee/tools/__init__.py -> bee/tools/spawn_tool.py
  -> bee/agent/spawn.py -> bee/agent/loop.py
Re-measurement showed the tools->agent edge is a call-time (deferred)
import inside the spawn handler — the correct pattern — so no static
cycle exists. This test pins that: a regression that hoists the agent
import to module level would recouple the layers, make bee.tools
unimportable without the agent, and break independent tool testing.
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

BEE_DIR = Path(__file__).resolve().parent.parent / "bee"
ROOT = Path(__file__).resolve().parent.parent


def _top_level_agent_imports(path: Path) -> list[str]:
    """Module-level imports reaching bee.agent (deferred function-level
    imports are the sanctioned pattern and are ignored)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bad = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name == "bee.agent" or a.name.startswith("bee.agent."):
                    bad.append(f"import {a.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "bee.agent" or mod.startswith("bee.agent."):
                bad.append(f"from {mod} import ...")
            elif node.level and node.level >= 2:
                # relative import from bee/tools/* : level 2 == bee.* —
                # resolve the first name segment against the package root
                pass
            elif node.level == 1 and (node.module or "") in ("agent",) :
                bad.append(f"from .{node.module} import ...")
    # handle `from ..agent import x` (level=2, module='agent') explicitly
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.level == 2 \
                and (node.module or "").split(".")[0] == "agent":
            bad.append(f"from ..{node.module} import ...")
    return bad


def test_tools_have_no_static_agent_import():
    offenders = {}
    for p in sorted((BEE_DIR / "tools").glob("*.py")):
        bad = _top_level_agent_imports(p)
        if bad:
            offenders[p.name] = bad
    assert not offenders, (
        "static bee.tools -> bee.agent imports (hoisted agent imports "
        f"recouple the layers): {offenders}")


def test_tools_import_without_agent():
    """`import bee.tools` in a fresh interpreter must not load bee.agent."""
    code = (
        "import sys, bee.tools; "
        "loaded=[m for m in sys.modules if m=='bee.agent' or m.startswith('bee.agent.')]; "
        "print('AGENT_LOADED:'+','.join(sorted(loaded)) if loaded else 'AGENT_CLEAN')"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                       text=True, timeout=60, cwd=str(ROOT))
    assert r.returncode == 0, f"bee.tools import failed: {r.stderr[:500]}"
    line = [ln for ln in r.stdout.splitlines() if ln.startswith("AGENT_")]
    assert line and line[-1] == "AGENT_CLEAN", (
        f"importing bee.tools pulls in the agent layer: {line}")
