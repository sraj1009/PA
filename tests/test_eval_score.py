"""A52: the eval headline must be the score of the run that ran.

`evals/results_summary.json` and the printed line are built from the LATEST row per
task id across the whole of `evals/results.jsonl`. That is useful as a ledger, but
as a headline it lied: a `only=["memory_write"]` run printed
`score: 21/21 overall`, carrying 20 passes earned by code that no longer exists —
and every report in this repo quotes that number.
"""
from __future__ import annotations

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
