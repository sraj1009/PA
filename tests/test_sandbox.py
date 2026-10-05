"""GPU fallback tests for the Docker sandbox tool (no docker calls are made —
subprocess.run is stubbed and the argv is inspected)."""
from __future__ import annotations

import types
from pathlib import Path

import pytest

from bee.config import load_config
from bee.tools import sandbox as sb


class R:
    def __init__(self, returncode=0, stdout="ok\n", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _ctx(gpu=True):
    cfg = load_config()
    cfg.sandbox.gpu = gpu
    return types.SimpleNamespace(cfg=cfg, workspace=Path("C:/tmp/bee-test-ws"))


def _track_run_calls(monkeypatch, calls, responses=()):
    """Stub subprocess.run: track only `docker run` argv; probes get plain success."""
    def fake_run(args, **k):
        if len(args) > 1 and args[1] == "run":
            calls.append(list(args))
            if len(calls) - 1 < len(responses):
                return responses[len(calls) - 1]
            return R()
        return R()
    monkeypatch.setattr(sb.subprocess, "run", fake_run)


def test_no_gpus_flag_without_nvidia_runtime(monkeypatch):
    monkeypatch.setattr(sb, "_nvidia_runtime", lambda: False)
    calls = []
    _track_run_calls(monkeypatch, calls)
    out = sb.sandbox_tools()[0].handler(_ctx(gpu=True), command="echo hi")
    assert calls and "--gpus" not in calls[0]
    assert "GPU not available" in str(out)


def test_gpus_flag_with_nvidia_runtime(monkeypatch):
    monkeypatch.setattr(sb, "_nvidia_runtime", lambda: True)
    calls = []
    _track_run_calls(monkeypatch, calls)
    sb.sandbox_tools()[0].handler(_ctx(gpu=True), command="echo hi")
    assert calls and "--gpus" in calls[0] and "all" in calls[0]


def test_retry_without_gpus_on_runtime_nvidia_error(monkeypatch):
    monkeypatch.setattr(sb, "_nvidia_runtime", lambda: True)  # probe says yes...
    calls = []
    first_fail = R(returncode=125,
                   stderr='could not select device driver "nvidia" with capabilities: [[gpu]]')
    _track_run_calls(monkeypatch, calls, responses=[first_fail])  # ...but driver fails at runtime
    out = sb.sandbox_tools()[0].handler(_ctx(gpu=True), command="echo hi")
    assert len(calls) == 2
    assert "--gpus" in calls[0] and "--gpus" not in calls[1]
    assert "ok" in str(out)


def test_hardening_flags_on_default_config(monkeypatch):
    """Phase 1: untrusted code must run with the full container boundary."""
    monkeypatch.setattr(sb, "_nvidia_runtime", lambda: False)
    calls = []
    _track_run_calls(monkeypatch, calls)
    sb.sandbox_tools()[0].handler(_ctx(gpu=False), command="echo hi")
    assert calls, "docker run was not invoked"
    a = calls[0]

    def after(flag):
        return a.index(flag) + 1 if flag in a else -1

    # network isolation
    assert a[after("--network")] == "none"
    # resource caps
    assert a[after("--memory")] == "2g"
    assert a[after("--memory-swap")] == "2g"
    assert a[after("--cpus")] == "2"
    assert a[after("--pids-limit")] == "128"
    # capability reduction
    assert a[after("--cap-drop")] == "ALL"
    assert a[after("--security-opt")] == "no-new-privileges"
    # read-only root FS + bounded /tmp
    assert "--read-only" in a
    tmpfs = a[after("--tmpfs")]
    assert tmpfs.startswith("/tmp:") and "noexec" in tmpfs and "size=256m" in tmpfs
    # non-root execution
    assert a[after("--user")] == "1000:1000"
    # the explicit workspace grant is still present
    assert "-v" in a and "-w" in a and a[after("-w")] == "/workspace"
    # host .env is masked (read-only empty file bound over it) so untrusted
    # code cannot read credentials
    env_masks = [a[i + 1] for i, x in enumerate(a)
                 if x == "-v" and a[i + 1].endswith(":/workspace/.env:ro")]
    assert env_masks, "host .env is not masked in the sandbox"


def test_hardening_can_be_relaxed_per_config(monkeypatch):
    """Operator knobs: disable read-only + run as image default user (old root
    image fallback). Everything else stays hardened."""
    monkeypatch.setattr(sb, "_nvidia_runtime", lambda: False)
    cfg = load_config()
    cfg.sandbox.read_only_root = False
    cfg.sandbox.user = ""
    calls = []
    _track_run_calls(monkeypatch, calls)
    sb.sandbox_tools()[0].handler(types.SimpleNamespace(cfg=cfg, workspace=Path("C:/tmp/bee-test-ws")),
                                  command="echo hi")
    a = calls[0]
    assert "--read-only" not in a and "--user" not in a
    assert a[a.index("--network") + 1] == "none"   # network stays off
    assert "--cap-drop" in a                        # caps stay dropped
