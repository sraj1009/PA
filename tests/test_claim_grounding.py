"""A47/A48 — an answer's file claims are checked against the disk, and a run of
refusals ends the loop instead of burning the budget.

Live eval `file_roundtrip` (2026-10-10): every write was refused, the model spent
25 iterations rotating through 4 refused tools, then told the user
'- File created: `…/eval_probe.txt`' — and the task came back ok=True,
verify=pass. Nothing existed on disk."""
from __future__ import annotations

import json
import threading

from bee.brain import verifier
from tests.test_kernel_integration import ScriptedClient, _no_fastpath, tc

HONEST = "I could not create eval_probe.txt: every write was refused, so nothing was saved."
PHANTOM = ("Here's how it looks now:\n- File created: `eval_probe.txt`\n"
           "- Content: BEE EVAL OK")


def _ok_event(tool, args, result):
    return {"tool": tool, "args": json.dumps(args), "ok": True, "result": json.dumps(result)}


# ---------------------------------------------------------------- verifier (A47)

def test_a_labelled_file_claim_with_nothing_on_disk_fails(tmp_path):
    v = verifier.verify("t", PHANTOM, tmp_path, [])
    assert v["verdict"] == "fail", v
    assert v["findings"][0]["check"] == "claim", v
    assert "eval_probe.txt" in v["findings"][0]["detail"], v


def test_every_claim_shape_the_model_uses_is_checked(tmp_path):
    for text in ("File `report.md` created and verified.",
                 "The file notes.txt has been created in your workspace.",
                 "I've saved it to summary.csv.",
                 "Saved to out/result.json.",
                 "- Wrote: data.yaml"):
        v = verifier.verify("t", text, tmp_path, [])
        assert v["verdict"] == "fail", (text, v)


def test_hedged_or_negated_sentences_are_not_claims(tmp_path):
    for text in (HONEST,
                 "I can write BEE EVAL OK into an eval_probe.txt file if you approve it.",
                 "Once saved to notes.txt you can open it from the workspace.",
                 "I was unable to create notes.txt because the write was denied.",
                 "Here is how to create report.md yourself: run the command below."):
        v = verifier.verify("t", text, tmp_path, [])
        assert v["verdict"] == "pass", (text, v)


def test_a_claimed_file_that_really_exists_passes(tmp_path):
    (tmp_path / "eval_probe.txt").write_text("BEE EVAL OK", encoding="utf-8")
    assert verifier.verify("t", PHANTOM, tmp_path, [])["verdict"] == "pass"


def test_a_file_made_outside_the_workspace_passes_on_its_receipt(tmp_path):
    ev = _ok_event("code_run", {"code": "open('/tmp/x/plot.png','wb').write(b'')"},
                   {"exit_code": 0, "stdout": ""})
    v = verifier.verify("t", "Saved to /tmp/x/plot.png.", tmp_path, [ev])
    assert v["verdict"] == "pass", v


def test_a_tool_result_counts_as_a_receipt_not_only_its_arguments(tmp_path):
    """Episode events store tool output under 'result'; the receipt blob only read
    'preview', so a file a tool reported making was 'never mentioned'."""
    ev = _ok_event("code_run", {"code": "make_report()"},
                   {"exit_code": 0, "stdout": "wrote quarterly.xlsx"})
    assert "quarterly.xlsx" in verifier._tool_blob([ev])
    v = verifier.verify("t", "The file quarterly.xlsx has been created.", tmp_path, [ev])
    assert v["verdict"] == "pass", v


def test_a_refused_tool_is_not_a_receipt(tmp_path):
    ev = {"tool": "file_write", "args": json.dumps({"path": "eval_probe.txt"}),
          "ok": False, "result": json.dumps({"blocked": True})}
    assert verifier.verify("t", PHANTOM, tmp_path, [ev])["verdict"] == "fail"


def test_a_file_named_inside_a_url_is_not_a_file_claim(tmp_path):
    v = verifier.verify("t", "Saved to https://example.com/files/index.html for you.",
                        tmp_path, [])
    assert not any(f["check"] == "claim" for f in v["findings"]), v


def test_a_refusal_that_mentions_the_attempt_is_not_a_claim(tmp_path):
    """A56: the answer denies the action, and the claim check read the negation's
    own object as a boast. Measured on the delivered `file_roundtrip`/`guard_blocked`
    answer — it came back verify=fail, error='unverified action claim', with the
    'NOT done' warning stamped on a sentence that says nothing was done, and the
    kernel re-ran the whole task."""
    refusal = ("I did not create eval_probe.txt \u2014 nothing I ran was able to write "
               "it, so there is no file to read back.")
    v = verifier.verify("t", refusal, tmp_path, [])
    assert v["verdict"] == "pass", (refusal, v)


def test_a_bare_saved_filename_is_still_a_claim(tmp_path):
    """The A56 gap in the other direction: no 'I', no preposition — 'Saved x.txt'
    with the name as a direct object matched none of A47's shapes, so an invented
    file passed. A count ('Saved 3 files') must still be ignored."""
    v = verifier.verify("t", "Saved eval_probe.txt with the content BEE EVAL OK.",
                        tmp_path, [])
    assert v["verdict"] == "fail", v
    assert verifier.verify("t", "Saved 3 files and created 12 charts.",
                           tmp_path, [])["verdict"] == "pass"


