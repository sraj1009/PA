"""A52: the eval headline must be the score of the run that ran.

`evals/results_summary.json` and the printed line are built from the LATEST row per
task id across the whole of `evals/results.jsonl`. That is useful as a ledger, but
as a headline it lied: a `only=["memory_write"]` run printed
`score: 21/21 overall`, carrying 20 passes earned by code that no longer exists —
and every report in this repo quotes that number.

A62 is the other two ways the same number lied: a task that never ran (cloud down)
was counted as a pass, and `evals/verify_suite.py` recomputed the cross-history
ledger into the git-tracked `evals/REPORT.md` under the words "(latest run)".
"""
from __future__ import annotations

import json

from bee.evals.runner import summarize


def _history(n=21, ok_ids=None):
    ok_ids = ok_ids if ok_ids is not None else {f"t{i}" for i in range(n)}
    return {f"t{i}": {"id": f"t{i}", "ts": "2026-10-01T00:00:00",
                       "ok": f"t{i}" in ok_ids} for i in range(n)}


def test_a_partial_run_is_not_reported_as_a_suite_score():
    s = summarize(_history(21), [{"id": "t0", "ok": True}])
    assert s["run_score"] == "1/1"
    assert s["run_n"] == 1
    assert s["carried"] == 20                      # 20 rows are from other runs
    assert s["single_run"] is False
    assert s["score"] == "21/21"                   # still the ledger, now labelled


def test_a_full_run_reports_one_number_with_nothing_carried():
    rows = [{"id": f"t{i}", "ok": i != 3} for i in range(21)]
    s = summarize(_history(21, ok_ids={f"t{i}" for i in range(21) if i != 3}), rows)
    assert s["single_run"] is True
    assert s["carried"] == 0
    assert s["run_score"] == s["score"] == "20/21"
    assert s["run_failures"] == s["failures"] == ["t3"]


def test_the_run_score_follows_this_run_not_the_history():
    """A regression that passed last week must not be masked by the old pass."""
    hist = _history(3, ok_ids={"t0", "t1", "t2"})
    s = summarize(hist, [{"id": "t1", "ok": False}])
    assert s["run_score"] == "0/1"
    assert s["run_failures"] == ["t1"]
    assert s["score"] == "3/3", "the ledger stays as it was — it is not the verdict"


def test_a_single_task_run_of_one_task_totals_one():
    s = summarize(_history(1, ok_ids=set()), [{"id": "t0", "ok": False}])
    assert s["single_run"] is True and s["carried"] == 0
    assert s["run_score"] == "0/1" and s["score"] == "0/1"


# ------------------------------------------------------------------ A62: skips
def _skips(n):
    return [{"id": f"s{i}", "ok": True, "skipped": True} for i in range(n)]


def test_a_task_that_never_ran_is_not_counted_as_a_pass():
    """`_run_tasks` writes a skip as `ok: True, skipped: True`, and `summarize`
    counted only `ok` — so a 21-task run with 5 cloud-skipped tasks printed
    `score: 21/21 — full suite` and set single_run: True. That is the number
    evals/REPORT.md and docs quote."""
    rows = [{"id": f"t{i}", "ok": True} for i in range(16)] + _skips(5)
    s = summarize(_history(21), rows)
    assert s["run_n"] == 16 and s["run_score"] == "16/16"
    assert s["skipped"] == 5 and s["skipped_ids"] == ["s0", "s1", "s2", "s3", "s4"]
    assert s["single_run"] is False, "a run that skipped a fifth of the suite is not a suite score"


def test_skips_do_not_rescue_a_failing_run():
    rows = [{"id": "t0", "ok": True}, {"id": "t1", "ok": False}] + _skips(1)
    s = summarize({"t0": {"id": "t0", "ts": "x", "ok": True},
                   "t1": {"id": "t1", "ts": "x", "ok": False},
                   "t2": {"id": "t2", "ts": "x", "ok": True}}, rows)
    assert s["run_score"] == "1/2" and s["run_failures"] == ["t1"]
    assert s["skipped"] == 1 and s["single_run"] is False


def test_pinned_model_skips_fastpath_only_tasks():
    """P1-3: a task asserting the fastpath tier has nothing to measure when the
    suite pins a model (the fastpath tier is bypassed by design), so it is
    SKIPPED — not failed — in both gate arms, and still scored interactively."""
    from bee.evals.runner import _should_skip

    class _Ctx:
        cfg = None

    t = {"id": "fp_block_run_code_rmtree", "skip_if": "pinned_model"}
    assert _should_skip(t, _Ctx(), model=None) is False
    assert _should_skip(t, _Ctx(), model="bee4b") is True
    assert _should_skip({"id": "x"}, _Ctx(), model="bee4b") is False


