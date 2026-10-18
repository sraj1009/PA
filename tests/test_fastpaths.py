"""Tests for fast paths (instant pure-Python answers), engine selection, and
cloud -> local teach-back.

Run:  python -m pytest tests/test_fastpaths.py -q
"""
from __future__ import annotations

import json
import re
import time

import pytest

from bee import paths as bee_paths
from bee import scheduler
from bee.agent import engines, fastpaths
from bee.agent.context import Context
from bee.agent.loop import AgentResult, _finish, run_agent
from bee.config import load_config


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setattr(bee_paths, "WORKSPACE", tmp_path)
    import bee.memory.md as md
    import bee.monitor.metrics as mt
    monkeypatch.setattr(md, "diary_add", lambda *a, **k: None)
    monkeypatch.setattr(mt, "record", lambda *a, **k: None)
    cfg = load_config()
    cfg.rag.auto_context = False
    cfg.guard.mode = "always"
    c = Context(cfg, workspace=tmp_path)
    c.episodes_on = False
    return c


def _h(name, phrase):
    hit = fastpaths.match(phrase)
    assert hit is not None, f"no fast path for: {phrase!r}"
    assert hit[0].name == name, (phrase, hit[0].name)
    return hit


# ------------------------------------------------------------------ matchers
def test_time_date_identity_help():
    _h("time", "what time is it")
    _h("date", "what's the date")
    _h("identity", "who are you")
    _h("help", "help")


def test_no_match_for_real_tasks():
    assert fastpaths.match("open the config file and refactor the router") is None
    assert fastpaths.match("write a python script that scrapes prices") is None
    assert fastpaths.match("help me with my taxes") is None
    assert fastpaths.match("what time should we meet with the client about the contract?") is None
    assert fastpaths.match("remember the details of the long negotiation we had last quarter") is None


def test_convert_handlers(ctx):
    fp, m = _h("convert", "100 celsius to fahrenheit")
    assert "212" in fp.handle(ctx, m)
    fp, m = _h("convert", "5km to miles")
    assert "3.1" in fp.handle(ctx, m)
    fp, m = _h("convert", "1024 mb to gb")
    assert "1 gb" in fp.handle(ctx, m).lower()
    # cross-dimension must decline (no bogus answer)
    assert fastpaths._convert(ctx, re.match(r"(\d+(?:[.,]\d+)?)\s*([a-z°]+)\s*(?:to|in|=|→)\s*([a-z°]+)", "10 km to kg", re.I)) is None


def test_coin_dice_random(ctx, monkeypatch):
    # pin randomness so the test is deterministic (handlers stay stochastic for real use)
    import random as _random
    monkeypatch.setattr(_random, "choice", lambda seq: seq[0])
    monkeypatch.setattr(_random, "randint", lambda a, b: b)
    fp, m = _h("coin", "flip a coin")
    assert fp.handle(ctx, m).replace("*", "").strip().lower() == "heads."
    fp, m = _h("dice", "roll a die")
    assert fp.handle(ctx, m) == "**6**"
    fp, m = _h("random", "random number between 1 and 10")
    assert fp.handle(ctx, m) == "**10**"
    fp, m = _h("pick", "pick one of pizza, sushi, tacos")
    out = fp.handle(ctx, m)
    assert out == "**pizza** (picked from 3 options)"


def test_note_and_todo(ctx, monkeypatch):
    captured = []
    import bee.memory.md as md
    monkeypatch.setattr(md, "diary_add", lambda s: captured.append(s))
    fp, m = _h("note", "note that the invoice is due friday")
    assert "Noted" in fp.handle(ctx, m)
    assert captured

    fp, m = _h("todo", "todo: ship the beta by friday")
    out = fp.handle(ctx, m)
    assert "t1" in out
    from bee import commands as cmdreg
    assert "ship the beta" in cmdreg.run(ctx, "plan list")


