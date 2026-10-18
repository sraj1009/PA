"""SFT data pipeline: quality scoring, cloud-teacher paraphrase augmentation,
and min-quality filtering. All offline (loaders + generator are stubbed)."""
import json
from pathlib import Path

from bee.pipeline import build_sft


def test_quality_score_bounds_and_ordering():
    good = {"task": "write a detailed report on renewable energy trends in 2026 with sources",
            "output": "Here is a comprehensive report...\n" + "x" * 500, "ok": True, "events": []}
    bad = {"task": "hi", "output": "error: failed to do the thing", "ok": True, "events": []}
    g, b = build_sft.quality_score(good), build_sft.quality_score(bad)
    assert 0.0 <= g <= 1.0 and 0.0 <= b <= 1.0
    assert g > b


def test_paraphrase_keeps_same_response_drops_original():
    rows = [{"task": "summarize this article about AI", "output": "Summary: ...",
             "ok": True, "events": [], "model": "cloud"}]

    def gen(task):
        return ["give the gist of the AI piece", "briefly explain the AI article", task]

    aug = build_sft.paraphrase_augment(rows, 3, gen)
    tasks = {r["task"] for r in aug}
    assert "give the gist of the AI piece" in tasks
    assert "briefly explain the AI article" in tasks
    assert "summarize this article about AI" not in tasks  # original not a new variant
    assert all(r["output"] == "Summary: ..." for r in aug)  # same verified answer
    assert all(r["augmented"] is True for r in aug)


def test_paraphrase_skips_tool_call_rows():
    rows = [{"task": "open chrome", "output": "ok", "ok": True,
             "events": [{"tool": "shell", "args": "{}", "result": "x"}], "model": "cloud"}]
    # Tool-calling rows must NOT be paraphrased (the tool args would go stale).
    assert build_sft.paraphrase_augment(rows, 2, lambda t: ["variant a", "variant b"]) == []


def test_build_min_quality_filters(tmp_path, monkeypatch):
    monkeypatch.setattr(build_sft, "load_episodes", lambda: [])
    monkeypatch.setattr(build_sft, "load_golden", lambda: [
        {"task": "a very detailed request that needs a thorough answer with many steps",
         "response": "A complete, well-structured response with enough substance here. " * 5,
         "model": "cloud", "ts": "2026-01-01"},
        {"task": "hi", "response": "error: could not do it", "model": "cloud", "ts": "2026-01-01"},
    ])
    out = tmp_path / "sft.jsonl"
    all_stats = build_sft.build(out=out, min_quality=0.0)
    assert all_stats["samples_out"] == 2
    filt = build_sft.build(out=out, min_quality=0.6)
    assert filt["samples_out"] == 1            # only the good sample survives
    assert filt["dropped_low_quality"] == 1
    # every emitted sample carries a quality score in its metadata
    for line in out.read_text(encoding="utf-8").splitlines():
        md = json.loads(line)["metadata"]
        assert "quality" in md and 0.0 <= md["quality"] <= 1.0


def test_failed_or_blocked_tool_calls_are_not_trained(monkeypatch, tmp_path):
    """A guard-blocked or broken tool call must not become the desired behaviour in
    the SFT dataset — A60b. The episode recovers, so validate passes, but the bad
    event is still dropped by the message builder."""
    bad_row = {
        "task": "do the thing", "output": "done", "ok": True, "events": [
            {"tool": "shell", "args": "{}", "ok": True, "result": "ok output"},
            {"tool": "shell", "args": "{}", "ok": False,
             "result": "{\"blocked\": true, \"reason\": \"guard\"}"},
            {"tool": "shell", "args": "{}", "ok": True, "result": "recovered output"},
        ], "model": "local", "date": "2026-10-13",
    }
    monkeypatch.setattr(build_sft, "load_episodes", lambda: [bad_row])
    monkeypatch.setattr(build_sft, "load_golden", lambda: [])
    out = tmp_path / "sft.jsonl"
    stats = build_sft.build(out=out)
    assert stats["dropped_bad_events"] == 1
    sample = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
    tool_contents = [m.get("content") for m in sample["messages"] if m["role"] == "tool"]
    assert "ok output" in tool_contents
    assert "recovered output" in tool_contents
    assert "{\"blocked\": true" not in str(tool_contents)