def test_the_resume_helper_takes_the_latest_row_by_ts(tmp_path, monkeypatch):
    """eval_resume.py picked "last row in file order", the runner's own summary
    compares `ts`, and the two definitions diverge on any ledger that was rotated,
    re-copied or hand-fixed (today's real results.jsonl is monotonic, so this is a
    latent disagreement, not an observed incident — but the resumer is the job that
    decides which tasks get re-run at 3 a.m.)."""
    import eval_resume

    ledger = tmp_path / "evals" / "results.jsonl"
    ledger.parent.mkdir()
    ledger.write_text(
        '{"ts": "2026-10-14T10:00:00", "id": "a", "ok": false}\n'
        '{"ts": "2026-10-13T10:00:00", "id": "a", "ok": true}\n', encoding="utf-8")
    monkeypatch.setattr(eval_resume, "ROOT", tmp_path)
    latest = eval_resume.latest_results()
    assert latest["a"]["ok"] is False, (
        "the resumer took the LAST ROW, so a stale pass in line 2 hides the newer "
        "regression and the task never re-runs")


def test_the_report_never_calls_the_ledger_the_latest_run(tmp_path, monkeypatch):
    """A62's user-visible half: evals/REPORT.md is git-tracked and said "(latest run
    19/21)" while the last real run scored 18/21 — the number came from the
    cross-history ledger."""
    from evals.verify_suite import _latest_llm_run, agent_eval_lines

    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "results.jsonl").write_text(
        '{"ts": "2026-10-10T10:00:00", "id": "a", "ok": true}\n'
        '{"ts": "2026-10-10T10:00:00", "id": "b", "ok": true}\n'
        '{"ts": "2026-10-13T10:00:00", "id": "b", "ok": false}\n', encoding="utf-8")
    (tmp_path / "evals" / "results_summary.json").write_text(json.dumps(
        {"ts": "2026-10-13T10:05:00", "n": 2, "score": "2/2", "run_score": "0/1",
         "run_n": 1, "run_failures": ["b"], "carried": 1, "skipped": 0,
         "single_run": False}), encoding="utf-8")
    monkeypatch.setattr("evals.verify_suite.ROOT", tmp_path)

    llm = _latest_llm_run()
    assert llm["score"] == "1/2" and llm["run_score"] == "0/1"
    text = "\n".join(agent_eval_lines(llm))
    assert "NOT a suite score" in text
    assert "(latest run" not in text, text
    # the ledger keeps its own number, but labelled as history, not as a verdict
    assert "**1/2** of 2 — historical, not one run" in text, text

    full = dict(llm, single_run=True, run_score="18/21", run_n=21, carried=0,
                skipped=0, run_failures=["x"])
    one = "\n".join(agent_eval_lines(full))
    assert "**18/21**" in one and "full suite in one run" in one
    assert "historical" not in one, one
    assert agent_eval_lines(None) == [
        "- Agent eval suite: no runs recorded yet — `python -m bee.cli eval` (needs the LLM)."]


# ------------------------------------------- P1-3: CI, repeats, suite shape
def test_wilson_interval_matches_the_textbook_values():
    """The printed score is a point estimate over tens of tasks; P1-3 publishes
    its 95% interval so a one-task gate delta is not read as a measurement.
    Normal approximation is useless at k=0/k=n (zero width where certainty is
    lowest), Wilson is not — pinned against its closed-form values."""
    from bee.evals.runner import wilson_interval
    assert wilson_interval(0, 0) is None
    lo, hi = wilson_interval(10, 10)
    assert hi == 1.0 and 0.70 < lo < 0.75
    lo0, hi0 = wilson_interval(0, 10)
    assert lo0 == 0.0 and abs(hi0 - 0.2775) < 0.005
    lo3, hi3 = wilson_interval(3, 4)
    assert abs(lo3 - 0.3006) < 0.005 and abs(hi3 - 0.9544) < 0.005


