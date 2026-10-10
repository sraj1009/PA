"""automation_job create validation (A43).

Verified by probe on 2026-10-09: five jobs — `at: "tomorrow 9am"`, daily with no
time, daily `time: "8 in the morning"`, weekly with no time, one_time with an empty
`at` — were stored as `pending, enabled=True, next_run=""` while the tool answered
`{"created": …, "next_run": ""}` and the note "authorized automation". Nothing could
ever fire them. Same class as A24b ("a reminder that succeeded into the store while
the user waited"), one layer down: the path the MODEL uses.
"""
from __future__ import annotations

import pytest

from bee.automation.store import JobStore
from bee.automation.tools import automation_job
from bee.automation.worker import JobWorker


class _Ctx:
    pass


def _worker(tmp_path):
    ctx = _Ctx()
    ctx.automation_worker = JobWorker(ctx=None, kernel=None,
                                      store=JobStore(tmp_path / "jobs.json"),
                                      default_timezone="Asia/Kolkata")
    return ctx


NEVER_FIRES = [
    ({"op": "create", "kind": "one_time", "at": "tomorrow 9am", "task": "stretch"}, "at"),
    ({"op": "create", "kind": "one_time", "task": "x"}, "at"),
    ({"op": "create", "kind": "daily", "task": "standup"}, "time"),
    ({"op": "create", "kind": "daily", "time": "8 in the morning", "task": "s"}, "time"),
    ({"op": "create", "kind": "weekly", "task": "review"}, "time"),
]


@pytest.mark.parametrize("args,field", NEVER_FIRES)
def test_a_job_that_can_never_fire_is_refused_and_not_stored(tmp_path, args, field):
    ctx = _worker(tmp_path)
    out = automation_job(ctx, **args)
    assert "created" not in out, out
    assert "can never fire" in out["error"], out
    assert field in out["error"], f"the message must name {field}: {out['error']}"
    assert ctx.automation_worker.jobs() == [], "a deaf job was persisted"


def test_a_valid_schedule_is_still_accepted(tmp_path):
    ctx = _worker(tmp_path)
    out = automation_job(ctx, op="create", kind="daily", time="08:00",
                         task="schedule briefing")
    assert out.get("created") and out["next_run"], out
    jobs = ctx.automation_worker.jobs()
    assert len(jobs) == 1 and jobs[0].enabled and jobs[0].next_run


def test_every_seconds_as_text_is_a_clear_error_not_a_python_one(tmp_path):
    """A43b: `int('1h')` escaped the tool as ValueError, so the model saw
    'invalid literal for int() with base 10' — nothing it can correct."""
    ctx = _worker(tmp_path)
    out = automation_job(ctx, op="create", kind="interval", every_seconds="1h",
                         task="poll")
    assert "every_seconds" in out["error"] and "1h" in out["error"], out
    assert "base 10" not in out["error"], out


def test_numeric_strings_still_work(tmp_path):
    ctx = _worker(tmp_path)
    out = automation_job(ctx, op="create", kind="interval", every_seconds="3600",
                         task="poll")
    assert out.get("created"), out


def test_day_names_are_accepted_and_land_on_the_right_days(tmp_path):
    ctx = _worker(tmp_path)
    out = automation_job(ctx, op="create", kind="weekly", days=["mon", "tue"],
                         time="09:00", task="status")
    assert out.get("created"), out
    job = ctx.automation_worker.jobs()[0]
    assert job.trigger.days == [0, 1], job.trigger.days


def test_an_unknown_day_is_refused_rather_than_scheduled_wrong(tmp_path):
    ctx = _worker(tmp_path)
    out = automation_job(ctx, op="create", kind="weekly", days=["funday"],
                         time="09:00", task="status")
    assert "days" in out.get("error", ""), out
    assert ctx.automation_worker.jobs() == []


def test_an_unknown_trigger_kind_is_named(tmp_path):
    ctx = _worker(tmp_path)
    out = automation_job(ctx, op="create", kind="moonrise", task="look up")
    assert "moonrise" in out.get("error", ""), out


def test_rules_add_reports_a_bad_rate_limit_cleanly(tmp_path):
    ctx = _worker(tmp_path)
    out = automation_job(ctx, op="rules", rule_op="add", kind="timer",
                         message="ping", max_per_hour="six")
    assert "max_per_hour" in out.get("error", ""), out
