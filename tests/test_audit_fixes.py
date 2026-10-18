"""Audit-pass regressions (2026-10-08): operator switches must have effects.

Every test here pins a defect found by reading the code after the acceptance
audit claimed 543/543 green. The species were consistent: a config key or a
documented safety mechanism that no code path honoured, and an error path that
reported success.

Run:  python -m pytest tests/test_audit_fixes.py -q
"""
from __future__ import annotations

import importlib
import io
import logging
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from bee import paths
from bee.config import load_config


# ------------------------------------------------------------- config knobs
def test_computeruse_disabled_removes_the_desktop_tools(monkeypatch):
    """computeruse.enabled used to be read by nothing: setting it false still
    left the model able to call computer_input."""
    from bee import tools as tool_registry
    cfg = load_config()
    monkeypatch.setattr(cfg.computeruse, "enabled", False)
    monkeypatch.setattr("bee.config.load_config", lambda *a, **k: cfg,
                        raising=False)
    tool_registry._CACHE = None
    try:
        names = {t.name for t in tool_registry.build_default_tools()}
        assert not {n for n in names if n.startswith("computer_")}, \
            f"computeruse.enabled=false must unregister desktop control: {names}"
    finally:
        tool_registry._CACHE = None


def test_computeruse_enabled_keeps_them(monkeypatch):
    from bee import tools as tool_registry
    cfg = load_config()
    monkeypatch.setattr(cfg.computeruse, "enabled", True)
    monkeypatch.setattr("bee.config.load_config", lambda *a, **k: cfg,
                        raising=False)
    tool_registry._CACHE = None
    try:
        names = {t.name for t in tool_registry.build_default_tools()}
        assert "computer_input" in names and "computer_observe" in names
    finally:
        tool_registry._CACHE = None


def test_monitor_disabled_stops_the_metrics_stream(monkeypatch, tmp_path):
    from bee.monitor import metrics
    cfg = load_config()
    monkeypatch.setattr("bee.config.load_config", lambda *a, **k: cfg)
    monkeypatch.setattr(cfg.monitor, "enabled", False)
    monkeypatch.setattr(paths, "METRICS_DIR", tmp_path)
    monkeypatch.setattr(paths, "METRICS_FILE", tmp_path / "metrics.jsonl")
    metrics.reset_enabled_cache_for_tests(None)
    try:
        metrics.record("task", note="should-not-be-written")
        assert not (tmp_path / "metrics.jsonl").exists()
        monkeypatch.setattr(cfg.monitor, "enabled", True)
        metrics.reset_enabled_cache_for_tests(None)
        metrics.record("task", note="written")
        assert "written" in (tmp_path / "metrics.jsonl").read_text(encoding="utf-8")
    finally:
        metrics.reset_enabled_cache_for_tests(None)


def test_scheduler_disabled_pauses_persisted_system_jobs(tmp_path):
    """scheduler.enabled=false has to stop maintenance that an earlier run
    already persisted, and re-enabling must resume exactly that set."""
    from bee import scheduler
    from bee.automation.models import Job, JobTrigger
    from bee.automation.store import JobStore

    class StubWorker:
        def __init__(self, store):
            self.store = store
            self.created = []

        def create_job(self, job):
            self.created.append(job)
            self.store.save_job(job)

    cfg = load_config()
    store = JobStore(tmp_path / "automation")
    # a maintenance job left over from a previous enable
    store.save_job(Job(id="nightly_consolidate", owner="system",
                       description="memory consolidation (diary -> longterm)",
                       action={"type": "function", "fn": "bee.scheduler.consolidate"},
                       trigger=JobTrigger(kind="daily", time="03:00"),
                       enabled=True))
    user_job = Job(id="job_mine", owner="main", description="my reminder",
                   action={"type": "agent_task", "task": "x"},
                   trigger=JobTrigger(kind="one_time", at="2030-01-01T00:00:00"),
                   enabled=True)
    store.save_job(user_job)

    w = StubWorker(store)
    cfg_off = SimpleNamespace(scheduler=SimpleNamespace(enabled=False))
    scheduler._register_nightly_jobs(w, cfg_off)
    assert store.load_job("nightly_consolidate").enabled is False
    assert w.created == [], "a disabled scheduler must register no new work"
    assert store.load_job("job_mine").enabled is True, "user jobs are not ours to touch"

    w2 = StubWorker(store)
    cfg_on = load_config()          # the real shape: automation + scheduler keys
    cfg_on.scheduler.enabled = True
    scheduler._register_nightly_jobs(w2, cfg_on)
    assert store.load_job("nightly_consolidate").enabled is True
    assert store.load_job("job_mine").enabled is True, "user jobs stay untouched"
    # the pause list must cover exactly what the register path creates
    assert {j.id for j in w2.created} | {"nightly_consolidate"} == \
        set(scheduler._SYSTEM_JOB_IDS)