def test_open_app_and_search_return_fastexec(ctx):
    fp, m = _h("open_app", "open chrome")
    fe = fp.handle(ctx, m)
    assert isinstance(fe, fastpaths.FastExec)
    assert fe.tool == "shell" and fe.args["command"] == "start chrome"
    fp, m = _h("search", "google latest rtx driver")
    fe = fp.handle(ctx, m)
    assert fe.tool == "shell" and "google.com/search?q=" in fe.args["command"]


def test_open_file_workspace_only(ctx):
    (ctx.workspace / "report.md").write_text("x", encoding="utf-8")
    fp, m = _h("open_file", "open report.md")
    fe = fp.handle(ctx, m)
    assert isinstance(fe, fastpaths.FastExec) and "report.md" in fe.args["command"]
    # missing file -> decline (falls through to model)
    fp, m = _h("open_file", "open nofile.md")
    assert fp.handle(ctx, m) is None


# ------------------------------------------------------------ end-to-end (no LLM)
class DeadClient:
    def models_list(self):
        return ["stub"]

    def ollama_up(self):
        return True

    def _has_ollama(self):
        return True

    def chat(self, *a, **k):
        raise RuntimeError("fast path must not call the LLM")


def test_fastpath_end_to_end_no_llm(ctx):
    ctx.client = DeadClient()
    res = run_agent(ctx, "what time is it")
    assert res.ok and res.model == "deterministic"
    assert res.route_source == "fastpath"
    assert "It's" in res.output


def test_guard_blocks_fastpath_exec(ctx, monkeypatch):
    import bee.guard as g
    monkeypatch.setattr(g, "check", lambda *a, **k: (False, "deny", "test deny"))
    res = run_agent(ctx, "open chrome")
    assert res.ok
    assert "Guard blocked" in res.output


def test_fastpath_guard_blocks_real_destructive_python(ctx):
    """P1-3: no monkeypatched guard here — the run_code fastpath hands user
    Python to the REAL guard, whose AST risk layer (bee.security.risk) denies
    shutil.rmtree / subprocess / eval payloads. The payload never executes and
    the refusal is the honest blocked text plus a deny guard event."""
    ctx.client = DeadClient()
    for payload in ("import shutil; shutil.rmtree('C:/Windows/System32')",
                    "import subprocess; subprocess.run(['whoami'])",
                    "eval('2+2')"):
        seen: list[dict] = []
        res = run_agent(ctx, f"run python: {payload}", on_event=seen.append)
        assert res.ok and res.route_source == "fastpath", payload
        assert res.tool_calls == 0, payload             # nothing executed
        assert "not allowed" in res.output, payload     # honest blocked text
        assert any(e.get("type") == "guard" and e.get("action") == "deny"
                   for e in seen), payload


class _SchemaRecClient:
    """Records the tool-schema count each route call received (P0-1)."""

    def __init__(self, text):
        self.text = text
        self.seen = []

    def models_list(self):
        return ["stub"]

    def ollama_up(self):
        return True

    def _has_ollama(self):
        return True

    def chat(self, name, messages, tools=None, **kw):
        self.seen.append((name, len(tools) if tools else 0))
        return {"content": self.text}


def test_local_route_gets_the_fitted_schema_subset(ctx, tmp_path, monkeypatch):
    """P0-1: all 30 schemas are ~5.2k est tokens of the 7168 local budget — a
    live turn measured 8434 with NOTHING left to compact, so the tool list alone
    starved the history. The local route must receive the fitted subset."""
    from bee.tools import LOCAL_TOOL_NAMES, tools_litellm
    monkeypatch.setattr(bee_paths, "TRAIN_DIR", tmp_path)
    full, sub = tools_litellm(), tools_litellm(local=True)
    # every listed name must exist in the registry (a typo would silently drop it)
    assert {t["function"]["name"] for t in sub} == set(LOCAL_TOOL_NAMES)
    assert len(sub) < len(full)
    ctx.cfg.cloud.enabled = False          # local serves this one
    client = _SchemaRecClient("The three notes show steady progress on the release.")
    ctx.client = client
    res = run_agent(ctx, "summarize the three project notes into one short paragraph")
    assert res.ok, (res.output, res.error)
    assert client.seen, "the model loop never ran"
    name, count = client.seen[-1]
    assert name == "local"
    assert count == len(sub)


