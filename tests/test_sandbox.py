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
