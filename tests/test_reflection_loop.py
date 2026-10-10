"""The self-improvement flywheel (A40): lesson quality, one chokepoint, no silence.

A lesson is written into memory/lessons/ and then injected into EVERY future
system prompt by `context.recent_lessons()`, so a bad lesson is a permanent wrong
example. Two of the ones stored on this machine were the exact plumbing-ramble the
loop already refuses to ship — they were allowed to be *learned*.

Also pinned: reflection now runs at the kernel (every surface learns, not just the
REPL), `learning.reflect` is a switch with a real reader, a cancelled task teaches
nothing, and a lesson that could not be written is reported rather than swallowed.
"""
from __future__ import annotations

import threading

import pytest

from bee import paths
from bee.agent import reflection
from bee.agent.context import Context
from bee.agent.loop import AgentResult
from bee.config import load_config
from bee.kernel import AgentKernel

# Verbatim from memory/lessons/2026-10-05.md and 2026-10-06.md on this machine.
CONTAMINATED = [
    "- worked: No issues identified in task execution as the prompt did not include "
    "specific function calls for execution.\n- failed: None\n- next: Provide more details "
    "on needed actions to proceed.",
    "- worked: None of the provided functions support directly opening Chrome or navigating "
    "to specific pages in it.\n- failed: none\n- next: Use a different approach.",
    "- worked: Successfully identified the limitations of the system.\n- failed: None\n"
    "- next: Explore how external information can be integrated.",
    "- worked: Successfully completed 21 iterations, used one tool for web scraping.\n"
    "- failed: none\n- next: nothing",
    "- worked: Successfully opened grok.com in the default browser within 2 cloud iterations "
    "and no tool failures.\n- failed: none\n- next: keep going",
    "- worked: None, task stopped early.\n- failed: Stopped by user prematurely.\n"
    "- next: Revisit the task with a more detailed plan.",
]
USEFUL = [
    "- worked: Browser successfully opened grok.com, typed the query and pressed Enter.\n"
    "- failed: none\n- next: Confirm the page finished loading before reporting success.",
    "- worked: Used web_search to find the RTX 3050 specs and quoted the VRAM figure.\n"
    "- failed: none\n- next: Re-read the spec sheet before stating clock speeds.",
    "- worked: Read the CSV columns before computing, so the totals matched.\n"
    "- failed: none\n- next: Print the column names first on any new file.",
    "- worked: Gave the multiplication as a number, not as an explanation.\n"
    "- failed: none\n- next: Keep the spoken part under four sentences.",
]


def _res(**kw) -> AgentResult:
    base = dict(output="done", ok=True, model="local", iterations=3, tool_calls=1)
    base.update(kw)
    return AgentResult(**base)


@pytest.mark.parametrize("lesson", CONTAMINATED)
def test_contaminated_lessons_from_the_real_store_are_rejected(lesson):
    ok, why = reflection._usable(lesson, _res())
    assert not ok and why, lesson[:60]


@pytest.mark.parametrize("lesson", USEFUL)
def test_task_specific_lessons_are_still_kept(lesson):
    """The gate must not become a blunt object: lessons that name the tool or the
    outcome are the whole point of the flywheel."""
    ok, why = reflection._usable(lesson, _res())
    assert ok, why


def test_lesson_is_written_and_returned(monkeypatch, tmp_path):
    dest = tmp_path / "lessons"
    monkeypatch.setattr(paths, "LESSONS_DIR", dest)
    client = _StubClient("- worked: opened the file first\n- failed: none\n- next: keep it")
    ctx = _Ctx(client)
    lesson = reflection.reflect(ctx, "Summarise the report in the workspace", _res())
    assert "opened the file first" in lesson
    assert list(dest.glob("*.md")), "no lesson file written"


def test_cancelled_task_writes_no_lesson(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "LESSONS_DIR", tmp_path / "lessons")
    client = _StubClient("- worked: something")
    ctx = _Ctx(client)
    r = _res()
    r.cancelled = True
    assert reflection.reflect(ctx, "Open the notes app and type the draft", r) == ""
    assert client.calls == [], "a cancelled task still cost a local-model call"


def test_rejected_lesson_is_not_written(monkeypatch, tmp_path):
    dest = tmp_path / "lessons"
    monkeypatch.setattr(paths, "LESSONS_DIR", dest)
    client = _StubClient(CONTAMINATED[0])
    ctx = _Ctx(client)
    assert reflection.reflect(ctx, "Open the notes app and type the draft", _res()) == ""
    assert not list(dest.glob("*.md")), "contaminated lesson reached the store"