def test_every_system_job_fn_resolves_in_the_worker_allowlist(tmp_path):
    """The job-id parity pin above cannot see an fn string the worker cannot
    resolve: dotted names go through an explicit allowlist
    (`worker.FUNCTIONS`) and an unknown one fails the job at run time - i.e.
    at 03:00, after the fact. `recall_guard` shipped registered-but-
    unreachable exactly that way (fixed 2026-10-18); this is the class pin,
    not just the one job."""
    from bee import scheduler
    from bee.automation import worker as job_worker
    from bee.automation.store import JobStore

    class StubWorker:
        def __init__(self, store):
            self.store = store
            self.created = []

        def create_job(self, job):
            self.created.append(job)
            self.store.save_job(job)

    cfg = load_config()
    cfg.scheduler.enabled = True
    w = StubWorker(JobStore(tmp_path / "automation"))
    scheduler._register_nightly_jobs(w, cfg)
    assert w.created, "expected the nightly specs to register"
    missing = [j.id for j in w.created
               if (j.action or {}).get("type") == "function"
               and (j.action or {}).get("fn") not in job_worker.FUNCTIONS]
    assert not missing, f"unresolvable system job fn strings: {missing}"


def test_model_gate_disabled_skips_evaluation():
    from bee.evals.gate import model_quality_gate
    cfg = load_config()
    ctx = SimpleNamespace(cfg=cfg, client=None)
    cfg.model_gate.enabled = False
    cfg.model_gate.candidate = "bee-8b"
    out = model_quality_gate(ctx)
    assert out.get("skipped") and "model_gate.enabled=false" in out["skipped"]


def test_sandbox_max_output_bounds_the_tool_payload():
    """sandbox.max_output was declared and never read, so an operator lowering
    it could not protect the context window from a chatty sandbox run."""
    from bee.tools.base import MAX_CHARS, envelope
    big = "x" * (MAX_CHARS * 5)
    tight = envelope(command="ls", exit_code=0, output=big, limit=2000)
    assert len(tight["output"]) < 2500 and "truncated" in tight["output"]
    default = envelope(command="ls", exit_code=0, output=big)
    assert len(default["output"]) > len(tight["output"]), \
        "the per-tool limit must actually bind, the default must not shrink"


def test_realtime_engine_receives_barge_in_and_partial_growth():
    """voice.rt_barge_in / rt_partial_min_growth were dropped when building
    VoiceEngineCfg, so the engine always used its own defaults (and the console
    printed a hardcoded 'barge-in: ON')."""
    src = Path("bee/cli.py").read_text(encoding="utf-8")
    block = src.split("eng_cfg = VoiceEngineCfg(")[1].split(")")[0]
    assert "barge_in=vc.rt_barge_in" in block
    assert "partial_min_growth=vc.rt_partial_min_growth" in block


# ------------------------------------------------------------- error paths
def test_action_failure_keeps_the_real_exception():
    """session._with_timeout used to re-raise a STRING, which always blew up as
    'TypeError: exceptions must derive from BaseException' and buried the
    reason the desktop action failed."""
    from bee.computeruse.session import _with_timeout

    def boom():
        raise RuntimeError("could not launch 'notepad.exe'")

    with pytest.raises(RuntimeError) as exc:
        _with_timeout(boom, 5.0)
    assert "could not launch" in str(exc.value)


