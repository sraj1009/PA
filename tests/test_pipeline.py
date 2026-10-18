"""Data pipeline — validate / sanitize / build_sft / train_router (offline).
Run: python tests/test_pipeline.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bee.pipeline import validate, sanitize  # noqa: E402
from bee.pipeline.build_sft import row_to_messages  # noqa: E402


def _ev(tool, ok=True, args="{}", result="{}"):
    return {"tool": tool, "ok": ok, "args": args, "result": result, "seconds": 0.1}


def test_validate_math_pass():
    row = {"ok": True, "task": "compute 2+2", "output": "the answer is 4",
           "events": [_ev("calculator", True,
                          json.dumps({"expression": "2+2"}),
                          json.dumps({"result": "4"}))]}
    v = validate.validate(row)
    assert v["verdict"] == "pass" and v["type"] == "math", v


def test_validate_math_fail():
    row = {"ok": True, "task": "compute 2+2", "output": "the answer is 5",
           "events": [_ev("calculator", True,
                          json.dumps({"expression": "2+2"}),
                          json.dumps({"result": "4"}))]}
    v = validate.validate(row)
    assert v["verdict"] == "fail", v


def test_validate_file_missing():
    row = {"ok": True, "task": "write x", "output": "done",
           "events": [_ev("file_write", True,
                          json.dumps({"path": "nope.txt", "content": "c"}), "{}")]}
    v = validate.validate(row, Path(__file__).parent)
    assert v["verdict"] == "fail" and v["type"] == "file", v


def test_validate_failed_episode():
    row = {"ok": False, "task": "x", "output": "", "events": []}
    assert validate.validate(row)["verdict"] == "fail"


def test_detect_types():
    assert validate.detect_type("compute 1+1", [_ev("calculator")]) == "math"
    assert validate.detect_type("write a file", [_ev("file_write")]) == "file"
    assert validate.detect_type("sort this array", [_ev("code_run")]) == "dsa"
    assert validate.detect_type("run the build", [_ev("shell")]) == "shell"
    assert validate.detect_type("look it up", [_ev("web_search")]) == "web"
    assert validate.detect_type("hi", []) == "generic"


def test_sanitize_redacts():
    row = {"ok": True, "task": "email me at john@gmail.com", "output": "done",
           "events": [_ev("shell", True, json.dumps({"command": "echo sk-abcdefghijklmnop1234"}), "{}")]}
    clean, n = sanitize.scrub_episode(row)
    assert n >= 2, n
    assert "john@gmail.com" not in json.dumps(clean)
    assert "sk-abcdefghijklmnop1234" not in json.dumps(clean)
    assert clean["metadata"]["redactions"] == n
    # original untouched
    assert "john@gmail.com" in row["task"]


def test_row_to_messages():
    row = {"ok": True, "task": "do it", "output": "done",
           "events": [_ev("calculator", True, json.dumps({"expression": "1+1"}),
                          json.dumps({"result": "2"}))]}
    # A60b changed the contract to (messages, dropped_bad_events) and build() sums
    # the second value into stats — the assertions below now unpack instead of
    # pretending the tuple is a list.
    msgs, dropped = row_to_messages(row)
    assert dropped == 0
    assert msgs[0]["role"] == "user" and msgs[0]["loss"] is False
    assert msgs[1]["role"] == "assistant" and msgs[1]["loss"] is True
    assert msgs[1]["tool_calls"][0]["function"]["name"] == "calculator"
    assert msgs[2]["role"] == "tool" and msgs[2]["loss"] is False
    assert msgs[3]["role"] == "assistant" and msgs[3]["content"] == "done"
    # failed episode -> no messages at all
    assert row_to_messages({**row, "ok": False, "output": ""}) == (None, 0)
    # a failed/blocked event is skipped AND counted, so the sample teaches the
    # recovery rather than the denied call: user + (assistant,tool) for the one good
    # event + final assistant = 4 messages, and 'rm -rf' appears nowhere.
    msgs, dropped = row_to_messages({**row, "events": [
        _ev("calculator", True, json.dumps({"expression": "1+1"}), json.dumps({"result": "2"})),
        _ev("shell", False, json.dumps({"command": "rm -rf /"}), '{"blocked": true}')]})
    assert dropped == 1 and len(msgs) == 4
    assert "rm -rf" not in json.dumps(msgs)


def test_router_label():
    from bee.pipeline.train_router import label_row
    assert label_row({"ok": True, "task": "2+2*3", "escalated": False}) == "det"
    assert label_row({"ok": True, "task": "write a report", "escalated": True}) == "cloud"
    assert label_row({"ok": True, "task": "write a report", "escalated": False}) == "local"
    assert label_row({"ok": False, "task": "2+2", "escalated": False}) is None  # failed: no label
    # serving model beats the flag (2026-10-17): hybrid cloud-first clears
    # `escalated` while the cloud model answered — unknown, not "local".
    assert label_row({"ok": True, "task": "routine ask", "escalated": False,
                      "model": "cloud"}) is None
    assert label_row({"ok": True, "task": "routine ask", "escalated": False,
                      "model": "local"}) == "local"
    assert label_row({"ok": True, "task": "remote ask", "escalated": False,
                      "model": "glm-5.2:cloud"}) is None


def test_build_sft_merges_cloud_golden(monkeypatch, tmp_path):
    from bee.pipeline import build_sft
    from bee import paths as p

    ep_dir = tmp_path / "episodes"
    ep_dir.mkdir()
    (ep_dir / "ep.jsonl").write_text(json.dumps(
        {"task": "compute 2+2", "output": "the answer is 4", "ok": True,
         "events": [_ev("calculator", True, json.dumps({"expression": "2+2"}),
                        json.dumps({"result": "4"}))],
         "date": "2026-10-05", "model": "local"}), encoding="utf-8")
    train_dir = tmp_path / "train"
    (train_dir / "golden").mkdir(parents=True)
    (train_dir / "golden" / "cloud_golden.jsonl").write_text(
        json.dumps({"task": "explain photosynthesis", "response": "It is how plants make food.",
                    "model": "cloud", "ts": "2026-10-05T12:00:00"}) + "\n"
        # duplicate task of the episode above -> must be deduped
        + json.dumps({"task": "compute 2+2", "response": "4", "model": "cloud",
                      "ts": "2026-10-05T12:01:00"}) + "\n",
        encoding="utf-8")

    monkeypatch.setattr(p, "EPISODES_DIR", ep_dir)
    monkeypatch.setattr(p, "TRAIN_DIR", train_dir)
    out = tmp_path / "sft.jsonl"
    stats = build_sft.build(workspace=tmp_path, out=out)

    rows = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
    # P1 parity: messages[0] is the canonical system prompt; the user task is
    # the first non-system message.
    tasks = {next(m["content"] for m in r["messages"] if m["role"] == "user") for r in rows}
    assert all(r["messages"][0]["role"] == "system" for r in rows), "parity prefix missing"
    assert stats["parity_in"] == stats["samples_out"] == 2, stats
    # golden is a 'generic' Q&A (verdict=unknown) — still trained on: cloud is the teacher
    assert stats["golden_in"] == 1, stats
    assert "explain photosynthesis" in tasks
    # dedupe: episode wins, golden dup dropped
    assert "compute 2+2" in tasks and stats["dropped_dup"] == 1
    assert stats["samples_out"] == 2


def test_build_sft_golden_still_scrubs_pii(monkeypatch, tmp_path):
    from bee.pipeline import build_sft
    from bee import paths as p

    ep_dir = tmp_path / "episodes"
    ep_dir.mkdir()
    train_dir = tmp_path / "train"
    (train_dir / "golden").mkdir(parents=True)
    (train_dir / "golden" / "cloud_golden.jsonl").write_text(json.dumps(
        {"task": "what is my email", "response": "Your email is john@gmail.com.",
         "model": "cloud", "ts": "2026-10-05T12:00:00"}), encoding="utf-8")

    monkeypatch.setattr(p, "EPISODES_DIR", ep_dir)
    monkeypatch.setattr(p, "TRAIN_DIR", train_dir)
    out = tmp_path / "sft.jsonl"
    build_sft.build(workspace=tmp_path, out=out)
    text = out.read_text(encoding="utf-8")
    assert "john@gmail.com" not in text


def test_parity_prefix_carries_identity_and_tool_surface(monkeypatch, tmp_path):
    """P1 SFT/inference parity: every emitted row carries the canonical system
    prompt inference sends — identity, the act-don't-refuse rule, the fitted
    local tool surface — with loss=False (never trained on). parity=False
    restores the old user-first row for one-off ablations."""
    from bee.pipeline import build_sft
    from bee import paths as p

    ep_dir = tmp_path / "episodes"
    ep_dir.mkdir()
    (ep_dir / "ep.jsonl").write_text(json.dumps(
        {"task": "compute 2+2", "output": "the answer is 4", "ok": True,
         "events": [], "date": "2026-10-05", "model": "local"}), encoding="utf-8")
    train_dir = tmp_path / "train"
    (train_dir / "golden").mkdir(parents=True)
    monkeypatch.setattr(p, "EPISODES_DIR", ep_dir)
    monkeypatch.setattr(p, "TRAIN_DIR", train_dir)

    out = tmp_path / "sft.jsonl"
    stats = build_sft.build(workspace=tmp_path, out=out, keep_unknown=True, min_quality=0.0)
    assert stats["parity_in"] == 1 and stats["samples_out"] == 1, stats
    sample = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
    sysmsg = sample["messages"][0]
    assert sysmsg["role"] == "system" and sysmsg["loss"] is False
    assert "You are BEE" in sysmsg["content"]
    assert "Act, don't refuse" in sysmsg["content"]
    assert "calculator" in sysmsg["content"]           # fitted tool surface
    assert sample["messages"][1]["role"] == "user"

    out2 = tmp_path / "sft2.jsonl"
    stats2 = build_sft.build(workspace=tmp_path, out=out2, keep_unknown=True,
                             min_quality=0.0, parity=False)
    assert stats2["parity_in"] == 0, stats2
    sample2 = json.loads(out2.read_text(encoding="utf-8").splitlines()[0])
    assert sample2["messages"][0]["role"] == "user"


def test_canonical_prompt_stays_in_sync_with_the_live_one(tmp_path):
    """Parity must not silently drift: the training frame keeps sharing the
    live frame's load-bearing pieces (persona, act-don't-refuse, the user's
    name) — and stays inside the box's training budget."""
    from bee.agent.context import Context, build_system_prompt, canonical_system_prompt
    from bee.config import load_config
    cfg = load_config()
    live = build_system_prompt(Context(cfg, workspace=tmp_path))
    canon = canonical_system_prompt(cfg)
    for phrase in ("You are BEE", "Act, don't refuse", cfg.user.name):
        assert phrase in live, (phrase, live[:200])
        assert phrase in canon, (phrase, canon[:200])
    assert len(canon) < 4000, f"canonical prompt too large: {len(canon)} chars"