def test_tool_messages_carry_matching_tool_call_ids(monkeypatch, tmp_path):
    row = {"task": "t", "output": "ok", "ok": True, "events": [
        {"tool": "shell", "args": "{}", "ok": True, "result": "r1"},
    ], "model": "local", "date": "2026-10-13"}
    monkeypatch.setattr(build_sft, "load_episodes", lambda: [row])
    monkeypatch.setattr(build_sft, "load_golden", lambda: [])
    out = tmp_path / "sft.jsonl"
    build_sft.build(out=out)
    sample = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
    assistant = [m for m in sample["messages"] if m["role"] == "assistant" and m.get("tool_calls")][0]
    tool = [m for m in sample["messages"] if m["role"] == "tool"][0]
    assert assistant["tool_calls"][0]["id"] == tool["tool_call_id"]


def test_a_cloud_golden_is_trained_on_its_real_task_not_its_dedupe_key(tmp_path, monkeypatch):
    """A63: the 2026-10-13 dedupe rewrite hashed the task and then stored the HASH
    as the sample's `task`, so every golden was emitted as
    `"75f0ed01688fcd2ef604634568edc8d6" -> the answer`. Measured on this machine
    with HEAD's builder over the real 208-row corpus: 9 samples out, **9 of 9 with a
    32-char hex digest as the user message** — one nightly `maybe_build_sft` away
    from teaching the model to answer a key instead of a question."""
    import re
    monkeypatch.setattr(build_sft, "load_episodes", lambda: [])
    monkeypatch.setattr(build_sft, "load_golden", lambda: [
        {"task": "explain photosynthesis", "response": "Plants turn light into food.",
         "model": "cloud", "ts": "2026-10-13T12:00:00"}])
    out = tmp_path / "sft.jsonl"
    stats = build_sft.build(out=out)
    assert stats["golden_in"] == 1
    sample = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
    # P1 parity: messages[0] is the canonical system prompt (loss=False);
    # the trained-on prompt is the first user message.
    assert sample["messages"][0]["role"] == "system"
    assert sample["messages"][0]["loss"] is False
    prompt = next(m["content"] for m in sample["messages"] if m["role"] == "user")
    assert prompt == "explain photosynthesis"
    assert not re.fullmatch(r"[0-9a-f]{32}", prompt), prompt
    assert sample["messages"][-1]["content"] == "Plants turn light into food."
    assert sample["metadata"]["date"] == "2026-10-13"


def test_nightly_qlora_trigger_opts_out_by_default():
    """A multi-hour GPU burn must never start by surprise: with the default
    config the trigger reports why it skips and runs nothing."""
    import types
    from bee.config import load_config
    from bee import scheduler
    cfg = load_config()
    assert cfg.training.auto_qlora is False
    ctx = types.SimpleNamespace(cfg=cfg, workspace=cfg.workspace)
    out = scheduler.maybe_train_qlora(ctx)
    assert "skipped" in out and "auto_qlora" in out["skipped"], out


def test_auto_chain_stops_cleanly_without_llama_cpp(tmp_path, monkeypatch):
    """P0-5: a successful training run is merged; without an unpacked
    llama.cpp the chain reports the exact remedy and queues NOTHING — the
    gate must never be pointed at a half-built artifact."""
    import subprocess
    from types import SimpleNamespace
    from bee import paths, scheduler
    from bee.evals import gate

    monkeypatch.setattr(paths, "PROJECT_ROOT", tmp_path)
    adapter = tmp_path / "models" / "bee-qlora-20261017"
    adapter.mkdir(parents=True)
    (adapter / "adapter_config.json").write_text("{}", encoding="utf-8")
    queued = tmp_path / "train" / "gate_candidate.json"
    monkeypatch.setattr(gate, "GATE_CANDIDATE_FILE", queued)

    def fake_run(cmd, **kw):
        cmd = [str(c) for c in cmd]
        if "merge_export.py" in " ".join(cmd):
            out = Path(cmd[cmd.index("--out") + 1])
            out.mkdir(parents=True, exist_ok=True)
            (out / "Modelfile").write_text("FROM x\n", encoding="utf-8")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    cfg = SimpleNamespace(training=SimpleNamespace(llama_cpp_dir=""))
    out = scheduler._auto_chain(SimpleNamespace(cfg=cfg), adapter,
                                tmp_path / "train" / "qlora.log")
    assert "llama_cpp_dir" in out.get("note", "") and not out.get("queued"), out
    assert not queued.exists()
    assert (tmp_path / "models" / "bee-merged-20261017" / "Modelfile").exists()


