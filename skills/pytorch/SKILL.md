# pytorch

description: PyTorch training/inference on the 8GB RTX 3050 — models, DataLoaders, GPU discipline, VRAM budgeting.

## When to use
Building/training/evaluating neural nets, fine-tuning, inference scripts.

## How
1. All torch work runs in the sandbox: sandbox_run "python train.py" (use_gpu=true). The workspace is mounted at /workspace.
2. VRAM budget on 8 GB: model params + optimizer state (Adam = 2x params in fp32 master) + activations. Rule of thumb: fp32 fine-tune of ≤ 7B is impossible without offload; use QLoRA (see finetune skill) or ≤ 1.5B dense.
3. Standard training skeleton:
   ```python
   import torch
   assert torch.cuda.is_available(), "GPU not visible in sandbox"
   dev = "cuda"
   model.to(dev)
   opt = torch.optim.AdamW(model.parameters(), lr=1e-4, weight_decay=0.01)
   for batch in loader:  # batch_size: start small (8-16), grad_accum=4-8
       loss = model(...).loss
       (loss / grad_accum).backward()
       if (step+1) % grad_accum == 0: opt.step(); opt.zero_grad()
   ```
4. Determinism: torch.manual_seed(42); set cudnn.deterministic=True for reproducible runs.
5. Track experiments: mlflow (in sandbox) — mlflow.set_experiment("bee"); log params/metrics.

## Gotchas
- CUDA OOM: halve batch size first, then gradient_checkpointing=True, then mixed precision (torch.cuda.amp autocast + GradScaler).
- CPU torch is installed by default; GPU variant needs the Dockerfile.gpu build.
- Save checkpoints to /workspace/checkpoints/ so they're visible on the host.
- Long training: run in background and poll (sandbox timeout is capped at 3600s).
