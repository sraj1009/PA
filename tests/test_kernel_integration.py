"""Kernel integration tests (Phase 2) — full task lifecycle through the REAL
run_agent loop, with a scripted LLM stand-in (no model, no network, no cloud).

Scenarios (required):
 1. simple local request
 2. tool call
 3. multi-step task
 4. permission-required task (granted)
 5. denied task
 6. failed task (provider failure -> bounded retry -> FAILED)
 7. verification failure (claimed success, effect missing -> retry -> pass)
 8. cancellation (pre-set + mid-run)
 9. follow-up message referencing the prior task

Run:  python -m pytest tests/test_kernel_integration.py -q
"""
from __future__ import annotations

import json
import threading
import time

import pytest

from bee.agent.client import LLMError
from bee.agent.context import Context
from bee.config import load_config
from bee.kernel import AgentKernel, AgentEventKind, TaskState


# ----------------------------------------------------------------- stand-in
class ScriptedClient:
    """chat() pops scripted items: str -> final answer; dict -> raw LLM out;
    Exception -> raise. Records every call (name, messages, kwargs)."""

    def __init__(self, script: list, delay: float = 0.0):
        self.script = list(script)
        self.calls: list[tuple] = []
        self.delay = delay

    def chat(self, name, messages, tools=None, **kw):
        self.calls.append((name, [dict(m) for m in messages], kw))
        if self.delay:
            time.sleep(self.delay)
        if not self.script:
            return {"content": "(scripted: no reply left)", "usage": {}}
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, str):
            return {"content": item, "usage": {}}
        return item

    def ollama_up(self):
        return True

    def _has_ollama(self):
        return True

    def models_list(self):
        return ["bee4b"]


def tc(cid: str, name: str, args: dict) -> dict:
    return {"tool_calls": [{"id": cid, "name": name, "arguments": args}]}


def make_kernel(tmp_path, script, approver=None, delay=0.0):
    cfg = load_config()
    cfg.cloud.enabled = False           # no real provider calls, ever
    cfg.workspace = tmp_path
    client = ScriptedClient(script, delay=delay)
    ctx = Context(cfg, workspace=tmp_path, client=client,
                  guard_on=True, guard_mode="unattended",
                  episodes_on=False, rag_on=False,
                  cancel_event=threading.Event())
    k = AgentKernel(ctx, approver=approver if approver is not None else (lambda t, a, r: False),
                    sessions_dir=tmp_path / "sessions",
                    receipts_path=tmp_path / "receipts.jsonl")
    ctx.kernel = k
    return k, client, ctx


def _events(k, kind):
    return [e for e in k.events.log if e.kind == kind]


def test_f5_denied_guard_ask_does_not_strand_task(tmp_path):
    """Acceptance audit (guard_blocked eval, REAL DEFECT): a guard 'ask'
    that the approver DENIES must return the task to EXECUTING. Before the
    fix the task stayed in WAITING_FOR_PERMISSION, so when the model
    finished its refusal-explanation the kernel's move to VERIFYING raised
    InvalidTransitionError and the whole task crashed."""
    k, client, _ctx = make_kernel(tmp_path, [
        tc("c1", "shell", {"command": "git reset --hard HEAD~1"}),
        "That command is blocked by policy; I did not run it.",
    ], approver=lambda t, a, r: False)      # unattended: everything asks->deny
    (tmp_path / "keep.txt").write_text("keep me")
    r = k.run("Run 'git reset --hard HEAD~1' in the workspace and report what happened.",
              session_id="f5")
    # the task completed its lifecycle instead of crashing mid-transition
    assert r is not None
    assert AgentEventKind.PERMISSION_DENIED in [e.kind for e in k.events.log]
    assert r.task.state in (TaskState.COMPLETED, TaskState.FAILED), r.task.state.value
    assert (tmp_path / "keep.txt").exists()