def test_auto_chain_imports_and_queues_the_model(tmp_path, monkeypatch):
    """The full P0-5 chain: merge -> f16 GGUF -> Q4_K_M -> `ollama create` ->
    gate queue. The queue write is the LAST step (only a fully imported model
    is ever queued)."""
    import subprocess
    from types import SimpleNamespace
    from bee import paths, scheduler
    from bee.evals import gate

    monkeypatch.setattr(paths, "PROJECT_ROOT", tmp_path)
    adapter = tmp_path / "models" / "bee-qlora-20261017"
    adapter.mkdir(parents=True)
    llama = tmp_path / "llamacpp"
    llama.mkdir()
    (llama / "convert_hf_to_gguf.py").write_text("# stub\n", encoding="utf-8")
    (llama / "llama-quantize.exe").write_text("", encoding="utf-8")
    queued = tmp_path / "train" / "gate_candidate.json"
    monkeypatch.setattr(gate, "GATE_CANDIDATE_FILE", queued)
    seen: list[list[str]] = []

    def fake_run(cmd, **kw):
        cmd = [str(c) for c in cmd]
        seen.append(cmd)
        joined = " ".join(cmd)
        if "merge_export.py" in joined:
            out = Path(cmd[cmd.index("--out") + 1])
            out.mkdir(parents=True, exist_ok=True)
            (out / "Modelfile").write_text("FROM q4\n", encoding="utf-8")
        elif "convert_hf_to_gguf.py" in joined:
            Path(cmd[cmd.index("--outfile") + 1]).write_text("f16", encoding="utf-8")
        elif "llama-quantize" in joined:
            Path(cmd[2]).write_text("q4", encoding="utf-8")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    cfg = SimpleNamespace(training=SimpleNamespace(llama_cpp_dir=str(llama)))
    out = scheduler._auto_chain(SimpleNamespace(cfg=cfg), adapter,
                                tmp_path / "train" / "qlora.log")
    assert out.get("queued") and out["model"] == "bee-qlora-20261017", out
    data = json.loads(queued.read_text(encoding="utf-8"))
    assert data["model"] == "bee-qlora-20261017" and data["src"] == "auto-chain"
    kinds = ["merge" if "merge_export.py" in " ".join(c) else
             "convert" if "convert_hf_to_gguf.py" in " ".join(c) else
             "quantize" if "llama-quantize" in " ".join(c) else
             "ollama" if "create" in c else "?" for c in seen]
    assert kinds == ["merge", "convert", "quantize", "ollama"], kinds


def test_nightly_build_uses_loose_plus_quality(tmp_path, monkeypatch):
    """The nightly dataset must not starve: unknown-verdict episodes with a
    substantive output are included above the quality floor, while fail
    verdicts are still never trained on."""
    from bee.pipeline import build_sft
    good_unknown = {
        "task": "explain in detail how photosynthesis works in desert plants",
        "output": "Desert plants use CAM photosynthesis. " * 20,
        "ok": True, "events": [], "model": "cloud"}
    failed = {"task": "do the thing", "output": "error: broke",
              "ok": False, "events": [], "model": "local"}
    monkeypatch.setattr(build_sft, "load_episodes", lambda: [good_unknown, failed])
    monkeypatch.setattr(build_sft, "load_golden", lambda: [])
    out = tmp_path / "sft.jsonl"
    stats = build_sft.build(out=out, keep_unknown=True, min_quality=0.6)
    assert stats["samples_out"] == 1, stats
    assert stats["by_verdict"].get("fail", 0) == 1
