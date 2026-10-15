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
