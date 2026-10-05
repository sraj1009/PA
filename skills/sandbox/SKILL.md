# sandbox

description: The Docker ML environment — when/how to use sandbox_run, GPU mode, file visibility, failure modes.

## When to use
Any ML/DL work, GPU jobs, heavy data processing, or destructive commands that shouldn't touch the host.

## How
1. sandbox_run "python script.py" — cwd is /workspace (your host workspace is mounted; files written there appear on the host).
2. GPU: sandbox_run "python train.py" use_gpu=true (needs bee-sandbox:gpu image + NVIDIA driver + docker --gpus support).
3. Install missing libs at runtime: sandbox_run "uv pip install <pkg>" (uv venv is /opt/venv).
4. Long jobs: raise timeout (max 3600s); for longer, launch with nohup and poll a log file:
   sandbox_run "nohup python train.py > /workspace/train.log 2>&1 & echo started"
   then: sandbox_run "tail -20 /workspace/train.log"
5. Verify GPU: sandbox_run "python -c 'import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"cpu\")'"

## Failure modes
- "docker not reachable" → Docker Desktop not running (WSL2 backend).
- "no shared lib" / CUDA errors → wrong image (cpu vs gpu) or driver missing.
- "timeout" → job is long; use the nohup+poll pattern.
- Files not appearing on host → they were written outside /workspace.