def test_the_run_score_is_published_with_its_confidence_interval():
    rows = [{"id": f"t{i}", "ok": i < 4} for i in range(6)]      # 4/6 = 66.7%
    s = summarize(_history(6, ok_ids={f"t{i}" for i in range(4)}), rows)
    assert s["run_score"] == "4/6"
    lo, hi = s["ci95"]
    assert lo < 66.7 < hi, s
    assert s["ci95_str"] == f"{lo:.1f}-{hi:.1f}%"
    assert summarize({"x": {"id": "x", "ts": "x", "ok": True}}, [])["ci95"] is None


def test_repeat_tasks_publish_per_rep_counts_and_a_flake_list():
    """A repeat task that failed some reps reports WHICH reps — "2/3" is flake
    evidence, "0/3" is a break; the flake list is what the gate prints next to
    a near-threshold verdict."""
    rows = [{"id": "rep", "ok": False, "reps_passed": 2, "reps_total": 3},
            {"id": "clean", "ok": True, "reps_passed": 2, "reps_total": 2}]
    s = summarize({"rep": {"id": "rep", "ts": "x", "ok": False},
                   "clean": {"id": "clean", "ts": "x", "ok": True}}, rows)
    assert s["flaky"] == [{"id": "rep", "passed": 2, "total": 3}]
    assert s["run_score"] == "1/2"


def test_every_repeat_rep_must_pass_and_all_reps_run(monkeypatch):
    """The old loop let a later passing rep overwrite an earlier failure, so
    `repeat: N` was documented as "every run must pass" and computed as "the
    last run passed". P1-3 also needs the true count: a failed middle rep with
    a passing last rep row would have been hidden."""
    from types import SimpleNamespace
    from bee.agent.loop import AgentResult
    from bee.evals import runner

    class FakeKernel:
        def __init__(self, oks):
            self.oks = list(oks)
            self.calls = []

        def run(self, task, session_id=None, model=None, on_event=None, max_iters=15):
            self.calls.append(session_id)
            ok = self.oks.pop(0)
            return SimpleNamespace(agent_result=AgentResult(
                output="19 * 23 = 437", ok=ok, error="" if ok else "rep failed"))

    tasks = [{"id": "rep_task", "task": "What is 19 * 23? Answer with just the number.",
              "expect": ["437"], "repeat": 3}]
    monkeypatch.setattr(runner, "load_tasks", lambda: tasks)

    ctx = SimpleNamespace(kernel=FakeKernel([True, False, True]), cancel_event=None)
    row = runner._run_tasks(ctx, None, None)[0]
    assert len(ctx.kernel.calls) == 3, "all reps run — the flake count is the evidence"
    assert row["ok"] is False, "a failed middle rep fails the task"
    assert (row["reps_passed"], row["reps_total"]) == (2, 3)

    ctx2 = SimpleNamespace(kernel=FakeKernel([True, True, True]), cancel_event=None)
    row2 = runner._run_tasks(ctx2, None, None)[0]
    assert row2["ok"] is True and row2["reps_passed"] == 3


def test_the_eval_suite_tasks_are_all_scored_by_a_nonvacuous_rubric():
    """P1-3 expanded the suite 21 -> ~60 for statistical power. An `expect: []`
    task with no event assertion can only ever pass vacuously, and the tier
    assertions have to respect how the events actually flow: fastpath tasks
    emit no fastpath route event (the first route event is the router's), while
    det tasks do (model="det")."""
    import pathlib
    import yaml
    tasks = yaml.safe_load(
        pathlib.Path("evals/tasks.yaml").read_text(encoding="utf-8"))["tasks"]
    ids = [t["id"] for t in tasks]
    assert len(ids) == len(set(ids))
    assert len(tasks) >= 60, f"expansion target is ~60 tasks, found {len(tasks)}"
    rubric = ("expect", "expect_any", "expect_tool", "expect_route",
              "expect_guard", "expect_verify", "expect_redact")
    for t in tasks:
        assert any(t.get(k) for k in rubric), f"{t['id']} has no rubric"
        rep = t.get("repeat", 1)
        assert isinstance(rep, int) and rep >= 1, t["id"]
    known_skip = {"cloud", "pinned_model"}
    for t in tasks:
        if t.get("skip_if"):
            assert t["skip_if"] in known_skip, (
                f"{t['id']}: unknown skip_if {t['skip_if']!r} would be silently ignored")
    for t in tasks:
        if str(t["id"]).startswith("fp_"):
            assert not t.get("expect_route"), (
                f"{t['id']} asserts a route event a fastpath never emits")
        if str(t["id"]).startswith("det_"):
            assert t.get("expect_route") == "det", (
                f"{t['id']} must pin the deterministic tier ticket")