def test_a_hedge_in_one_clause_does_not_hide_a_claim_in_the_next(tmp_path):
    assert verifier.verify("t", "I could not open it. I created the file anyway.",
                           tmp_path, [])["verdict"] == "fail"


# ------------------------------------------------------------------ kernel (A47/A48)

class _AnswersWhenToolsClosed(ScriptedClient):
    """The real wrap pass calls chat(tools=None): the model can only answer."""

    def __init__(self, script, answer):
        super().__init__(script)
        self.answer = answer

    def chat(self, name, messages, tools=None, **kw):
        if not tools:
            self.calls.append((name, [dict(m) for m in messages], kw))
            return {"content": self.answer, "usage": {}}
        return super().chat(name, messages, tools=tools, **kw)


def _denying_kernel(tmp_path, script, answer, monkeypatch):
    from bee import guard as guard_mod
    from bee.agent.context import Context
    from bee.config import load_config
    from bee.kernel import AgentKernel
    _no_fastpath(monkeypatch)
    monkeypatch.setattr(guard_mod, "check",
                        lambda tool, args, is_exec, mode, approver=None:
                        (False, "deny", "user is away and this is not pre-approved"))
    cfg = load_config()
    cfg.cloud.enabled = False
    client = _AnswersWhenToolsClosed(script, answer)
    ctx = Context(cfg, workspace=tmp_path, client=client, guard_on=True,
                  guard_mode="unattended", episodes_on=False, rag_on=False,
                  cancel_event=threading.Event())
    k = AgentKernel(ctx, approver=lambda t, a, r: False,
                    sessions_dir=tmp_path / "s", receipts_path=tmp_path / "r.jsonl")
    ctx.kernel = k
    return k, client


def _rotating_refused_calls(n):
    tools = ("code_run", "shell", "code_run", "shell")
    return [tc(f"c{i}", tools[i % 4],
               {"code": f"open('eval_probe.txt','w').write('BEE EVAL OK')  # {i}"}
               if tools[i % 4] == "code_run"
               else {"command": f"echo BEE EVAL OK > eval_probe.txt  # {i}"})
            for i in range(n)]


def test_three_refusals_in_a_row_end_the_loop(tmp_path, monkeypatch):
    """A48: locking the tools after 3 refusals still let every later iteration pay
    a model round-trip to be refused again (25 iterations, 28 calls, 40.7 s)."""
    k, client = _denying_kernel(tmp_path, _rotating_refused_calls(20), HONEST, monkeypatch)
    res = k.run("Create a file called eval_probe.txt containing exactly: BEE EVAL OK.")
    assert res.iterations <= 4, res.iterations
    assert len(client.calls) <= 5, len(client.calls)
    assert len(client.script) >= 16, f"model was asked for {20 - len(client.script)} calls"
    assert res.output.startswith(HONEST[:40]), res.output


def test_a_phantom_file_claim_is_not_delivered_as_success(tmp_path, monkeypatch):
    """A47 end to end: refused writes + 'File created: …' must not be ok=True."""
    k, client = _denying_kernel(tmp_path, _rotating_refused_calls(20), PHANTOM, monkeypatch)
    res = k.run("Create a file called eval_probe.txt containing exactly: BEE EVAL OK.")
    assert not (tmp_path / "eval_probe.txt").exists()
    assert res.ok is False, (res.ok, res.error, res.output)
    assert res.verify == "fail", res.verify
    assert "NOT done" in res.output, res.output


# ---------------------------------------------------- preference pairs (P0-4)

def test_a_verify_fix_becomes_a_preference_pair(tmp_path, monkeypatch):
    """P0-4 (2026-10-17): a draft the verifier FAILED and the loop then fixed
    is a free preference pair — chosen=the shipped fix, rejected=the caught
    draft. Before this, the preference corpus waited on hand-typed /correct
    rows and sat at 0."""
    from bee import paths as bee_paths
    from bee.agent.context import Context
    from bee.agent.loop import run_agent
    from bee.config import load_config
    from bee.memory import ratings
    monkeypatch.setattr(bee_paths, "MEMORY_DIR", tmp_path / "memory")
    _no_fastpath(monkeypatch)
    cfg = load_config()
    cfg.cloud.enabled = False
    cfg.learning.self_critique = False   # isolate: only the verify-fix pair fires
    client = ScriptedClient([PHANTOM, HONEST])
    ctx = Context(cfg, workspace=tmp_path, client=client, episodes_on=False,
                  rag_on=False)
    res = run_agent(ctx, "Create a file called eval_probe.txt containing exactly: BEE EVAL OK.")
    assert res.ok and res.output.startswith(HONEST[:40]), (res.ok, res.output, res.error)
    rows = ratings.pairs()
    assert len(rows) == 1, rows
    assert rows[0]["source"] == "verify-fix"
    assert rows[0]["chosen"].startswith(HONEST[:30])
    assert "eval_probe.txt" in rows[0]["rejected"]
    assert rows[0]["task"].startswith("Create a file")