# ---------------------------------------------------------------- scenarios
def test_1_simple_local_request(tmp_path):
    k, client, _ = make_kernel(tmp_path, ["A router forwards packets between networks using routing tables."])
    r = k.run("Explain what a router does in networking.", session_id="i1")
    assert r.ok is True and r.task.state == TaskState.COMPLETED
    assert "router" in r.output.lower()
    assert len(client.calls) >= 1
    assert [e.kind for e in k.events.log if e.kind == AgentEventKind.TASK_COMPLETED]
    # receipts: the agent-level run receipt exists and is redaction-safe JSON
    rows = [json.loads(l) for l in (tmp_path / "receipts.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(row["tool"] == "agent" and row["action"] == "run" for row in rows)
    assert r.verification.verdict in ("pass", "unverified")


def test_2_tool_call(tmp_path):
    # factorial(6) deliberately: a single function call with NO operator, which
    # the deterministic tier declines (it requires an operator), so this still
    # exercises the real LLM -> tool -> verify path.
    k, client, _ = make_kernel(tmp_path, [
        tc("c1", "calculator", {"expression": "factorial(6)"}),
        "The result is 720.",
    ])
    r = k.run("Use the calculator to compute factorial(6).", session_id="i2")
    assert r.ok and r.task.state == TaskState.COMPLETED
    assert "720" in r.output
    tools = [e.data.get("tool") for e in _events(k, AgentEventKind.TOOL_COMPLETED)]
    assert "calculator" in tools
    assert len(_events(k, AgentEventKind.TOOL_STARTED)) == 1
    rows = [json.loads(l) for l in (tmp_path / "receipts.jsonl").read_text(encoding="utf-8").splitlines()]
    calc = [row for row in rows if row["tool"] == "calculator"]
    assert calc and calc[0]["verification"] == "pass"   # effect checked, not assumed
    assert r.task.observations[0].ok


def test_3_multi_step_task(tmp_path):
    k, client, _ = make_kernel(tmp_path, [
        tc("c1", "file_write", {"path": "reports/summary.txt", "content": "Q3: 1.2M"}),
        tc("c2", "file_read", {"path": "reports/summary.txt"}),
        "Saved and read back the Q3 summary.",
    ])
    r = k.run("Write the Q3 summary report to reports/summary.txt and read it back to confirm.",
              session_id="i3")
    assert r.ok and r.task.state == TaskState.COMPLETED
    assert (tmp_path / "reports" / "summary.txt").read_text(encoding="utf-8") == "Q3: 1.2M"
    tools = [e.data.get("tool") for e in _events(k, AgentEventKind.TOOL_COMPLETED)]
    assert tools.count("file_write") == 1 and tools.count("file_read") == 1
    assert r.verification.verdict == "pass"
    assert len(r.task.observations) == 2


def test_4_permission_required_granted(tmp_path):
    (tmp_path / "a.txt").write_text("original")
    k, client, _ = make_kernel(tmp_path, [
        tc("c1", "code_run", {"code": "import os\nos.rename('a.txt', 'b.txt')"}),
        "Renamed a.txt to b.txt.",
    ], approver=lambda tool, args, reason: True)
    r = k.run("Rename a.txt to b.txt in the workspace.", session_id="i4")
    kinds = [e.kind for e in k.events.log]
    assert AgentEventKind.PERMISSION_REQUESTED in kinds
    assert AgentEventKind.PERMISSION_GRANTED in kinds
    assert (tmp_path / "b.txt").exists() and not (tmp_path / "a.txt").exists()
    assert r.task.state == TaskState.COMPLETED
    rows = [json.loads(l) for l in (tmp_path / "receipts.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(row["action"] == "permission" and row["permission"] == "granted" for row in rows)
    # WAITING_FOR_PERMISSION was a real state (kernel observed by the approver)
    assert r.task.state == TaskState.COMPLETED  # terminal; path included the wait


def test_5_denied_task(tmp_path):
    k, client, _ = make_kernel(tmp_path, [
        tc("c1", "shell", {"command": "rm -rf /tmp/bee-denied-probe"}),
        "I cannot do that — the guard blocked it.",
    ])
    r = k.run("Delete everything inside /tmp/bee-denied-probe recursively.", session_id="i5")
    kinds = [e.kind for e in k.events.log]
    assert AgentEventKind.PERMISSION_DENIED in kinds
    blocked = [o for o in r.task.observations if o.blocked]
    assert blocked, "the denied tool call must be recorded as blocked"
    import tempfile
    from pathlib import Path as _P
    assert not (_P(tempfile.gettempdir()) / "bee-denied-probe").exists(), "denied command must not run"
    assert r.task.state == TaskState.COMPLETED          # agent explained; nothing ran
    assert r.verification.verdict == "unverified"        # and success is NOT claimed
    rows = [json.loads(l) for l in (tmp_path / "receipts.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(row["tool"] == "shell" and "blocked" in row["result"].lower() for row in rows)


def test_6_failed_task_provider_retry(tmp_path):
    k, client, _ = make_kernel(tmp_path, [
        LLMError("connection refused", kind="connect"),
        LLMError("connection refused", kind="connect"),
    ])
    r = k.run("Explain the TCP handshake in detail.", session_id="i6")
    assert r.ok is False and r.task.state == TaskState.FAILED
    assert r.task.failure_kind == "provider"
    assert r.task.retry_count == 1 and r.retried is True
    assert len(client.calls) == 2, "exactly one retry, then stop"
    kinds = [e.kind for e in k.events.log]
    assert AgentEventKind.TASK_FAILED in kinds
    rows = [json.loads(l) for l in (tmp_path / "receipts.jsonl").read_text(encoding="utf-8").splitlines()]
    run_rows = [row for row in rows if row["tool"] == "agent"]
    assert run_rows[-1]["retry_count"] == 1


def test_7_verification_failure_then_retry(tmp_path):
    k, client, _ = make_kernel(tmp_path, [
        # attempt 1: creates the WRONG folder, claims success
        tc("c1", "shell", {"command": "mkdir wrongdir"}),
        "Done — folder created.",
        # attempt 2 (kernel retry with correction note): does it right
        tc("c2", "shell", {"command": "mkdir invoices"}),
        "Done — invoices folder created.",
    ])
    r = k.run("Create a folder called invoices.", session_id="i7")
    assert (tmp_path / "invoices").is_dir(), "the intended effect must exist afterwards"
    assert r.task.state == TaskState.COMPLETED
    assert r.retried is True and r.task.retry_count == 1
    assert r.verification.verdict == "pass"
    # the retry note was actually injected into the second run
    retried = [m.get("content", "") for c in client.calls for m in c[1]
               if isinstance(m.get("content"), str) and "FAILED VERIFICATION" in m["content"]]
    assert retried, "the correction note was not injected into the retry"
    kinds = [e.kind for e in k.events.log]
    assert kinds.count(AgentEventKind.VERIFICATION_COMPLETED) == 2


def test_8_cancellation_scoped_not_pre_set(tmp_path):
    """N4 contract (supersedes the old pre-set test): a cancel event left
    SET by a previously-cancelled task must NOT cancel the NEXT task — the
    kernel clears it at task start. Cancellation is task-scoped and owned by
    the kernel, not by whichever entry point happens to clear the event.
    (Mid-run cancellation — the real cancel path — is test_8b.)"""
    k, client, ctx = make_kernel(tmp_path, ["all good"])
    ctx.cancel_event.set()   # stale cancel from an earlier task
    r = k.run("Do a quick thing.", session_id="i8a")
    assert r.cancelled is False, "stale cancel event must not poison the new task"
    assert not ctx.cancel_event.is_set(), "kernel must clear the event at task start"
    assert client.calls, "the new task must run normally"


def test_8b_cancellation_mid_run(tmp_path):
    k, client, ctx = make_kernel(
        tmp_path, [tc("c1", "calculator", {"expression": "1"}), "late answer"], delay=0.4)
    box = {}

    def go():
        box["r"] = k.run("compute something slowly", session_id="i8b")

    th = threading.Thread(target=go)
    th.start()
    time.sleep(0.2)          # the first LLM call is in flight (0.4s)
    k.cancel()
    th.join(timeout=20)
    assert th.ident is None or not th.is_alive()
    r = box["r"]
    assert r.cancelled is True and r.task.state == TaskState.CANCELLED


def test_9_follow_up_resolves_against_active_task(tmp_path):
    k, client, _ = make_kernel(tmp_path, [
        "Invoice draft ready.",
        "Updated — the invoice is set for 10 AM.",
    ])
    r1 = k.run("Draft the invoice for Apex Carnage.", session_id="i9")
    assert r1.task.state == TaskState.COMPLETED
    r2 = k.run("Actually make it 10 AM.", session_id="i9")
    # the second LLM call must see the ORIGINAL task + the follow-up merged
    last_user = client.calls[-1][1][-1]["content"]
    assert "Apex Carnage" in last_user, "follow-up lost the referenced entity"
    assert "10 AM" in last_user
    assert r2.task.state == TaskState.COMPLETED
    # and it resolved against the active task, not as an unrelated prompt
    assert "follow-up" in r2.task.text
    # session persisted with the active task for future turns
    s = k.get_session("i9")
    assert s.active_task_text.startswith("Draft the invoice for Apex Carnage.")
    assert (tmp_path / "sessions" / "i9.json").exists()
    # a genuinely unrelated message starts a NEW task
    k.ctx.client.script = ["Unrelated answer."]
    r3 = k.run("Tell me about the history of glass.", session_id="i9")
    assert "follow-up" not in r3.task.text


def test_10_repl_stop_word_semantics(tmp_path):
    """'stop' with no running task reports the last task's state (unit-level)."""
    k, client, _ = make_kernel(tmp_path, ["done."])
    k.run("Do the thing.", session_id="i10")
    before = len(client.calls)
    r = k.run("stop.", session_id="i10")
    assert r.cancelled is True and len(client.calls) == before


def test_11_events_full_sequence(tmp_path):
    k, client, _ = make_kernel(tmp_path, [
        tc("c1", "calculator", {"expression": "factorial(6)"}),
        "It is 720.",
    ])
    # factorial(6) has no operator, so the deterministic tier declines it and the
    # tool path runs. (Prose-wrapped arithmetic like "compute 6 times 7" is now
    # answered by the det tier — see test_prose_wrapped_math_is_answered_... .)
    k.run("Use the calculator to compute factorial(6).", session_id="i11")
    kinds = [e.kind for e in k.events.log]
    seq = [k for k in kinds if k in {AgentEventKind.USER_MESSAGE, AgentEventKind.TASK_CREATED,
                                     AgentEventKind.PLAN_CREATED, AgentEventKind.TOOL_STARTED,
                                     AgentEventKind.TOOL_COMPLETED,
                                     AgentEventKind.VERIFICATION_STARTED,
                                     AgentEventKind.VERIFICATION_COMPLETED,
                                     AgentEventKind.MEMORY_WRITTEN,
                                     AgentEventKind.TASK_COMPLETED}]
    for expected in (AgentEventKind.USER_MESSAGE, AgentEventKind.TASK_CREATED,
                     AgentEventKind.PLAN_CREATED, AgentEventKind.TOOL_STARTED,
                     AgentEventKind.TOOL_COMPLETED, AgentEventKind.VERIFICATION_STARTED,
                     AgentEventKind.VERIFICATION_COMPLETED, AgentEventKind.MEMORY_WRITTEN,
                     AgentEventKind.TASK_COMPLETED):
        assert expected in seq, f"missing event {expected}"
    # order sanity: plan before tool, verification before completion
    assert seq.index(AgentEventKind.PLAN_CREATED) < seq.index(AgentEventKind.TOOL_STARTED)
    assert seq.index(AgentEventKind.VERIFICATION_COMPLETED) < seq.index(AgentEventKind.TASK_COMPLETED)


# ---------------- instant tiers must see the raw utterance ------------------
# The kernel prepends the session context block to the text it sends the MODEL.
# That augmented string used to be what routing and the fast paths judged, so
# any bare follow-up in an ongoing conversation lost its 0 ms handler.

def test_bare_math_stays_deterministic_mid_session(tmp_path):
    k, client, _ctx = make_kernel(tmp_path, ["I can plan, draft, summarize and run code."])
    k.run("Summarize your capabilities in one line.", session_id="s1")
    calls_before = len(client.calls)
    r = k.run("1234 + 5678", session_id="s1")
    assert r.model == "deterministic", f"a model answered the math: {r.model}"
    assert "6912" in r.output
    assert len(client.calls) == calls_before, \
        "an LLM round-trip was spent on a question the det tier answers in 0 ms"


def test_fastpath_still_matches_mid_session(tmp_path):
    k, client, _ctx = make_kernel(tmp_path, ["earlier turn"])
    k.run("Remind me to file the taxes tomorrow.", session_id="s2")
    calls_before = len(client.calls)
    r = k.run("what time is it", session_id="s2")
    assert len(client.calls) == calls_before, "the fast path was bypassed by session context"
    assert r.output and r.model in ("deterministic", "fastpath") or "fast" in str(r.model)


def test_cloud_prefix_override_still_wins_over_fastpath_mid_session(tmp_path):
    """Explicit intent must survive the same refactor: route_text carries the
    'cloud:' form and the explicit tier beats the fast paths."""
    k, client, _ctx = make_kernel(tmp_path, ["[fake]", "[fake]", "[fake]", "[fake]"])
    r = k.run("cloud: what time is it", session_id="s3")
    assert r.model != "deterministic", "explicit engine choice must not be pre-empted"


def test_followup_classifier_separates_commands_from_nudges():
    """The merge rule is '≤4 words looks like a follow-up' — which also caught
    complete requests. Nudges must still merge; commands must not."""
    from bee.kernel.session import AgentSession
    s = AgentSession(id="cls")
    s.active_task_text = "Remind me to file the taxes"
    for nudge in ["Tomorrow.", "At 6pm instead", "actually make it Friday", "that one"]:
        assert s.resolve_followup(nudge)[0] == "continue", nudge
    for cmd in ["1234 + 5678", "25*40/100", "5 plus 5", "what time is it",
                "open chrome", "hi"]:
        d, txt = s.resolve_followup(cmd)
        assert d == "new" and txt == cmd, f"{cmd!r} merged as {d}: {txt!r}"


# ------------------------------------------- narrated calls & meta-rambles (A27)
RAMBLE = ("It seems like there might have been an error or misunderstanding as no "
          "function calls were provided for execution based on the initial request. "
          "The available functions are: system_health, file_read, shell.")
NARRATION = ("To execute the specified Git command, I will use a computer_command "
             "function call to run `git reset --hard HEAD~1` in the workspace.")


def test_narrated_tool_call_is_nudged_not_shipped(tmp_path):
    """Seven eval tasks ended as a sentence ABOUT a call ("I will use a
    computer_command function call…"). That is neither an action nor an answer,
    so the loop must send it back once instead of returning it to the user."""
    k, client, ctx = make_kernel(tmp_path, [NARRATION, "Nothing ran; here is why."])
    res = k.run("run git reset --hard HEAD~1 and tell me what happened")
    second_call_msgs = client.calls[1][1]
    assert any("described an action instead of performing it" in str(m.get("content"))
               for m in second_call_msgs), second_call_msgs[-1]
    assert res.output != NARRATION
    assert "function call" not in res.output.lower()


def test_meta_ramble_never_becomes_the_answer(tmp_path, monkeypatch):
    """'no function calls were provided / the available functions are…' is the
    model answering its own system prompt. The final pass runs with tools
    disabled and the request restated."""
    _no_fastpath(monkeypatch)
    k, client, ctx = make_kernel(tmp_path,
                                    [RAMBLE, "The workspace has 12 top-level entries."])
    res = k.run("List the top-level entries of the workspace. How many are directories?")
    assert "12 top-level entries" in res.output, res.output
    last = client.calls[-1]
    assert last[2].get("tools") is None, "final pass must not offer tools again"
    prompt = " ".join(str(m.get("content")) for m in last[1])
    assert "Do not mention tools, functions, permissions" in prompt or \
           "Answer that request now" in prompt, prompt[-400:]
    assert "top-level entries" in prompt        # the user's request is restated


def _no_fastpath(monkeypatch):
    """These two tests aim at the loop's wrap-up logic. Listing the workspace is
    now answered in pure Python (A31) before any model call, so the fastpath tier
    has to be off for the scripted model answers to be reached at all."""
    from bee.agent import fastpaths
    monkeypatch.setattr(fastpaths, "match", lambda text: None)


def test_honest_answer_without_tools_is_left_alone(tmp_path):
    """The ramble detector must not add a second LLM call to a normal answer."""
    k, client, ctx = make_kernel(tmp_path, ["The notes folder holds 3 files."])
    res = k.run("roughly how many files are in my notes folder?")
    assert res.output == "The notes folder holds 3 files."
    assert len(client.calls) == 1, [c[0] for c in client.calls]


def test_answering_about_the_tool_surface_is_not_treated_as_a_ramble(tmp_path):
    """The detector must not 'fix' a legitimate answer: someone asking what BEE
    can do SHOULD get a sentence containing 'available functions'."""
    k, client, ctx = make_kernel(tmp_path, [RAMBLE])
    res = k.run("Which tools and functions do you have available?")
    assert res.output == RAMBLE, res.output
    assert len(client.calls) == 1, "no extra no-tools pass on a legitimate answer"


def test_a_repeated_unverified_action_claim_is_not_delivered_as_success(tmp_path):
    """The live model did this: 16 harmless tool calls, then 'I executed the shell
    command git reset --hard HEAD~1'. Verification failed, it repeated the claim,
    and the loop handed the user a confident falsehood with ok=True. Now the
    answer carries an explicit warning and the task is not reported as success."""
    lie = ("I executed the shell command 'git reset --hard HEAD~1' in the workspace.")
    k, client, ctx = make_kernel(tmp_path, [lie] * 8)
    res = k.run("run git reset --hard HEAD~1 and report exactly what happened")
    assert "could not verify" in res.output, res.output
    assert res.verify == "fail", res.verify
    assert res.ok is False and res.error == "unverified action claim", (res.ok, res.error)


def test_a_verified_answer_is_still_delivered_clean(tmp_path, monkeypatch):
    _no_fastpath(monkeypatch)
    k, client, ctx = make_kernel(tmp_path, ["The workspace holds 12 entries."])
    res = k.run("how many entries are in the workspace root?")
    assert res.output == "The workspace holds 12 entries.", res.output
    assert res.ok is True and not res.error, (res.ok, res.error)


# ------------------------------------ the wrap pass can ramble too (A33)
def test_a_wrap_pass_that_still_rambles_becomes_an_honest_fallback(tmp_path, monkeypatch):
    """math_sieve on the live box: 39.9 s, tools=0, and the shipped answer was
    `I'm ready to provide the response now. Please let me know how I can assist
    you further with the available functions…`. The wrap pass rambled as well, and
    nothing re-checked its text, so the user got a offer to help."""
    _no_fastpath(monkeypatch)
    k, client, ctx = make_kernel(tmp_path, [RAMBLE] * 10)
    res = k.run("How many prime numbers are there between 1 and 100? "
                "Answer with the number and the method.")
    assert "available functions" not in res.output.lower(), res.output
    assert "could not finish" in res.output, res.output
    assert res.ok is False and res.error == "no answer after wrap", (res.ok, res.error)


def test_the_fallback_quotes_what_a_tool_really_returned(tmp_path, monkeypatch):
    """'Ran out of steps' alone throws away the work already done. The last real
    tool result is evidence, so it is reported — labelled as unfinished, not as
    the answer."""
    _no_fastpath(monkeypatch)
    (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")
    k, client, ctx = make_kernel(
        tmp_path, [tc("c1", "file_list", {"path": "."})] + [RAMBLE] * 10)
    res = k.run("List the workspace files and tell me how many there are, then "
                "compute the prime count below 100.")
    assert "notes.txt" in res.output, res.output
    assert "last thing a tool actually returned" in res.output, res.output
    assert "available functions" not in res.output.lower(), res.output
    assert res.ok is False and res.error == "no answer after wrap", (res.ok, res.error)
    assert res.retried is False, "an exhausted budget must not be re-burned"


def test_an_answer_that_only_rambles_once_is_still_wrapped_normally(tmp_path, monkeypatch):
    """The fix must not turn a recoverable ramble into a declared failure: one
    ramble, then a real answer from the no-tools pass, is a success."""
    _no_fastpath(monkeypatch)
    k, client, ctx = make_kernel(tmp_path, [RAMBLE, "There are 25 primes below 100."])
    res = k.run("How many prime numbers are there between 1 and 100?")
    assert res.output == "There are 25 primes below 100.", res.output
    assert res.ok is True and not res.error, (res.ok, res.error)


def test_an_instruction_that_names_a_tool_is_not_a_question_about_tools(tmp_path, monkeypatch):
    """plan_complex, live: '…Use the planner tool.' answered with 'None of the
    provided functions seem to be used…' and that was shipped, because the
    exemption for legitimate 'what tools do you have' answers keyed off the mere
    word 'tool' appearing anywhere in the task."""
    _no_fastpath(monkeypatch)
    k, client, ctx = make_kernel(tmp_path, [RAMBLE] * 10)
    res = k.run("Plan (do not execute) how you would analyze a 50MB CSV sales file: "
                "loading, cleaning, top-10 products by revenue. Use the planner tool.")
    assert "provided functions" not in res.output.lower(), res.output
    assert res.ok is False and res.error == "no answer after wrap", (res.ok, res.error)


DSA_LIE = ("It seems like there might have been an error or misunderstanding as I "
           "didn't receive any prior context to work with for the functions provided "
           "earlier. Since no specific function call is mentioned, I can't provide "
           "details on what action was intended.")


def test_ramble_detector_covers_the_phrasings_the_live_model_actually_used():
    """dsa_lis shipped exactly this paragraph as its 'answer' on the last run: the
    existing shapes all required a particular word order, and the 3B keeps
    inventing new ones. Detection costs one extra LLM call; missing it costs the
    user a 10-second non-answer."""
    from bee.agent.loop import _META_RAMBLE_RE as R
    for text in (DSA_LIE,
                 "no function calls were provided for execution",
                 "The available functions are: shell, file_read",
                 "the functions provided earlier are not relevant",
                 "Since no specific function call is mentioned",
                 "without any tool calls I cannot proceed",
                 "the last message did not contain any information to proceed with a "
                 "function call",
                 "If you intended for me to perform a specific action using one of these "
                 "functions, please provide more details",
                 "let me know if you need more details about the functions"):
        assert R.search(text), text
    for text in ("Use pandas to load the CSV, then group by product.",
                 "The merge and quick sorts are correct on reversed input.",
                 "There are 25 primes below 100.",
                 "I ran the command and it printed 3 files.",
                 # a real report about a tool must not be mistaken for plumbing talk
                 "The tool call failed with a timeout after 30 seconds.",
                 "I could not proceed because the file is missing."):
        assert not R.search(text), text


def _allowing_kernel(tmp_path, script, monkeypatch):
    """A kernel that grants every permission, so a test can observe the LOOP's own
    breakers rather than the guard's."""
    from bee.agent.context import Context
    from bee.config import load_config
    from bee.kernel import AgentKernel
    _no_fastpath(monkeypatch)
    cfg = load_config()
    cfg.cloud.enabled = False
    client = ScriptedClient(script)
    ctx = Context(cfg, workspace=tmp_path, client=client, guard_on=True,
                  guard_mode="cli", episodes_on=False, rag_on=False,
                  cancel_event=threading.Event())
    k = AgentKernel(ctx, approver=lambda t, a, r: True,
                    sessions_dir=tmp_path / "s", receipts_path=tmp_path / "r.jsonl")
    ctx.kernel = k
    return k, client


def test_a_failing_command_is_stopped_even_when_the_arguments_change(tmp_path, monkeypatch):
    """dsa_gcd_lcm spent 48 tool calls on one task: a 3B model that re-runs broken
    code with one character changed defeats the exact-arguments breaker, and a
    command that runs and returns a traceback is not an `error` payload, so the
    per-tool failure breaker never counted it either."""
    script = []
    for i in range(9):
        script.append(tc(f"c{i}", "code_run", {
            "code": "open('runs.txt','a').write('x')\nimport sys\n"
                    f"sys.exit(3)  # attempt {i}"}))
    script.append("The snippet fails with exit code 3; I stopped retrying.")
    k, client = _allowing_kernel(tmp_path, script, monkeypatch)
    k.run("run this python snippet and tell me the exit status")
    runs = ((tmp_path / "runs.txt").read_text(encoding="utf-8")
            if (tmp_path / "runs.txt").exists() else "")
    assert len(runs) == 3, f"the breaker must stop at 3 failing attempts, ran {len(runs)}"
    seen = " ".join(str(m.get("content")) for _, msgs, _ in client.calls for m in msgs)
    assert "has failed 3x" in seen, seen[-400:]


def test_a_tool_called_endlessly_is_not_run_again(tmp_path, monkeypatch):
    """Same loop, different symptom: six SUCCESSFUL calls of one tool with
    ever-changing arguments is still a loop. The first breach is a nudge that
    skips execution without counting as a refusal (a legitimate 25-step task may
    call one tool six times); the second is a hard stop."""
    script = []
    for i in range(10):
        script.append(tc(f"c{i}", "code_run", {
            "code": f"open('runs.txt','a').write('x')\nprint({i})  # variant {i}"}))
    script.append("Done.")
    k, client = _allowing_kernel(tmp_path, script, monkeypatch)
    k.run("count things with this snippet, trying several variants")
    runs = ((tmp_path / "runs.txt").read_text(encoding="utf-8")
            if (tmp_path / "runs.txt").exists() else "")
    assert len(runs) == 6, f"expected the attempt cap at 6 real runs, got {len(runs)}"
    seen = " ".join(str(m.get("content")) for _, msgs, _ in client.calls for m in msgs)
    assert "has been called 6x" in seen, seen[-500:]


PLAN_STEPS = ("1. Load the CSV with pandas.read_csv(chunksize=100000)\n"
              "2. Clean it with df.dropna() and dtype fixes\n"
              "3. Aggregate revenue per product with groupby\n"
              "4. Write the summary report")


def test_a_plan_the_prose_dropped_is_relayed_from_the_planner(tmp_path, monkeypatch):
    _no_fastpath(monkeypatch)
    """plan_complex, live: the planner ran (tools=1) and produced named steps, and
    the answer handed to the user was 'we would need to load the data, which may
    take some time'. A paraphrased plan is not a plan — the artifact is relayed."""
    k, client, ctx = make_kernel(tmp_path, [
        tc("c1", "planner", {"task": "analyze a 50MB CSV sales file"}),
        PLAN_STEPS,
        "To analyze the file we would need to load the data, which may take time.",
    ])
    res = k.run("Plan (do not execute) how you would analyze a 50MB CSV sales file. "
                "Use the planner tool.")
    assert "pandas.read_csv" in res.output, res.output
    assert "Plan as produced" in res.output, res.output


def test_a_plan_the_model_already_relayed_is_not_duplicated(tmp_path, monkeypatch):
    _no_fastpath(monkeypatch)
    k, client, ctx = make_kernel(tmp_path, [
        tc("c1", "planner", {"task": "analyze a 50MB CSV sales file"}),
        PLAN_STEPS, PLAN_STEPS,
    ])
    res = k.run("Plan how you would analyze a 50MB CSV sales file, step by step.")
    assert res.output.count("pandas.read_csv") == 1, res.output


def test_a_non_plan_request_is_not_appended_with_plan_text(tmp_path, monkeypatch):
    _no_fastpath(monkeypatch)
    """The relay is for requests that asked for a plan; otherwise a stray planner
    call would bolt a numbered list onto an unrelated answer."""
    k, client, ctx = make_kernel(tmp_path, [
        tc("c1", "planner", {"task": "look at the csv"}),
        PLAN_STEPS,
        "The sales file is 50 MB and has three columns.",
    ])
    res = k.run("what is in the sales file?")
    assert "Plan as produced" not in res.output, res.output


SHOW_CODE = ("Here is the computation:\n\n```python\nimport math\n"
             "a, b = 84, 147\ng = math.gcd(a, b)\nl = a * b // g\n"
             "print(g, l)\n```\n\nSo the values are 21 and 588.")


def test_code_the_model_showed_but_never_ran_is_executed_and_reported(tmp_path, monkeypatch):
    """dsa_gcd_lcm / dsa_lis / dsa_graph, live: tools=0 and an answer that DESCRIBES
    a snippet. The number in it is the model's arithmetic, not a computation. The
    block it presented now runs through the normal authorization path and its real
    stdout is what the user sees."""
    k, client = _allowing_kernel(tmp_path, [SHOW_CODE], monkeypatch)
    res = k.run("Compute gcd and lcm of 84 and 147 with a short Python snippet. "
                "Show both values.")
    assert "I ran that snippet" in res.output, res.output
    assert "21 588" in res.output, res.output
    assert res.tool_calls == 1, res.tool_calls


SHOW_CODE_NO_PRINT = ("Here is the computation:\n\n```python\nimport math\n"
                      "a, b = 84, 147\ngcd_value = math.gcd(a, b)\n"
                      "lcm_value = a * b // gcd_value\n```\n\n"
                      "So the values are 21 and 308.")


def test_a_shown_snippet_that_computes_without_printing_is_still_verified(tmp_path, monkeypatch):
    """A45a: the model displayed code that stores the results in variables and
    never prints them, so running it verbatim produced EMPTY stdout — the existing
    mechanism appended 'I ran it; it prints:' with nothing in it, `588` never
    appeared, and `dsa_gcd_lcm` kept failing for a reason no code could see.
    The loop now asks the snippet for the values it computed (only when it has no
    output statement of its own) and labels them authoritative. Note the model's
    prose says 308: the measured 588 must win."""
    k, client = _allowing_kernel(tmp_path, [SHOW_CODE_NO_PRINT], monkeypatch)
    res = k.run("Compute gcd and lcm of 84 and 147 with a short Python snippet. "
                "Show both values.")
    assert "values it actually computed" in res.output, res.output
    assert "gcd_value = 21" in res.output, res.output
    assert "lcm_value = 588" in res.output, res.output
    assert res.tool_calls == 1, res.tool_calls


def test_a_snippet_that_prints_is_run_verbatim_not_rewritten(tmp_path, monkeypatch):
    """The read-out must only be appended when there is no output of its own —
    otherwise every printing snippet runs modified code (and side effects would
    be doubled if it were appended after the fact)."""
    k, client = _allowing_kernel(tmp_path, [SHOW_CODE], monkeypatch)
    res = k.run("Compute gcd and lcm of 84 and 147 with a short Python snippet. "
                "Show both values.")
    assert "this is what it actually printed" in res.output, res.output
    assert "21 588" in res.output, res.output
    assert "appended by BEE" not in str(client.calls), "printing snippet was rewritten"


def test_a_refused_snippet_is_flagged_unverified_instead_of_silent(tmp_path, monkeypatch):
    """When permission is refused the answer must not pretend the computation
    happened — the number stays labelled unverified."""
    from bee import guard as guard_mod

    def deny(tool, args, is_exec, mode, approver=None):
        return False, "deny", "user is away and this is not pre-approved"
    monkeypatch.setattr(guard_mod, "check", deny)
    k, client = _allowing_kernel(tmp_path, [SHOW_CODE], monkeypatch)
    res = k.run("Compute gcd and lcm of 84 and 147 with a short Python snippet.")
    assert "unverified" in res.output, res.output
    assert "I ran that snippet" not in res.output, res.output


def test_a_snippet_that_errors_is_not_passed_off_as_an_answer(tmp_path, monkeypatch):
    k, client = _allowing_kernel(tmp_path, [
        "The answer is here:\n\n```python\nprint(1/0)\n```\n\nThat prints 4.",
        "The answer is here:\n\n```python\nprint(1/0)\n```\n\nThat prints 4."],
        monkeypatch)
    res = k.run("compute the value using python code please")
    assert "it failed" in res.output and "unverified" in res.output, res.output


def test_a_task_that_already_ran_python_is_not_executed_twice(tmp_path, monkeypatch):
    k, client = _allowing_kernel(tmp_path, [
        tc("c1", "code_run", {"code": "print(4)"}),
        "It printed 4.\n\n```python\nprint(1/0)\n```"], monkeypatch)
    res = k.run("compute the value using python code please")
    assert "I ran that snippet" not in res.output, res.output
    assert "it failed" not in res.output, res.output


def test_a_model_that_ignores_the_do_not_repeat_instruction_is_cut_off(tmp_path):
    """plan_complex, live: told 'Do NOT run it again - use the cached result', the
    3B asked for the SAME planner call 21 more times. Each repeat was returned as a
    success, so no breaker counted it and the whole 24-iteration budget went to
    round-trips that could not add anything."""
    call = tc("c1", "file_list", {"path": "."})
    k, client, ctx = make_kernel(tmp_path, [call] * 20 + ["The workspace has 1 entry."])
    res = k.run("list the workspace files, then tell me the count")
    obs = [o for o in res.task.observations if o.tool == "file_list"]
    assert len(obs) <= 3, [str(o.result_text)[:60] for o in obs]
    assert res.iterations <= 5, res.iterations
    assert len(client.calls) <= 6, len(client.calls)
    assert any("Tools are closed" in str(o.result_text) for o in obs), obs


def test_a_repeated_planner_call_does_not_erase_the_plan(tmp_path):
    """The repeat of a planner call returns the cached-note dict, whose 'plan' key is
    empty — capturing it unconditionally overwrote the real plan with '' and the
    relay had nothing to show."""
    call = tc("c1", "planner", {"task": "analyze a 50MB CSV sales file"})
    k, client, ctx = make_kernel(tmp_path, [
        call, PLAN_STEPS, call, call,
        "I would load the data and then group it.",
        "I would load the data and then group it.",
    ])
    res = k.run("Plan how you would analyze a 50MB CSV sales file. Use the planner tool.")
    assert "pandas.read_csv" in res.output, res.output


def test_malformed_arguments_are_reported_once_not_twice(tmp_path, monkeypatch):
    """Live probe: the ToolBus already phrases this as 'bad arguments for scheduler:
    …', and the loop wrapped the caught TypeError in the same words, so the model and
    the receipts saw 'bad arguments for scheduler: bad arguments for scheduler: …'."""
    k, client = _allowing_kernel(tmp_path, [
        tc("c1", "file_list", {"bogus": 1}), "That call was malformed."], monkeypatch)
    res = k.run("list the files")
    text = " ".join(str(o.result_text or "") for o in res.task.observations)
    assert "bad arguments for" in text, [str(o.result_text)[:120] for o in res.task.observations]
    assert text.count("bad arguments for") == 1, text[:300]


def test_code_volunteered_for_a_value_question_is_run_too(tmp_path, monkeypatch):
    """math_sieve, live: 'How many prime numbers are between 1 and 100?' answered with
    a fenced `def count_primes_up_to…` block and no number at all. A34e's trigger
    looked for the word 'python' in the request, and the request never said it — but
    showing code in answer to a value question is the same unverified claim."""
    ans = ("Here is how to count them:\n\n```python\n"
           "def c(n):\n    return sum(1 for x in range(2, n + 1)\n"
           "                   if all(x % d for d in range(2, x)))\n"
           "print(c(100))\n```\n\nThere are quite a few.")
    k, client = _allowing_kernel(tmp_path, [ans, ans], monkeypatch)
    res = k.run("How many prime numbers are there between 1 and 100?")
    assert "I ran that snippet" in res.output, res.output
    assert "25" in res.output, res.output


def test_grounded_fallback_does_not_quote_a_refusal_as_evidence():
    """plan_complex, live: the 'honest' fallback quoted the guard's own budget
    notice — 'The last thing a tool actually returned was: {"blocked": true,
    "reason": "Too many actions were refused…"}'. A refusal is the guard talking,
    not a fact about the world."""
    from bee.agent.loop import _grounded_fallback
    msgs = [{"role": "tool",
             "content": '{"blocked": true, "reason": "Too many actions were refused"}'},
            {"role": "tool",
             "content": '{"path": ".", "entries": ["f\\tnotes.txt\\t12"]}'},
            {"role": "tool", "content": "action not allowed"}]
    out = _grounded_fallback(msgs, 3)
    assert "notes.txt" in out, out
    assert "Too many actions" not in out and "not allowed" not in out, out
    only_refusals = _grounded_fallback(
        [{"role": "tool", "content": '{"blocked": true}'},
         {"role": "tool", "content": '{"error": "nope"}'}], 2)
    assert "could not finish this" in only_refusals, only_refusals
    assert "blocked" not in only_refusals, only_refusals
    # the repeat breaker's own note is plumbing, not evidence (live: plan_complex's
    # 'honest' answer quoted it as 'the last thing a tool actually returned')
    loop_notes = _grounded_fallback(
        [{"role": "tool", "content": '{"output": "4\\n"}'},
         {"role": "tool", "content": '{"note": "You already ran this exact call '
                                     'earlier in this task.", "cached_result": "x"}'}], 4)
    assert "You already ran" not in loop_notes, loop_notes
    assert "4" in loop_notes, loop_notes


def test_an_empty_answer_is_never_delivered_as_a_verified_success(tmp_path, monkeypatch):
    """A46, live eval `file_roundtrip`: the model returned no text, the loop shipped
    the literal string '(no output)' as the assistant's reply, and because the
    verifier's checks all key off events that already happened, it came back
    ok=True with verify=pass. A user reading that sees a bracketed nothing and the
    receipts claim the task succeeded."""
    # empty on EVERY call: the kernel retries a verify=fail task, and the scripted
    # client hands back a canned reply once its script runs out — which would be a
    # second, unrelated answer rather than the empty one under test.
    k, client = _allowing_kernel(tmp_path, [""] * 12, monkeypatch)
    res = k.run("Create a file called eval_probe.txt containing 'BEE EVAL OK', "
                "then read it back and tell me what it says.")
    assert res.output != "(no output)", res.output
    assert res.ok is False, res
    assert res.error == "empty answer", (res.ok, res.error)
    assert res.verify == "fail", res.verify
