"""Planning inputs (A45b / A45c / A45d).

The 21-task eval kept failing `plan_complex` and `dsa_graph`. Reading the outputs
showed neither was "the model is weak" — both were missing inputs:

  A45b the planner was told to "mention the tool(s) to use" but never given the
       tool list, so it invented `LoadCSVFileUsingLoaderTool(...)`;
  A45c the skill index showed only a one-line description, so the model knew a
       `dsa` skill existed but not that its modules are `bee.dsa.*` — and the live
       answer said "there is no module named 'bee_dsa'";
  A45d the task asserted the literal 'pandas' while a correct plan named `polars`.
"""
from __future__ import annotations

import json
import threading

from bee.agent import context as ctxmod
from bee.agent.client import LLMError
from bee.config import load_config
from bee.evals.runner import check_task


class _Recorder:
    """Captures the prompt the planner actually sends, returns a canned plan."""

    def __init__(self):
        self.prompts = []

    def chat(self, name, messages, tools=None, **kw):
        self.prompts.append(messages[-1]["content"])
        return {"content": "1. file_read sales.csv\n2. polars scan + group_by", "usage": {}}

    def ollama_up(self):
        return True


def _ctx():
    from bee.agent.context import Context
    from bee.tools import planner as P
    r = _Recorder()
    cfg = load_config()
    cfg.cloud.enabled = False
    c = Context(cfg, workspace=cfg.workspace, client=r, guard_on=True,
                guard_mode="unattended", episodes_on=False, rag_on=False,
                cancel_event=threading.Event())
    return c, r, P


def test_the_planner_is_shown_the_tools_it_may_use():
    c, rec, P = _ctx()
    tool = {t.name: t for t in P.planner_tools()}["planner"]
    out = tool.handler(c, task="Plan how to analyze a 50MB CSV sales file.")
    prompt = rec.prompts[-1]
    assert "Available tools:" in prompt, prompt[:400]
    assert "file_read" in prompt and "code_run" in prompt
    assert out["plan"].startswith("1.")


def test_the_planner_prompt_names_no_invented_tools_of_its_own():
    """Regression against the exact failure: with no tool list the model produced
    `LoadCSVFileUsingLoaderTool(...)` — a step the agent cannot execute."""
    c, rec, P = _ctx()
    tool = {t.name: t for t in P.planner_tools()}["planner"]
    tool.handler(c, task="Plan (do not execute) how you would analyze a 50MB CSV sales file.")
    prompt = rec.prompts[-1]
    assert "never invent a tool name" in prompt
    assert "does not actually need" in prompt, "relevance guard must stay"
    assert "Skills" in prompt, "the skill index must reach the planner too"


def test_the_skill_index_carries_the_module_names(tmp_path, monkeypatch):
    """A45c: the description alone left the model guessing `bee_dsa`.
    Hermetic by design — the suite redirects SKILLS_DIR (A25c), so the skill is
    written into the test's own copy rather than reading the user's library."""
    from bee import paths
    sk = tmp_path / "dsa"
    sk.mkdir()
    (sk / "SKILL.md").write_text(
        "# dsa\n\ndescription: algorithm work.\n\n"
        "```python\nfrom bee.dsa.graphs import dijkstra\n```\n", encoding="utf-8")
    monkeypatch.setattr(paths, "SKILLS_DIR", tmp_path)
    idx = ctxmod.skills_index(load_config(), force=None)
    assert "imports:" in idx, idx[:400]
    assert "bee.dsa.graphs" in idx, idx


def test_a_skill_without_imports_is_left_untouched():
    assert ctxmod._module_hint("# just prose\nno code here", "x") == ""


def _res(out, ok=True):
    class R:
        pass
    r = R()
    r.ok, r.output, r.error = ok, out, ""
    return r


def test_expect_any_accepts_an_equal_choice_but_not_silence():
    t = {"id": "plan_complex", "expect_any": ["pandas", "polars", "duckdb"]}
    assert check_task(t, _res("I will load it with polars and group_by"), [])[0] is True
    ok, why = check_task(t, _res("1) read the file 2) aggregate"), [])
    assert ok is False and "at least one of" in why, why


def test_expect_still_requires_every_hard_value():
    """expect_any must not weaken `expect`: computed values stay mandatory."""
    t = {"id": "x", "expect": ["588"], "expect_any": ["pandas", "polars"]}
    assert check_task(t, _res("polars gives 588"), [])[0] is True
    assert check_task(t, _res("polars gives 308"), [])[0] is False
    assert check_task(t, _res("pandas gives 588"), [])[0] is True


def test_the_eval_tasks_yaml_uses_the_new_field_correctly():
    import yaml, pathlib
    tasks = yaml.safe_load(pathlib.Path("evals/tasks.yaml").read_text(encoding="utf-8"))["tasks"]
    pc = next(t for t in tasks if t["id"] == "plan_complex")
    assert "expect" not in pc, "the pandas-only literal must not come back"
    assert set(pc["expect_any"]) >= {"pandas", "polars"}
