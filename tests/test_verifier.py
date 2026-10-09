"""Verifier — deterministic claim checks against episode events + disk. Run: python tests/test_verifier.py"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bee.brain import verifier  # noqa: E402


def _calc(expr, stated):
    return {"tool": "calculator", "ok": True, "args": json.dumps({"expression": expr}),
            "result": json.dumps({"expression": expr, "result": stated})}


def test_math_fail():
    events = [_calc("2+2", "5")]
    v = verifier.verify("t", "the answer is 5", Path(tempfile.gettempdir()), events)
    assert v["verdict"] == "fail" and v["findings"][0]["check"] == "math", v


def test_math_pass():
    events = [_calc("2+2", "4")]
    v = verifier.verify("t", "the answer is 4", Path(tempfile.gettempdir()), events)
    assert v["verdict"] == "pass", v


def test_file_missing():
    ws = Path(tempfile.mkdtemp())
    events = [{"tool": "file_write", "ok": True,
               "args": json.dumps({"path": "nope.txt", "content": "x"}),
               "result": json.dumps({"path": "nope.txt"})}]
    v = verifier.verify("t", "I wrote nope.txt", ws, events)
    assert v["verdict"] == "fail" and v["findings"][0]["check"] == "file", v


def test_file_present():
    ws = Path(tempfile.mkdtemp())
    (ws / "ok.txt").write_text("hello BEE", encoding="utf-8")
    events = [{"tool": "file_write", "ok": True,
               "args": json.dumps({"path": "ok.txt", "content": "hello BEE"}),
               "result": json.dumps({"path": "ok.txt"})}]
    v = verifier.verify("t", "done", ws, events)
    assert v["verdict"] == "pass", v


def test_url_unfetched_warn():
    events = []
    v = verifier.verify("t", "see https://never-fetched.example.com/page for details",
                        Path(tempfile.gettempdir()), events)
    assert v["verdict"] == "warn" and v["findings"][0]["check"] == "url", v


def test_url_fetched_pass():
    events = [{"tool": "web_fetch", "ok": True,
               "args": json.dumps({"url": "https://ok.example.com/page"}),
               "result": "{}"}]
    v = verifier.verify("t", "from https://ok.example.com/page: fact",
                        Path(tempfile.gettempdir()), events)
    assert v["verdict"] == "pass", v


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  [PASS] {fn.__name__}")
        except Exception as e:
            print(f"  [FAIL] {fn.__name__}: {e}")
            failed += 1
    print(f"\n{len(fns) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


# ------------------------------------------- claims vs evidence (A29)
def test_a_claimed_action_with_no_receipt_fails_verification(tmp_path):
    """The eval produced `I executed the shell command 'git reset --hard HEAD~1'`
    with zero tool calls in the episode. A user reading that believes their repo
    was reset — the most damaging kind of wrong answer, and the one check the
    verifier did not have (math/file/url all key off events that already happened)."""
    from bee.brain import verifier as V
    r = V.verify("run git reset --hard HEAD~1",
                 "I executed the shell command 'git reset --hard HEAD~1' in the workspace.",
                 tmp_path, [])
    assert r["verdict"] == "fail", r
    assert any(f["check"] == "claim" for f in r["findings"]), r


def test_a_claim_backed_by_a_real_tool_call_passes(tmp_path):
    from bee.brain import verifier as V
    events = [{"ok": True, "tool": "shell", "args": '{"command": "git status"}'}]
    r = V.verify("check git status", "I ran git status; the tree is clean.", tmp_path, events)
    assert r["verdict"] == "pass", r


def test_a_claim_after_a_failed_tool_call_still_fails(tmp_path):
    from bee.brain import verifier as V
    events = [{"ok": False, "tool": "file_write", "args": "{}"}]
    r = V.verify("make report.md", "I created the file report.md.", tmp_path, events)
    assert r["verdict"] == "fail", r


def test_ordinary_answers_are_not_flagged(tmp_path):
    from bee.brain import verifier as V
    for ans in ("The capital of France is Paris.",
                "I could not run that — the guard blocked it.",
                "Merge sort is O(n log n); quick sort is O(n^2) worst case."):
        assert V.verify("q", ans, tmp_path, [])["verdict"] != "fail", ans


def test_a_claim_must_match_a_receipt_not_just_any_receipt(tmp_path):
    """'Did any tool run?' is far too weak. Live evidence: the model made 23
    harmless tool calls, never ran git reset, and still reported
    "I executed the shell command 'git reset --hard HEAD~1'… your changes were
    discarded" — which the first version of the claim check passed."""
    import json
    from bee.brain import verifier as V
    lie = ("I executed the shell command 'git reset --hard HEAD~1' in the "
           "workspace. Your changes were discarded.")
    harmless = [
        {"ok": True, "tool": "file_read", "args": json.dumps({"path": "a.md"}),
         "preview": "…"},
        {"ok": True, "tool": "system_health", "args": "{}", "preview": "ram ok"},
    ]
    r = V.verify("run git reset --hard HEAD~1", lie, tmp_path, harmless)
    assert r["verdict"] == "fail", r
    assert any(f["check"] == "claim" and "git" in f["detail"] for f in r["findings"]), r

    # the same sentence with a real matching receipt passes
    truth = [{"ok": True, "tool": "shell",
              "args": json.dumps({"command": "git reset --hard HEAD~1"}),
              "preview": "HEAD is now at 384badf"}]
    assert V.verify("run git reset --hard HEAD~1", lie, tmp_path, truth)["verdict"] == "pass"


def test_a_claim_without_a_quoted_target_needs_only_some_receipt(tmp_path):
    """The rule must not demand evidence for prose it cannot resolve to a target,
    or every 'I ran the backup' after a real job creation would be refused."""
    from bee.brain import verifier as V
    ev = [{"ok": True, "tool": "automation_job", "args": "{}", "preview": "created job_x"}]
    r = V.verify("schedule a backup", "I ran the backup for you.", tmp_path, ev)
    assert r["verdict"] == "pass", r


def test_running_out_of_steps_is_not_an_action_claim(tmp_path):
    """"I ran out of steps…" is ordinary speech, but 'ran' sat in the claim verb
    list, so the assistant's own honest failure message was graded as an
    unverified destructive claim — and the kernel then retried the whole budget
    to 'correct' it (39.9 s -> 80 s on the eval box)."""
    from bee.brain import verifier as V
    honest = ("I ran out of steps before I could put this together. The last thing "
              "a tool actually returned was: notes.txt")
    r = V.verify("list the files and count the primes below 100", honest, tmp_path, [])
    assert not any(f.get("check") == "claim" for f in r["findings"]), r
    for phrase in ("I ran into a problem", "I ran the risk of losing data",
                   "I have run out of time"):
        assert not V._CLAIM_RE.search(phrase), phrase
    for phrase in ("I ran the command", "I have run the migration",
                   "I ran git push --force"):
        assert V._CLAIM_RE.search(phrase), phrase
