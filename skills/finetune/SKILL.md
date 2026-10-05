# finetune

description: QLoRA fine-tuning on the 8GB 3050 — HF PEFT + Accelerate to teach the local model YOUR domain.

## When to use
The Phase-4 self-improvement loop: after collecting good (task -> success) traces, bake them into qwen3.

## How
1. Train IN THE SANDBOX with GPU (bee-sandbox:gpu image):
   ```python
   # qlora_qwen3.py — run: python qlora_qwen3.py
   import torch
   from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments, SFTTrainer
   from datasets import Dataset
   from peft import LoraConfig

   NAME = "Qwen/Qwen3-8B"
   tok = AutoTokenizer.from_pretrained(NAME); tok.pad_token = tok.eos_token
   model = AutoModelForCausalLM.from_pretrained(NAME, torch_dtype=torch.bfloat16,
                                                device_map="cpu")  # 4-bit quantization moves it to GPU in PEFT
   lora = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05,
                     target_modules=["q_proj","k_proj","v_proj","o_proj"], task_type="CAUSAL_LM")
   ds = Dataset.from_list(load_my_traces())  # [{"prompt": ..., "completion": ...}]
   args = TrainingArguments("/workspace/checkpoints/bee-qlora",
       per_device_train_batch_size=1, gradient_accumulation_steps=8,
       num_train_epochs=3, learning_rate=2e-4, bf16=True, logging_steps=10)
   SFTTrainer(model, lora, ds, args, processing_class=tok).train()
   ```
2. 8 GB VRAM math: Qwen3-8B in 4-bit ≈ 4.5 GB weights + LoRA adapters + short sequences (≤ 2048 ctx) fits; keep sequences ≤ 2048 or use gradient_checkpointing.
3. Serve the adapter with Ollama: export merged/gguf (llama.cpp) → ollama create with a Modelfile pointing at the weights; register in models.yaml fine_tunes.
4. GATE: run `python -m bee.cli eval` before AND after — adopt the fine-tune only if the score improves.

## Gotchas
- Traces: only include SUCCESSFUL runs (check evals/results.jsonl ok=true).
- Overfitting risk with < 200 examples — aim for 500+ diverse (task, solution) pairs.
- bfloat16 needs the GPU build image; the CPU baseline image can't train.
- Keep the base model as fallback — if eval regresses, delete the adapter, not the base.