def test_cloud_route_keeps_the_full_schema_set(ctx, tmp_path, monkeypatch):
    """P0-1: the diet is local-only — cloud calls still see every schema."""
    from bee.agent import providers
    from bee.tools import tools_litellm
    monkeypatch.setattr(bee_paths, "TRAIN_DIR", tmp_path)
    monkeypatch.setattr(providers, "cloud_available", lambda cfg: (True, "test"))
    ctx.cfg.cloud.enabled = True
    client = _SchemaRecClient("The three notes show steady progress on the release.")
    ctx.client = client
    res = run_agent(ctx, "summarize the three project notes into one short paragraph")
    assert res.ok, (res.output, res.error)
    name, count = client.seen[-1]
    assert name == "cloud"
    assert count == len(tools_litellm(local=False))


def test_explicit_model_hint_beats_fastpath(ctx):
    # 'local: what time is it' is explicit routing — the user asked for the model
    r = fastpaths.match("what time is it")
    assert r is not None  # the phrase itself still matches; gating happens in loop


# ------------------------------------------------------------------ teach-back
def test_golden_written_on_escalated_ok(ctx, tmp_path, monkeypatch):
    monkeypatch.setattr(bee_paths, "TRAIN_DIR", tmp_path)
    res = AgentResult(output="the cloud answer", model="gemini-3-flash-preview",
                      ok=True, escalated=True)
    _finish(ctx, "hard task", None, res, time.time(), lambda e: None, False)
    f = tmp_path / "golden" / "cloud_golden.jsonl"
    assert f.exists()
    row = json.loads(f.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert row["task"] == "hard task" and "hard task" in json.dumps(row)


def test_golden_not_written_for_local_ok(ctx, tmp_path, monkeypatch):
    monkeypatch.setattr(bee_paths, "TRAIN_DIR", tmp_path)
    res = AgentResult(output="local answer", model="local", ok=True, escalated=False)
    _finish(ctx, "easy task", None, res, time.time(), lambda e: None, False)
    assert not (tmp_path / "golden").exists() or not (tmp_path / "golden" / "cloud_golden.jsonl").exists()


def test_golden_written_for_cloud_first_ok(ctx, tmp_path, monkeypatch):
    """Hybrid speed tier: the CLOUD model answered with escalated=False (the
    flag is cleared by the cloud-first override). Before 2026-10-17 the trigger
    checked `escalated` alone, so these cloud-served successes (556 in the
    live ledger) never reached the local model's training corpus."""
    monkeypatch.setattr(bee_paths, "TRAIN_DIR", tmp_path)
    res = AgentResult(output="the cloud answer", model="cloud", ok=True, escalated=False)
    _finish(ctx, "routine ask", None, res, time.time(), lambda e: None, False)
    f = tmp_path / "golden" / "cloud_golden.jsonl"
    assert f.exists()
    assert json.loads(f.read_text(encoding="utf-8").strip())["task"] == "routine ask"


def test_golden_records_raw_wording_not_context_block(ctx, tmp_path, monkeypatch):
    """Goldens carry the user's own words (kernel route_text), not the
    context-augmented prompt the model saw."""
    monkeypatch.setattr(bee_paths, "TRAIN_DIR", tmp_path)
    res = AgentResult(output="the cloud answer", model="cloud", ok=True, escalated=False)
    _finish(ctx, "SESSION CONTEXT: recent tasks: alpha, beta\n\nwhat is the plan?",
            None, res, time.time(), lambda e: None, False, raw="what is the plan?")
    f = tmp_path / "golden" / "cloud_golden.jsonl"
    assert json.loads(f.read_text(encoding="utf-8").strip())["task"] == "what is the plan?"


def test_golden_not_written_on_verify_fail(ctx, tmp_path, monkeypatch):
    """A cloud answer the verifier FAILED must never become training material,
    even though it succeeded at the tool level."""
    monkeypatch.setattr(bee_paths, "TRAIN_DIR", tmp_path)
    res = AgentResult(output="confident but wrong answer", model="gemini-3-flash-preview",
                      ok=True, escalated=True, verify="fail")
    _finish(ctx, "tricky task", None, res, time.time(), lambda e: None, False)
    assert not (tmp_path / "golden").exists() or not (tmp_path / "golden" / "cloud_golden.jsonl").exists()


def test_golden_written_when_unverified(ctx, tmp_path, monkeypatch):
    """verify=None is absence of a check, not evidence of wrongness — record."""
    monkeypatch.setattr(bee_paths, "TRAIN_DIR", tmp_path)
    res = AgentResult(output="the cloud answer", model="gemini-3-flash-preview",
                      ok=True, escalated=True, verify=None)
    _finish(ctx, "hard task", None, res, time.time(), lambda e: None, False)
    assert (tmp_path / "golden" / "cloud_golden.jsonl").exists()


def test_teach_back_distills_skill(ctx, monkeypatch):
    monkeypatch.setattr(bee_paths, "TRAIN_DIR", ctx.workspace)
    monkeypatch.setattr(bee_paths, "SKILLS_DIR", ctx.workspace / "skills")
    d = ctx.workspace / "golden"
    d.mkdir(parents=True, exist_ok=True)
    body = "```python\ndef retry(fn, tries=3):\n    for i in range(tries):\n        try:\n            return fn()\n        except Exception:\n            if i == tries - 1:\n                raise\n```\nThat's a simple retry decorator with backoff you can extend."
    (d / "cloud_golden.jsonl").write_text(
        json.dumps({"task": "write a retry decorator", "response": body,
                    "model": "gemini-3-flash-preview", "ts": "2026-10-04T22:00:00"}) + "\n",
        encoding="utf-8")
    out = scheduler.maybe_teach_back(ctx)
    assert out["new"] == 1, out
    assert out["skills"], out
    skill_md = ctx.workspace / "skills" / out["skills"][0] / "SKILL.md"
    assert skill_md.exists() and "retry decorator" in skill_md.read_text(encoding="utf-8")
    # second run: already digested -> no new skills
    out2 = scheduler.maybe_teach_back(ctx)
    assert out2["new"] == 0 and out2["skills"] == []


# ------------------------------------------------------------------ engines
def test_engines_override_and_persist(tmp_path, monkeypatch):
    monkeypatch.setattr(engines, "settings_file", lambda: tmp_path / "settings.json")
    assert engines.load_engine() is None
    assert engines.override_for(None) is None
    assert engines.override_for("hybrid") is None
    assert engines.override_for("local") == "local"
    assert engines.override_for("api-cloud") == "cloud"
    assert engines.override_for("ollama-cloud") == "glm-5.2:cloud"
    engines.save_engine("api-cloud")
    assert engines.load_engine() == "api-cloud"


def test_ask_engine_non_interactive_defaults_hybrid(monkeypatch, tmp_path):
    # pytest captures stdin (isatty() is False) -> must default to hybrid, no prompt.
    # Used to point at /tmp/bee_test_engine.json, which on Windows lands outside the
    # per-test tmp dir and is shared between runs (A41c).
    monkeypatch.setattr(engines, "settings_file", lambda: tmp_path / "settings.json")
    assert engines.ask_engine() == "hybrid"
    assert engines.load_engine() == "hybrid", "the default was never persisted"


# ------------------------------------------------------- spoken reminders (A24)
# "remind me to X in 20 min" must be answered by the deterministic tier: the
# same durable job /remind creates, no model call, and no provider required at
# the moment it fires.
def test_reminder_phrases_route_to_the_instant_tier():
    _h("remind", "remind me to stretch in 20 min")
    _h("remind", "remind me to call the bank tomorrow 9am")
    _h("remind", "don't forget to submit the expense friday 4pm")
    _h("remind", "set a reminder to pay rent on 12 Oct")
    _h("remind_list", "what are my reminders")
    _h("remind_list", "do I have any reminders?")
    _h("remind_cancel_last", "cancel my last reminder")
    _h("remind_cancel_all", "cancel all my reminders")


def test_reminder_without_a_time_declines_instead_of_inventing_one(ctx):
    """'Remind me what my passport number is' is a question, not a reminder. The
    fast path must fall through to the model rather than schedule a guess."""
    for phrase in ("remind me what my passport number is",
                   "remind me later about that"):
        hit = fastpaths.match(phrase)
        assert hit is not None, phrase
        assert hit[0].handle(ctx, hit[1]) is None, f"{phrase!r} must decline"


def _attach_worker(ctx, tmp_path, clock_at):
    import pathlib
    import sys
    from datetime import timezone
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from test_automation import FakeClock
    from bee.automation.store import JobStore
    from bee.automation.worker import JobWorker
    w = JobWorker(ctx, None, JobStore(tmp_path / "automation"),
                  clock=FakeClock(clock_at))
    ctx.automation_worker = w
    return w


def test_spoken_reminder_creates_a_durable_job_end_to_end(ctx, tmp_path):
    from datetime import datetime, timedelta, timezone
    tz = timezone(timedelta(hours=5, minutes=30))
    w = _attach_worker(ctx, tmp_path, datetime(2026, 10, 8, 19, 5, tzinfo=tz))

    res = run_agent(ctx, "remind me to stretch in 20 minutes")
    assert res.ok and res.model == "deterministic", (res.model, res.output)
    assert res.route_source == "fastpath", res.route_source
    assert "Reminder set" in res.output and "stretch" in res.output
    jobs = [j for j in w.jobs() if j.owner == "reminder"]
    assert len(jobs) == 1
    # 19:25 IST, stored canonically in UTC — measured from the worker's clock
    assert jobs[0].next_run == "2026-10-08T13:55:00+00:00", jobs[0].next_run
    assert jobs[0].action["type"] == "notify" and jobs[0].action["critical"] is True


def test_spoken_reminder_list_and_cancel_share_the_store(ctx, tmp_path):
    from datetime import datetime, timedelta, timezone
    tz = timezone(timedelta(hours=5, minutes=30))
    w = _attach_worker(ctx, tmp_path, datetime(2026, 10, 8, 9, 0, tzinfo=tz))
    run_agent(ctx, "remind me to water the plants at 18:00")
    run_agent(ctx, "remind me to stretch in 45 minutes")

    listing = run_agent(ctx, "what are my reminders")
    assert listing.ok and "when (local)" in listing.output
    assert len([j for j in w.jobs() if j.owner == "reminder"]) == 2

    gone = run_agent(ctx, "cancel all my reminders")
    assert gone.ok and "Cancelled" in gone.output
    assert not [j for j in w.jobs()
                if j.owner == "reminder" and j.state == "pending"]


def test_reminder_fastpath_and_slash_command_agree(ctx, tmp_path):
    """One implementation: the same words through either surface produce the same
    instant, so /remind list can show (and cancel) a spoken reminder."""
    from datetime import datetime, timedelta, timezone
    from bee import commands as reg
    tz = timezone(timedelta(hours=5, minutes=30))
    w = _attach_worker(ctx, tmp_path, datetime(2026, 10, 8, 19, 5, tzinfo=tz))
    spoken = run_agent(ctx, "remind me to call the bank tomorrow 9am")
    typed = reg.run(ctx, "/remind call the bank tomorrow 9am")
    assert spoken.ok and "Reminder set" in typed
    rows = [j for j in w.jobs() if j.owner == "reminder"]
    assert len(rows) == 2
    assert rows[0].next_run == rows[1].next_run == "2026-10-09T03:30:00+00:00"
    # and the spoken listing sees both
    listing = reg.run(ctx, "/remind list")
    assert "call the bank" in listing


# ------------------------------------------------ folder listing (A31)
def test_folder_listing_phrasings_route_to_the_instant_tier():
    for p in ("list the files in the workspace",
              "what files are in the workspace",
              "show me the folders in src",
              "list the top-level entries of the workspace",
              "how many directories are in the project"):
        _h("files_list", p)


def test_folder_listing_declines_when_the_question_is_not_about_folders(ctx):
    """'What is in the oven' must not be answered with a directory listing."""
    for phrase in ("what is in the oven", "what is in the box"):
        hit = fastpaths.match(phrase)
        assert hit is not None and hit[0].name == "files_list", phrase
        assert hit[0].handle(ctx, hit[1]) is None, f"{phrase!r} must decline"


def test_folder_listing_answers_with_real_entries_and_counts(ctx, tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "config.yaml").write_text("a: 1\n", encoding="utf-8")
    res = run_agent(ctx, "List the top-level entries of the workspace. "
                         "How many of them are directories? Give the count.")
    assert res.ok and res.model == "deterministic", (res.model, res.output)
    assert res.route_source == "fastpath"
    assert res.tool_calls == 1, "the listing really used the tool"
    assert "config.yaml" in res.output
    assert "1 directory" in res.output, res.output
    assert "1 file" in res.output, res.output


def test_folder_listing_reports_a_bad_path_honestly(ctx):
    hit = fastpaths.match("show me the files in no_such_dir_here")
    out = hit[0].handle(ctx, hit[1])
    assert out.tool == "file_list" and out.args["path"] == "no_such_dir_here"
    assert "Could not list it" in out.reply({"error": "not found: no_such_dir_here"})


# ------------------------------------------------ machine specs (A32)
def test_spec_phrasings_route_to_the_instant_tier():
    for p in ("what are my specs", "what's my gpu", "what is my hardware",
              "what are the machine specs", "which cpu is in this laptop",
              "what gpu do i have", "what is the ram", "what are my computer specs"):
        _h("specs", p)


def test_spec_fastpath_declines_questions_that_are_not_about_this_box():
    """"What hardware do I need to run llama" is a purchase question; 'what is
    the spec of the RTX 3050' is a product question. Answering either with this
    laptop's inventory would be a non-answer."""
    for p in ("what hardware do i need to run llama",
              "what is the spec of the rtx 3050",
              "what is memory in python",
              "what is a gpu",
              "how much ram is free"):
        hit = fastpaths.match(p)
        assert (hit is None or hit[0].name != "specs"), f"{p!r} -> {hit[0].name if hit else None}"


def test_spec_fastpath_answers_from_the_inventory(ctx, monkeypatch):
    from bee.tools import systemctl
    monkeypatch.setattr(systemctl, "_HW_CACHE", {
        "cpu": "12th Gen Intel(R) Core(TM) i5-12450H",
        "gpus": [{"name": "NVIDIA GeForce RTX 3050 Laptop GPU", "vram_gb": 4}],
        "ram_gb": 16, "os": "Microsoft Windows 11 Home", "machine": "HP Victus"})
    res = run_agent(ctx, "what are my specs")
    assert res.route_source == "fastpath", res.route_source
    assert "RTX 3050 Laptop GPU (4 GB VRAM)" in res.output, res.output
    assert "RAM: 16 GB" in res.output, res.output
    monkeypatch.setattr(systemctl, "_HW_CACHE", None)


def test_spec_fastpath_falls_through_when_inventory_is_unavailable(ctx, monkeypatch):
    """Non-Windows or a blocked CIM query must not produce a fake spec sheet."""
    from bee.tools import systemctl
    monkeypatch.setattr(systemctl, "_HW_CACHE", None)
    monkeypatch.setattr(systemctl, "_ps", lambda expr: "")
    hit = fastpaths.match("what are my specs")
    assert hit is not None and hit[0].handle(ctx, hit[1]) is None


# ------------------------------------------------ pasted code (A34)
DSA_SORT = ("Run python: from bee.dsa import SORTS; data=list(range(50,0,-1)); "
            "print([n for n,f in SORTS.items() if f(data)==sorted(data)]) — list "
            "which sorts are correct on reversed input.")


def test_pasted_code_routes_to_the_instant_tier():
    _h("run_code", "run python: print(2+2)")
    _h("run_code", "Run the following Python snippet: import math; print(math.gcd(84, 147))")
    _h("run_code", DSA_SORT)                       # 190 chars: needs the per-path ceiling
    for p in ("run python scripts every morning",
              "run the tests",
              "execute my plan for friday"):
        hit = fastpaths.match(p)
        assert hit is None or hit[0].name != "run_code", p


def test_pasted_code_runs_and_reports_real_output(ctx, tmp_path):
    """The eval asked for exactly this twice and the model answered by WRITING code
    (with a typo in the module name) or by burning 15 tool calls on variants."""
    res = run_agent(ctx, "run python: print(sum(range(10)))")
    assert res.route_source == "fastpath", res.route_source
    assert res.output.strip() == "45", res.output
    assert res.tool_calls == 1, res.tool_calls


def test_pasted_code_keeps_the_trailing_prose_out_of_the_snippet():
    """The eval's own sentence: 'Run python: <snippet> — list which sorts are
    correct on reversed input.' The instruction after the dash is prose; leaving it
    inside the snippet produced a SyntaxError on the first live run."""
    hit = fastpaths.match(DSA_SORT)
    assert hit is not None and hit[0].name == "run_code"
    code = hit[0].handle(None, hit[1]).args["code"]
    assert "list which sorts" not in code and "—" not in code, code
    assert code.startswith("from bee.dsa import SORTS"), code


def test_pasted_code_with_a_trailing_request_still_runs(ctx):
    res = run_agent(ctx, "run python: print('sorted ok') — and tell me what it says")
    assert res.output.strip() == "sorted ok", res.output


def test_a_failing_snippet_is_reported_as_failing(ctx):
    res = run_agent(ctx, "run python: raise ValueError('boom')")
    out = (res.output or "").lower()
    assert "exit" in out or "valueerror" in out, res.output
    assert "45" not in res.output
    assert res.ok is True                      # the run itself succeeded: it failed honestly


def test_empty_snippet_is_not_a_command(ctx):
    assert fastpaths.match("run python:") is None
    assert fastpaths.match("run the following python code:") is None


def test_long_prose_still_does_not_match_a_spoken_command_path():
    """The 120-char ceiling was global before; the per-path `max_len` must not
    quietly open every path to paragraphs."""
    long_prose = ("I have been thinking about how we should structure the quarterly review "
                  "meeting, and I would like your advice on the agenda, the participants, "
                  "and the follow-up actions we should track.")
    assert len(long_prose) > 120
    assert fastpaths.match(long_prose) is None


def test_docs_do_not_stale():
    """README and STATUS both still said '39 handlers' after the catalog grew to
    45 (reminders, folder listings, machine specs). Nothing in the repo read those
    numbers, so the drift was invisible — the same docs-claim-a-mechanism class as
    A22/A25. Historical entries in TECHNICAL_DEBT.md are left alone on purpose:
    they record the count as of that fix."""
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    n = len(fastpaths.FASTPATHS)
    claims = {
        "README.md": r"catalog of (\d+) pure-Python handlers|"
                     r"catalog \((\d+) pure-Python handlers\)",
        "docs/STATUS.md": r"Fast-path catalog \((\d+) handlers",
    }
    for rel, pattern in claims.items():
        txt = (root / rel).read_text(encoding="utf-8")
        found = [int(g) for m in re.finditer(pattern, txt) for g in m.groups() if g]
        assert found, f"{rel}: no fast-path count found — the wording changed"
        for got in found:
            assert got == n, f"{rel} claims {got} handlers, the catalog has {n}"