def test_derive_prefs_builds_pairs_from_episodes(tmp_path):
    from bee.memory import ratings
    from bee.pipeline import derive_prefs
    eps = tmp_path / "episodes"
    eps.mkdir()
    t_deploy = "explain the deploy pipeline in detail"
    t_gcd = "compute the gcd of 84 and 147 carefully"
    rows = [
        # rule B: same task, verifier fail -> verifier pass
        {"task": t_deploy, "model": "local", "ok": False,
         "verify": {"verdict": "fail"}, "ts": 1,
         "output": "I could not explain that at all. " * 2},
        {"task": t_deploy, "model": "local", "ok": True,
         "verify": {"verdict": "pass"}, "ts": 2,
         "output": "The deploy pipeline runs tests then ships. " * 2},
        # rule A: the cloud golden beats the failed local run of the same task
        {"task": t_gcd, "model": "local", "ok": False,
         "verify": {"verdict": "fail"}, "ts": 3,
         "output": "The greatest common divisor here is 7. " * 2},
        {"task": "one sided success with plenty of words", "model": "local",
         "ok": True, "verify": {"verdict": "pass"}, "ts": 4,
         "output": "A clean standalone answer with enough words. " * 2},
        # plumbing on both sides must NOT pair: a sentinel is not a bad answer,
        # and an excuse is not a good one (the first real dry run offered 24
        # such "pairs"; 2026-10-17).
        {"task": "plumbing only task with enough words", "model": "cloud",
         "ok": True, "verify": {"verdict": "pass"}, "ts": 5,
         "output": "It seems like there might have been an error or misunderstanding "
                   "as no function calls were provided."},
        {"task": "plumbing only task with enough words", "model": "local",
         "ok": False, "verify": {"verdict": "fail"}, "ts": 6,
         "output": "(stopped: max iterations reached)"},
        # harness-written "failures" don't count either: an "empty answer"
        # episode's output is the loop's grounded fallback, not a model
        # attempt (measured 2026-10-17: the chrome task paired narration
        # with exactly this fallback).
        {"task": "empty answer episode with enough words", "model": "cloud",
         "ok": True, "verify": {"verdict": "pass"}, "ts": 7,
         "output": "A real answer that eventually worked. " * 2},
        {"task": "empty answer episode with enough words", "model": "local",
         "ok": False, "error": "empty answer", "verify": {"verdict": "fail"},
         "ts": 8, "output": "I could not finish this in the steps I had. " * 2},
        # a golden that is an ERROR explanation is a captured defect, not a
        # lesson: rule A must refuse it (no pass rows here, so the task labels
        # nothing rather than preferring an error text).
        {"task": "error text golden task with words", "model": "local",
         "ok": False, "verify": {"verdict": "fail"}, "ts": 9,
         "output": "I rambled about the repeated calls again. " * 2},
    ]
    (eps / "2026-01-01.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    db = tmp_path / "r.db"
    t_err = "error text golden task with words"
    goldens = {ratings.task_key(t_gcd): {
        "task": t_gcd, "response": "gcd(84, 147) = 21, lcm = 588. " * 2,
        "model": "cloud"},
        ratings.task_key(t_err): {
            "task": t_err, "model": "cloud",
            "response": "The function foo does not accept any keyword arguments."}}
    st = derive_prefs.derive(episodes_dir=eps, db=db, goldens=goldens)
    assert st["pairs"] == 2, st
    # one-sided + plumbing-only + empty-answer + error-golden tasks label nothing
    assert st["skipped_no_sides"] == 4, st
    stored = ratings.pairs(db=db)
    assert len(stored) == 2
    by_model = {p["model"]: p for p in stored}
    assert by_model["cloud"]["chosen"].startswith("gcd(84, 147)")
    assert by_model["cloud"]["rejected"].startswith("The greatest common")
    assert by_model["local"]["chosen"].startswith("The deploy pipeline")
    assert by_model["local"]["rejected"].startswith("I could not")
    # re-derivation stores nothing new (same triples -> same pair keys)
    derive_prefs.derive(episodes_dir=eps, db=db, goldens=goldens)
    assert len(ratings.pairs(db=db)) == 2


def test_derive_prefs_respects_blocklist(tmp_path):
    from bee.memory import ratings
    from bee.pipeline import derive_prefs
    eps = tmp_path / "episodes"
    eps.mkdir()
    db = tmp_path / "r.db"
    task = "a task the user disliked and blocked"
    ratings.record(task, "x", -1, db=db)
    rows = [
        {"task": task, "model": "local", "ok": False, "verify": {"verdict": "fail"},
         "ts": 1, "output": "fail text long enough to matter " * 2},
        {"task": task, "model": "local", "ok": True, "verify": {"verdict": "pass"},
         "ts": 2, "output": "good text long enough to matter " * 2},
    ]
    (eps / "2026-01-01.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    st = derive_prefs.derive(episodes_dir=eps, db=db)
    assert st["pairs"] == 0 and st["skipped_blocked"] == 1, st
    assert ratings.pairs(db=db) == []


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
