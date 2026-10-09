"""J2 — skill versioning + eval gate (contract tests, no live model).

Pins the lifecycle: create/update -> version bump + status=candidate (hidden
from the prompt); gate = structural check + bounded eval probe; pass ->
active; fail -> stays candidate with the reason recorded. The eval probe's
run_suite is faked (deterministic); skills dir + eval results go to tmp.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from bee import paths
from bee.evals import skillgate


GOOD_SKILL = """# demo-skill

description: A deterministic demo procedure for testing the skill gate.

## When to use
When a test needs a well-formed skill.

## How
1. do the thing
2. verify it

## Gotchas
- none known
"""


@pytest.fixture
def env(tmp_path, monkeypatch):
    skills = tmp_path / "skills"
    skills.mkdir()
    results = tmp_path / "results.jsonl"
    monkeypatch.setattr(paths, "SKILLS_DIR", skills)
    monkeypatch.setattr(paths, "EVAL_RESULTS", results)
    monkeypatch.setattr("bee.evals.gate.structural_task_ids", lambda: ["t1", "t2"])
    import bee.memory.md as md
    monkeypatch.setattr(md, "diary_add", lambda s: None)
    ctx = SimpleNamespace()
    return {"ctx": ctx, "skills": skills, "results": results}


def _make_skill(name: str, body: str = GOOD_SKILL, script: str | None = None):
    d = skillgate.skill_dir(name)
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(body, encoding="utf-8")
    if script is not None:
        (d / "script.py").write_text(script, encoding="utf-8")
    return d


def _fake_probe(env, monkeypatch, outcomes: dict[str, bool]):
    def fake_run_suite(ctx, model=None, only=None):
        return [{"id": tid, "ok": outcomes.get(tid, True), "skipped": False,
                 "model": "bee4b", "error": "", "seconds": 0.1,
                 "ts": "2026-10-06T00:00:00", "repeat": 1, "expect": None,
                 "output_excerpt": ""} for tid in (only or [])]
    monkeypatch.setattr("bee.evals.runner.run_suite", fake_run_suite)


# ----------------------------------------------------------------- metadata
def test_new_skill_bumps_v1_candidate(env):
    _make_skill("demo")
    meta = skillgate.bump_skill("demo", source="agent")
    assert meta["version"] == 1 and meta["status"] == "candidate"
    on_disk = json.loads(skillgate.meta_path("demo").read_text(encoding="utf-8"))
    assert on_disk["version"] == 1 and on_disk["source"] == "agent"


def test_update_bumps_version_and_stays_candidate(env):
    _make_skill("demo")
    skillgate.bump_skill("demo")
    m2 = skillgate.bump_skill("demo")
    assert m2["version"] == 2 and m2["status"] == "candidate"
    assert len(m2["history"]) == 2


def test_legacy_skill_without_meta_is_active(env):
    _make_skill("legacy-skill")
    m = skillgate.read_meta("legacy-skill")
    assert m["status"] == "active" and m["version"] == 1
    assert not skillgate.meta_path("legacy-skill").exists()   # never created


# ------------------------------------------------------------- structural
def test_structural_check_rejects_incomplete(env):
    assert not skillgate.structural_check("missing")[0]
    _make_skill("short", body="# s\ndescription: x")
    assert "too short" in skillgate.structural_check("short")[1]
    _make_skill("nodecl", body="# s\n\n## How\n1. steps\n1. more and more padding text here")
    ok, why = skillgate.structural_check("nodecl")
    assert not ok and "description" in why
    _make_skill("nosection", body="# s\ndescription: x\n\nplain text with no sections at all here")
    ok, why = skillgate.structural_check("nosection")
    assert not ok and "sections" in why
    _make_skill("badscript", script="def broken(:\n  pass")
    ok, why = skillgate.structural_check("badscript")
    assert not ok and "does not compile" in why
    _make_skill("demo")
    assert skillgate.structural_check("demo")[0]


def test_structural_check_accepts_good_skill_with_script(env):
    _make_skill("goodscript", script="def run():\n    return 1\n")
    ok, why = skillgate.structural_check("goodscript")
    assert ok and why == "ok"


# -------------------------------------------------------------------- gate
def test_gate_promotes_passing_candidate(env, monkeypatch):
    _make_skill("demo")
    skillgate.bump_skill("demo")
    _fake_probe(env, monkeypatch, {"t1": True, "t2": True})
    r = skillgate.gate_skill(env["ctx"], "demo")
    assert r["ok"] and r["status"] == "active", r
    m = skillgate.read_meta("demo")
    assert m["status"] == "active" and m["eval"]["passed"] is True
    assert m["eval"]["score"] == "2/2"
    assert m["history"][-1]["status"] == "active"


def test_gate_keeps_candidate_on_eval_regression(env, monkeypatch):
    # baseline: t1 and t2 both passed in the last recorded results
    env["results"].write_text(
        json.dumps({"id": "t1", "ok": True, "skipped": False, "model": "m",
                    "ts": "2026-10-05T00:00:00"}) + "\n" +
        json.dumps({"id": "t2", "ok": True, "skipped": False, "model": "m",
                    "ts": "2026-10-05T00:00:00"}) + "\n",
        encoding="utf-8")
    _make_skill("demo")
    skillgate.bump_skill("demo")
    _fake_probe(env, monkeypatch, {"t1": False, "t2": True})   # t1 regressed
    r = skillgate.gate_skill(env["ctx"], "demo")
    assert not r["ok"] and r["status"] == "candidate"
    m = skillgate.read_meta("demo")
    assert m["status"] == "candidate"
    assert "eval regression" in m["eval"]["reason"] and "t1" in m["eval"]["reason"]


def test_gate_keeps_candidate_on_bad_structure(env):
    _make_skill("broken", body="# b\ndescription: x")
    skillgate.bump_skill("broken")
    r = skillgate.gate_skill(env["ctx"], "broken")
    assert not r["ok"] and r["status"] == "candidate"
    assert "too short" in skillgate.read_meta("broken")["eval"]["reason"]


def test_gate_candidates_sweeps_batch(env, monkeypatch):
    _make_skill("good1"); skillgate.bump_skill("good1")
    _make_skill("good2"); skillgate.bump_skill("good2")
    _make_skill("bad"); skillgate.bump_skill("bad", source="teach-back")
    (skillgate.skill_dir("bad") / "SKILL.md").write_text("# b\ndescription: x\n",
                                                         encoding="utf-8")
    _fake_probe(env, monkeypatch, {"t1": True, "t2": True})
    r = skillgate.gate_candidates(env["ctx"])
    assert sorted(r["promoted"]) == ["good1", "good2"]
    assert r["rejected"] == ["bad"]
    assert skillgate.read_meta("good1")["status"] == "active"
    assert skillgate.read_meta("bad")["status"] == "candidate"


def test_gate_candidates_none(env):
    r = skillgate.gate_candidates(env["ctx"])
    assert r["gated"] == 0 and "no candidate" in r["note"]


# ------------------------------------------------------------- prompt index
def test_prompt_index_hides_candidates_and_shows_active(env):
    from bee.agent.context import skills_index
    from bee.config import Config
    _make_skill("shippable")
    skillgate.bump_skill("shippable")            # -> candidate (hidden)
    _make_skill("legacy-act")                    # no meta -> active (shown)
    idx = skills_index(Config())
    assert "legacy-act" in idx
    assert "shippable" not in idx
    # force-inclusion (the eval probe path) bypasses the filter
    idx2 = skills_index(Config(), force={"shippable"})
    assert "shippable" in idx2


def test_skill_create_tool_bumps_version(env):
    from bee.tools.skills import skill_tools
    tools = {t.name: t.handler for t in skill_tools()}
    ctx = SimpleNamespace()
    r1 = tools["skill_create"](ctx, name="via-tool", description="made by the agent loop",
                               content=GOOD_SKILL)
    assert r1["version"] == 1 and r1["status"] == "candidate"
    r2 = tools["skill_create"](ctx, name="via-tool", description="made by the agent loop",
                               content=GOOD_SKILL + "\n## Update\n- step 3\n")
    assert r2["version"] == 2
    # listing carries the version/status
    lst = {s["name"]: s for s in tools["skill_list"](ctx)["skills"]}
    assert lst["via-tool"]["version"] == 2 and lst["via-tool"]["status"] == "candidate"


# ------------------------- refusing a hallucinated skill before it hits disk (A30)
def test_placeholder_skill_is_rejected_and_nothing_is_written(env):
    """A 3B model called skill_create(name="new_skill_name",
    content="<full_markdown_content_with_a_description_line_and_sections>") and
    the tool wrote it. The nightly gate refuses to SHIP such a candidate, but it
    runs after the write — so the user's capability library kept a junk folder
    that `/skills` lists forever. Validation belongs at the chokepoint."""
    from bee.tools.skills import skill_tools
    tools = {t.name: t.handler for t in skill_tools()}
    ctx = SimpleNamespace()
    for bad in ("new_skill_name", "new-skill", "skill_name", "my_skill", "todo"):
        r = tools["skill_create"](ctx, name=bad, description="d", content=GOOD_SKILL)
        assert "error" in r and "placeholder" in r["error"], (bad, r)
    # too short / degenerate names are refused on those grounds instead
    for bad in ("x", "…", "  "):
        r = tools["skill_create"](ctx, name=bad, description="d", content=GOOD_SKILL)
        assert "error" in r, (bad, r)
    assert list(env["skills"].iterdir()) == [], "a rejected call must create no directory"


def test_unfilled_template_content_and_broken_script_are_rejected(env):
    from bee.tools.skills import skill_tools
    tools = {t.name: t.handler for t in skill_tools()}
    ctx = SimpleNamespace()
    r = tools["skill_create"](ctx, name="some_procedure", description="d",
                              content="<full_markdown_content_with_a_description>")
    assert "error" in r and "template" in r["error"], r
    assert not (env["skills"] / "some_procedure").exists()
    r2 = tools["skill_create"](ctx, name="another_procedure", description="d",
                               content=GOOD_SKILL, script="def (")
    assert "error" in r2 and "compile" in r2["error"], r2
    assert not (env["skills"] / "another_procedure").exists()


def test_real_skill_names_still_save_under_both_spellings(env):
    from bee.tools.skills import skill_tools
    tools = {t.name: t.handler for t in skill_tools()}
    ctx = SimpleNamespace()
    for good in ("pandas_csv_top_n_revenue", "docker-cleanup", "playwright_pdf.2"):
        r = tools["skill_create"](ctx, name=good, description="real procedure",
                                  content=GOOD_SKILL)
        assert r.get("ok") and r["status"] == "candidate", (good, r)
        assert (env["skills"] / good / "SKILL.md").exists()