def test_write_failure_is_reported_not_swallowed(monkeypatch, tmp_path, caplog):
    """A7's rule: a quiet failure looks like a success. Returning the lesson while
    the append failed would tell the user 'lesson saved' about nothing."""
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file, not a directory")
    client = _StubClient(USEFUL[0])
    ctx = _Ctx(client)          # build first: load_config() re-creates LESSONS_DIR
    monkeypatch.setattr(paths, "LESSONS_DIR", blocker / "lessons")
    with caplog.at_level("WARNING", logger="bee.reflect"):
        assert reflection.reflect(ctx, "Open the notes app and type the draft", _res()) == ""
    assert any("could not write lesson" in r.getMessage() for r in caplog.records)


# ----------------------------------------------------- kernel-owned flywheel

class _StubClient:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls: list = []

    def chat(self, name, messages, tools=None, **kw):
        self.calls.append((name, [dict(m) for m in messages]))
        if not self.answers:
            return {"content": "(no scripted reply)", "usage": {}}
        return {"content": self.answers.pop(0), "usage": {}}

    def ollama_up(self):
        return True

    def _has_ollama(self):
        return True

    def models_list(self):
        return ["bee4b"]


def _Ctx(client, lessons_dir=None, reflect=True):
    cfg = load_config()
    cfg.cloud.enabled = False
    cfg.learning.reflect = reflect
    ctx = Context(cfg, workspace=cfg.workspace, client=client, guard_on=True,
                  guard_mode="unattended", episodes_on=False, rag_on=False,
                  cancel_event=threading.Event())
    return ctx


def _kernel(tmp_path, client, lessons_dir=None, reflect=True):
    ctx = _Ctx(client, reflect=reflect)
    ctx.workspace = tmp_path
    k = AgentKernel(ctx, approver=lambda t, a, r: False,
                    sessions_dir=tmp_path / "sessions",
                    receipts_path=tmp_path / "receipts.jsonl")
    ctx.kernel = k
    return k, ctx


LONG_TASK = ("Write a short summary of the quarterly numbers and list the three "
             "things that changed since last quarter.")


def test_the_kernel_reflects_for_a_non_repl_surface(monkeypatch, tmp_path):
    """A40b: web / voice / LiveKit / scheduled / proactive tasks all end at the
    kernel, but reflection lived in the REPL loop — so those surfaces READ lessons
    in their prompt and never produced one. Now one chokepoint writes them."""
    dest = tmp_path / "lessons"
    monkeypatch.setattr(paths, "LESSONS_DIR", dest)
    client = _StubClient("Here is the summary: revenue rose, costs were flat.",
                         USEFUL[0])
    k, _ctx = _kernel(tmp_path, client)
    r = k.run(LONG_TASK, session_id="web-chat-1")     # a web-session id, not "repl"
    assert r.ok is True
    files = list(dest.glob("*.md"))
    assert files, "a non-REPL task produced no lesson"
    assert "opened grok.com" in files[0].read_text(encoding="utf-8")


def test_learning_switch_really_stops_the_write(monkeypatch, tmp_path):
    """A config key read by no code is a fake kill-switch (A12). Prove this one
    both reaches the kernel AND actually stops the call."""
    dest = tmp_path / "lessons"
    monkeypatch.setattr(paths, "LESSONS_DIR", dest)
    client = _StubClient("Here is the summary: revenue rose.", USEFUL[0])
    k, _ctx = _kernel(tmp_path, client, reflect=False)
    r = k.run(LONG_TASK, session_id="web-chat-2")
    assert r.ok is True
    assert not list(dest.glob("*.md"))
    assert len(client.calls) == 1, "reflection still spent a local-model call when disabled"


def test_reflection_never_breaks_the_users_turn(monkeypatch, tmp_path):
    """It is an optimization: an exception inside it must not surface as a failed
    task (the old REPL call was wrapped in `except: pass`, which also hid real bugs)."""
    dest = tmp_path / "lessons"
    monkeypatch.setattr(paths, "LESSONS_DIR", dest)
    client = _StubClient("Here is the summary: revenue rose.")
    k, _ctx = _kernel(tmp_path, client)

    def boom(*a, **kw):
        raise RuntimeError("reflection exploded")

    monkeypatch.setattr(reflection, "reflect", boom)
    r = k.run(LONG_TASK, session_id="web-chat-3")
    assert r.ok is True, "a reflection crash leaked into the user's result"


def test_the_eval_does_not_reflect(monkeypatch, tmp_path):
    """The scored run must stay deterministic: no extra model call per task and no
    lessons growing the prompt mid-run."""
    from bee.evals import runner

    seen = {}

    def spy(ctx, model=None, only=None):
        seen["reflect"] = ctx.cfg.learning.reflect
        return []

    class _null:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(runner, "_run_suite", spy)
    monkeypatch.setattr(runner, "_isolated_memory", lambda: _null())
    monkeypatch.setattr(runner, "_restore_workspace", lambda p: _null())
    ctx = _Ctx(_StubClient())
    ctx.workspace = tmp_path
    ctx.cfg.learning.reflect = True
    runner.run_suite(ctx)
    assert seen["reflect"] is False
    assert ctx.cfg.learning.reflect is True        # restored for the caller
