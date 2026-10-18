"""M12 close (2026-10-18): the `bee` package's import graph is measured from
source — module-level, `if __name__ == "__main__":` and function-level edges
alike — and its nontrivial strongly-connected components must be EXACTLY the
cycle groups documented below.

Why a lint and not a refactor: the register's original M12 text named two
lazy-import pairs (`cli <-> webapp`, `livekit.agent -> cli`); measuring the
FULL graph (2026-10-18: 155 modules, 440 unique edges — 222 of them
function-level) found **4** cycle groups, including one 24-module organ around
agent/kernel/tools/evals (P1-6 added `bee.practice`; the reason is recorded
below). Every group is closed by at least one lazy (or
`__main__`-guarded) edge — a top-level cycle cannot import at all, which is why
the import-time graph stays acyclic while the true dependency graph does not.

The enforcement is bidirectional, like the marker registry: a new member in a
group, a whole new group, or a group that no longer exists all fail; a
deliberate change is recorded by updating `DOCUMENTED_CYCLE_GROUPS` with a
reason. Scope: the `bee` package only (scripts import `bee`, never the reverse).
"""
from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

import bee

# Measured 2026-10-18. Line pointers are for orientation only (not asserted).
DOCUMENTED_CYCLE_GROUPS: dict[frozenset[str], str] = {
    frozenset({"bee.automation.models", "bee.automation.schedule"}):
        "schedule -> models is top-level (:23); models -> schedule is lazy (:281)",
    frozenset({"bee.memory.md", "bee.memory.search"}):
        "search -> md is top-level (:12); md -> search is lazy (:26, :83, :223)",
    frozenset({"bee.agent.answer_postprocess", "bee.agent.context",
               "bee.agent.fastpaths", "bee.agent.loop", "bee.agent.offline",
               "bee.agent.router", "bee.agent.tool_dispatch", "bee.automation",
               "bee.automation.tools", "bee.automation.worker", "bee.evals.gate",
               "bee.evals.runner", "bee.evals.skillgate", "bee.kernel",
               "bee.kernel.kernel", "bee.kernel.memory_if", "bee.kernel.session",
               "bee.kernel.tools_bus", "bee.pipeline.build_sft", "bee.practice",
               "bee.scheduler", "bee.tools", "bee.tools.planner",
               "bee.tools.skills"}):
        "the agent/kernel/tools/evals organ — one dependency blob; every path "
        "back closes through a lazy edge (agent.loop -> kernel :237, "
        "scheduler -> evals.gate :296, tools -> automation :41, ...). P1-6 "
        "added bee.practice (practice -> agent.loop top-level; "
        "automation.worker -> practice lazy in _fn_practice)",
    frozenset({"bee.cli", "bee.livekit.agent", "bee.livekit.transport",
               "bee.webapp"}):
        "cli -> webapp (:621-631) and -> livekit.transport (:724) lazy; "
        "livekit.agent -> cli lazy (:312); transport -> agent lazy (:82); "
        "webapp -> cli only under `if __name__ == '__main__'` (:605)",
}


def _module_name(pkg_dir: Path, path: Path) -> str:
    rel = path.relative_to(pkg_dir.parent).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _resolve(cur: str, is_init: bool, level: int, mod: str | None,
             names: list[str], modset: set[str]) -> list[str]:
    """Intra-package target modules of one ImportFrom (module paths only)."""
    out: list[str] = []
    if level:                              # relative import
        base = cur.split(".")
        if not is_init:                    # ordinary module: drop its own name
            base = base[:-1]
        if level > 1:
            base = base[: len(base) - (level - 1)]
        prefix = ".".join(base + ([mod] if mod else []))
        if mod:
            out.append(prefix)
        else:                              # `from . import x` — x may be a module
            out += [f"{prefix}.{n}" for n in names]
    elif mod and (mod == "bee" or mod.startswith("bee.")):
        out.append(mod)
        out += [f"{mod}.{n}" for n in names if f"{mod}.{n}" in modset]
    return [t for t in out if t in modset]


class _Collector(ast.NodeVisitor):
    """Every import in the module — any nesting level."""

    def __init__(self, mod: str, is_init: bool, modset: set[str]):
        self.mod = mod
        self.is_init = is_init
        self.modset = modset
        self.targets: list[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        for a in node.names:
            if a.name == "bee" or a.name.startswith("bee."):
                self.targets.append(a.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.targets += _resolve(self.mod, self.is_init, node.level,
                                 node.module, [a.name for a in node.names],
                                 self.modset)


def _import_graph(pkg_dir: Path) -> dict[str, set[str]]:
    modules = {_module_name(pkg_dir, p): p for p in pkg_dir.rglob("*.py")}
    modset = set(modules)
    succ: dict[str, set[str]] = defaultdict(set)
    for mod, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        collector = _Collector(mod, path.name == "__init__.py", modset)
        collector.visit(tree)
        for dst in collector.targets:
            succ[mod].add(dst)
            succ.setdefault(dst, set())
    return dict(succ)


def _nontrivial_sccs(succ: dict[str, set[str]]) -> list[list[str]]:
    """Tarjan, recursive (the package is ~150 modules)."""
    import sys as _sys

    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on: dict[str, bool] = {}
    stack: list[str] = []
    comps: list[list[str]] = []
    counter = [0]

    def strong(v: str) -> None:
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on[v] = True
        for w in succ[v]:
            if w not in index:
                strong(w)
                low[v] = min(low[v], low[w])
            elif on.get(w):
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp: list[str] = []
            while True:
                w = stack.pop()
                on[w] = False
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                comps.append(sorted(comp))

    old_limit = _sys.getrecursionlimit()
    _sys.setrecursionlimit(max(old_limit, 10000))
    try:
        for v in sorted(succ):
            if v not in index:
                strong(v)
    finally:
        _sys.setrecursionlimit(old_limit)
    return comps


def test_m12_import_cycle_groups_are_exactly_the_documented_ones():
    pkg_dir = Path(bee.__file__).resolve().parent
    graph = _import_graph(pkg_dir)
    assert len(graph) > 100, (
        f"graph walk found only {len(graph)} modules — the walker broke, "
        "not the package")

    found = {frozenset(comp) for comp in _nontrivial_sccs(graph)}
    documented = set(DOCUMENTED_CYCLE_GROUPS)
    if found != documented:
        lines = ["import-cycle groups changed "
                 "(see DOCUMENTED_CYCLE_GROUPS in tests/test_import_graph.py):"]
        for group in sorted(found - documented, key=len):
            lines.append(f"  NEW group ({len(group)}): " + ", ".join(sorted(group)))
        for group in sorted(documented - found, key=len):
            lines.append(f"  GONE group ({len(group)}): " + ", ".join(sorted(group)))
        raise AssertionError("\n".join(lines))
