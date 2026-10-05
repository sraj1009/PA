"""sandbox_run — Docker sandbox (bee-sandbox image, GPU passthrough optional).

The sandbox mounts the BEE workspace at /workspace, so any files the sandbox
writes are immediately visible from the host tools.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import platform
from .base import envelope


@dataclass
class T:
    name: str
    description: str
    parameters: dict
    handler: object


def docker_available() -> bool:
    try:
        r = subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"],
                           capture_output=True, text=True, timeout=8)
        return r.returncode == 0
    except Exception:
        return False


def _nvidia_runtime() -> bool:
    """Does this Docker setup have the nvidia runtime (GPU passthrough)?

    Docker Desktop without the Container Toolkit reports only `runc` —
    passing --gpus there fails every run with a device-driver error.
    """
    try:
        r = subprocess.run(["docker", "info", "--format", "{{json .Runtimes}}"],
                           capture_output=True, text=True, timeout=10)
        return r.returncode == 0 and "nvidia" in (r.stdout or "")
    except Exception:
        return False


def _to_container_path(p: Path) -> str:
    """Host path as the docker CLI should receive it.

    Docker Desktop (Windows) accepts native `C:\\...` paths and bridges them
    itself; the `/mnt/c/...` form is only valid for a real WSL2-native docker.
    Passing the WSL form to Docker Desktop yields a silently-empty mount, so
    on Windows we pass the path through unchanged.
    """
    s = str(p.resolve())
    if platform.system() == "Windows":
        return s  # Docker Desktop handles the C:\... -> container bridge
    return s


def sandbox_tools():
    def h_sandbox(ctx, command: str, use_gpu: bool = False, timeout: int = 0):
        cfg = ctx.cfg.sandbox
        if not cfg.enabled:
            return {"error": "sandbox disabled in config (sandbox.enabled=false)"}
        if not docker_available():
            return {"error": "docker not reachable. Start Docker Desktop (WSL2 backend) or set sandbox.enabled=false and use shell/code_run."}
        image = cfg.image
        workdir_host = _to_container_path(ctx.workspace)
        want_gpu = bool(use_gpu or cfg.gpu)
        args = ["docker", "run", "--rm", "-i", "--init"]
        gpu_ok = want_gpu and _nvidia_runtime()
        if gpu_ok:
            args += ["--gpus", "all"]
        elif want_gpu:
            gpu_ok = "no-nvidia-runtime"  # requested but unavailable -> CPU fallback
        args += ["-v", f"{workdir_host}:{cfg.workdir}", "-w", cfg.workdir, "-e", "HF_HOME=/workspace/.hf"]
        args += [image, "/bin/sh", "-c", str(command)]
        timeout = int(timeout or cfg.timeout)
        timeout = max(1, min(timeout, 3600))
        try:
            r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
            cpu_fallback = isinstance(gpu_ok, str)
            # last resort: docker accepted --gpus but the nvidia driver failed at run time
            if r.returncode != 0 and gpu_ok is True and \
               ("nvidia" in (r.stderr or "").lower() or "device driver" in (r.stderr or "").lower()):
                stripped = []
                skip = False
                for a in args:
                    if skip:
                        skip = False
                        continue
                    if a == "--gpus":
                        skip = True
                        continue
                    stripped.append(a)
                r = subprocess.run(stripped, capture_output=True, text=True, timeout=timeout)
                cpu_fallback = True
            note = "\n[sandbox: GPU not available in this Docker setup - ran on CPU]" \
                if (want_gpu and cpu_fallback) else ""
            return envelope(command, r.returncode, (r.stdout or "") + note, r.stderr or "")
        except subprocess.TimeoutExpired:
            return envelope(command, 124, error=f"timeout after {timeout}s")
        except Exception as e:
            return envelope(command, 1, error=str(e))

    return [
        T("sandbox_run",
          "Run a command INSIDE the Docker ML sandbox (uv venv with PyTorch, scikit-learn, polars, etc.). "
          "Workspace is mounted at /workspace — files written there are visible on the host. "
          "Use for: ML/DL training & inference, GPU jobs, heavy data, destructive commands. "
          "Args: command (shell string, e.g. 'python train.py'), use_gpu (default false), timeout (s, default 300).",
          {"type": "object", "properties": {
              "command": {"type": "string"}, "use_gpu": {"type": "boolean"}, "timeout": {"type": "integer"}},
           "required": ["command"]}, h_sandbox),
    ]