def test_session_observation_reports_the_true_cause():
    from bee.computeruse import ComputerAction, ComputerUseSession, MockDesktop

    md = MockDesktop()
    s = ComputerUseSession(md)
    s._dispatch = lambda a: (_ for _ in ()).throw(
        RuntimeError("no visible window matching X"))
    out = s.execute(ComputerAction(action="focus_window", target="X"))
    assert out["blocked"]
    assert "no visible window matching X" in out["error"], out["error"]
    assert "TypeError" not in out["error"]


def test_no_notifier_is_reported_as_failure_not_success(monkeypatch):
    from bee.monitor import alerts
    monkeypatch.setattr(alerts, "_run",
                        lambda *a, **k: SimpleNamespace(returncode=1, stderr=b"nope"))
    assert alerts.os_notify("BEE", "job failed") is False

    def missing(*a, **k):
        raise FileNotFoundError(2, "msg.exe not found")
    monkeypatch.setattr(alerts, "_run", missing)
    assert alerts.os_notify("BEE", "job failed") is False


# --------------------------------------------------------------- plumbing
def test_explicit_local_model_keeps_num_ctx():
    """client.py reads info['num_ctx'] with a hardcoded 8192 fallback; the
    explicit-local branch of get_llm omitted it, so config.yaml's 4096 (the
    value that keeps a 3B model fully on a 4 GB GPU) was ignored for any name
    containing a colon, including the ollama-cloud override."""
    cfg = load_config()
    cfg.ollama.num_ctx = 4096
    for name in ("qwen3:4b", "glm-5.2:cloud"):
        info = cfg.get_llm(name)
        assert info["cloud"] is False
        assert info["num_ctx"] == 4096, f"{name} lost the configured num_ctx"
    assert cfg.get_llm("local")["num_ctx"] == 4096


def test_workspace_agrees_between_paths_and_config():
    """paths.WORKSPACE used to freeze from os.environ at import — before
    load_config() read .env — splitting the tree: cfg.workspace (memory,
    automation) followed .env while plans/drafts/codeout stayed at the repo."""
    assert load_config().workspace == paths.WORKSPACE


def test_paths_reads_workspace_from_dotenv_only(monkeypatch, tmp_path):
    target = tmp_path / "elsewhere"
    (tmp_path / ".env").write_text(f"BEE_WORKSPACE={target}\n", encoding="utf-8")
    monkeypatch.delenv("BEE_WORKSPACE", raising=False)
    monkeypatch.setattr(paths, "PROJECT_ROOT", tmp_path)
    assert paths._workspace_from_env() == target.resolve()
    # process env always wins over .env
    monkeypatch.setenv("BEE_WORKSPACE", str(tmp_path / "from-env"))
    assert paths._workspace_from_env() == (tmp_path / "from-env").resolve()


def test_user_region_reaches_the_system_prompt():
    """README documents user.region as part of the 'Who I serve' block injected
    into every turn; the prompt builder only used name, timezone, interests."""
    from bee.agent.context import build_system_prompt
    cfg = load_config()
    cfg.user.name = "Boss"
    cfg.user.region = "IN"
    ctx = SimpleNamespace(cfg=cfg, name="BEE", workspace=paths.WORKSPACE,
                          model_override=None, guard_mode="cli",
                          force_skills=None, today=None, client=None)
    prompt = build_system_prompt(ctx)
    assert "region: IN" in prompt
    assert "Boss" in prompt


# ------------------------------------------------------------------ logging
def _teardown_root(saved_handlers, saved_level):
    root = logging.getLogger()
    root.handlers = saved_handlers
    root.setLevel(saved_level)
    if hasattr(root, "_bee_configured"):
        del root._bee_configured


def test_setup_logging_emits_info_diagnostics(monkeypatch):
    from bee.cli import setup_logging
    root = logging.getLogger()
    saved_handlers, saved_level = list(root.handlers), root.level
    root.handlers = []
    if hasattr(root, "_bee_configured"):
        del root._bee_configured
    monkeypatch.delenv("BEE_LOG_LEVEL", raising=False)
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stderr", buf)
    try:
        setup_logging("")
        assert root.level == logging.INFO
        assert root.handlers and root.handlers[0].stream is buf, \
            "diagnostics must go to stderr, never into the answer stream on stdout"
        logging.getLogger("bee.tts").info("why tts fell back")
        assert "why tts fell back" in buf.getvalue(), \
            "INFO diagnostics were being discarded — that is how a silent box stayed unexplained"
        n = len(root.handlers)
        setup_logging("DEBUG")
        assert len(root.handlers) == n, "setup_logging must not stack handlers"
        assert root.level == logging.DEBUG
        for noisy in ("httpx", "urllib3", "lancedb"):
            assert logging.getLogger(noisy).level >= logging.WARNING
    finally:
        _teardown_root(saved_handlers, saved_level)


def test_log_level_env_and_argument_precedence(monkeypatch):
    from bee.cli import setup_logging
    root = logging.getLogger()
    saved_handlers, saved_level = list(root.handlers), root.level
    root.handlers = []
    if hasattr(root, "_bee_configured"):
        del root._bee_configured
    try:
        monkeypatch.setenv("BEE_LOG_LEVEL", "WARNING")
        setup_logging("")
        assert root.level == logging.WARNING
        setup_logging("DEBUG")           # explicit argument beats the env
        assert root.level == logging.DEBUG
        monkeypatch.setenv("BEE_LOG_LEVEL", "nonsense")
        setup_logging("")
        assert root.level == logging.INFO, "an invalid level must not disable logging"
    finally:
        _teardown_root(saved_handlers, saved_level)


def test_windows_alert_falls_back_to_the_shell_balloon(monkeypatch):
    """msg.exe ships only with Windows Server, so on a desktop build every
    alert used to silently go nowhere — while the code still returned True."""
    from bee.monitor import alerts
    calls: list = []

    def fake_run(cmd, **kw):
        calls.append((list(cmd), kw))
        if cmd[0] == "msg":
            raise FileNotFoundError(2, "msg.exe not found")
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr(alerts, "_run", fake_run)
    monkeypatch.setattr(alerts.sys, "platform", "win32")
    assert alerts.os_notify("BEE alert", "provider failing 40%") is True
    assert calls[0][0][0] == "msg" and calls[1][0][0] == "powershell"
    script = calls[1][0][-1]
    assert "BEE alert" not in script and "provider failing" not in script, \
        "alert text must never be interpolated into a shell script"
    env = calls[1][1]["env"]
    assert env["BEE_TOAST_TITLE"] == "BEE alert"
    assert "provider failing" in env["BEE_TOAST_TEXT"]


def test_windows_alert_reports_failure_when_both_channels_fail(monkeypatch):
    from bee.monitor import alerts

    def fake_run(cmd, **kw):
        if cmd[0] == "msg":
            raise FileNotFoundError(2, "msg.exe not found")
        return SimpleNamespace(returncode=1, stderr=b"Access denied")

    monkeypatch.setattr(alerts, "_run", fake_run)
    monkeypatch.setattr(alerts.sys, "platform", "win32")
    assert alerts.os_notify("BEE alert", "disk full") is False


def test_toast_payload_is_redacted_on_every_channel(monkeypatch):
    """A locked-screen popup must not leak a card number (documented)."""
    from bee.monitor import alerts
    seen: list = []

    def fake_run(cmd, **kw):
        seen.append(kw.get("env", {}).get("BEE_TOAST_TEXT") or cmd[-1])
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr(alerts, "_run", fake_run)
    monkeypatch.setattr(alerts.sys, "platform", "win32")
    alerts.os_notify("BEE alert", "card 4111 1111 1111 1111 leaked?")
    assert seen and "4111 1111 1111 1111" not in seen[0]
