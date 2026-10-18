"""Preference tune of Qwen2.5-3B-Instruct on train/prefs.jsonl — single GPU.

Stage 2 after SFT: SFT teaches the format, preference tuning teaches the choice
(correction > original, verifier-clean > verifier-caught, cloud-success >
local-fail). QLoRA (4-bit base + LoRA) like training/qlora/train.py; pass the
SFT adapter with --adapter to continue from it.
Hardware: RTX 3050 4 GB — beta 0.1, 1 epoch, short sequences fit.

ORPO note (2026-10-17): the installed TRL 1.16 has no ORPOTrainer; ORPO's
selling point (single model, no frozen reference) is already covered here —
with a PEFT adapter, ref_model=None means "the same base weights with the
adapter disabled", so no second model is ever loaded. --loss-type stays as the
knob for TRL's unified preference losses (e.g. apo_zero) if we want to try one.

Usage:
  python training/dpo/export_prefs.py
  python training/dpo/train_dpo.py --prefs train/prefs.jsonl --out models/bee-dpo-v1 [--adapter models/bee-qlora-v1]
  python training/dpo/train_dpo.py --prefs ... --out ... --dry-run   # validate only, no torch
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_pairs(path: Path) -> list[dict]:
    out = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        try:
            row = json.loads(ln)
            assert (row.get("prompt") or "").strip(), "empty prompt"
            assert (row.get("chosen") or "").strip(), "empty chosen"
            assert (row.get("rejected") or "").strip(), "empty rejected"
            assert row["chosen"].strip() != row["rejected"].strip(), "chosen == rejected"
            out.append(row)
        except Exception as e:
            print(f"  [skip] bad pair: {e}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefs", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--base", default="Qwen/Qwen2.5-3B-Instruct")
    ap.add_argument("--adapter", default="",
                    help="SFT adapter to continue from (empty = base model)")
    ap.add_argument("--beta", type=float, default=0.1)
    ap.add_argument("--epochs", type=int, default=1)
    ap.add_argument("--lr", type=float, default=5e-5)
    ap.add_argument("--seq", type=int, default=2048)
    ap.add_argument("--loss-type", default="sigmoid",
                    help="TRL unified preference loss (sigmoid|apo_zero|...)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not Path(args.prefs).exists():
        print(f"no pairs file at {args.prefs} — run training/dpo/export_prefs.py first "
              "(and python -m bee.pipeline.derive_prefs to fill it from episodes)")
        return 2
    pairs = load_pairs(Path(args.prefs))
    by_src: dict[str, int] = {}
    for p in pairs:
        s = (p.get("source") or "unknown").strip() or "unknown"
        by_src[s] = by_src.get(s, 0) + 1
    print(f"pairs: {len(pairs)} from {args.prefs} by source: {by_src}")
    if len(pairs) < 10:
        print("need >= 10 preference pairs (automatic sources: run "
              "python -m bee.pipeline.derive_prefs; or rate + /correct answers)")
        return 2
    cfg = {"base": args.base, "adapter": args.adapter or None,
           "beta": args.beta, "epochs": args.epochs, "lr": args.lr,
           "seq": args.seq, "loss_type": args.loss_type}
    print("config: " + json.dumps(cfg, indent=1))
    if args.dry_run:
        print("DRY RUN OK — data + config valid. Remove --dry-run to train "
              "(needs CUDA torch + trl + peft: training/requirements.txt).")
        return 0
    try:
        import torch
        assert torch.cuda.is_available(), "DPO needs CUDA (this env is CPU-only)"
        from trl import DPOTrainer, DPOConfig
        import transformers
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
        from datasets import Dataset
    except Exception as e:
        print(f"cannot train here: {e}")
        return 3
    tok = transformers.AutoTokenizer.from_pretrained(args.base, use_fast=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    bnb = {"load_in_4bit": True, "bnb_4bit_quant_type": "nf4",
           "bnb_4bit_compute_dtype": torch.bfloat16, "bnb_4bit_use_double_quant": True}
    try:
        from transformers import BitsAndBytesConfig
        qconf = BitsAndBytesConfig(**bnb)
    except Exception:
        qconf = None
    model = transformers.AutoModelForCausalLM.from_pretrained(
        args.base, quantization_config=qconf, device_map="auto",
        trust_remote_code=True)
    if args.adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, args.adapter, is_trainable=True)
    else:
        model = prepare_model_for_kbit_training(model)
        model = get_peft_model(model, LoraConfig(
            r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
            task_type="CAUSAL_LM",
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                            "gate_proj", "up_proj", "down_proj"]))
    ds = Dataset.from_list([{"prompt": p["prompt"], "chosen": p["chosen"],
                             "rejected": p["rejected"]} for p in pairs])
    dconf = DPOConfig(output_dir=args.out, beta=args.beta,
                      loss_type=args.loss_type,
                      num_train_epochs=args.epochs,
                      learning_rate=args.lr, per_device_train_batch_size=1,
                      gradient_accumulation_steps=4, max_length=args.seq,
                      max_prompt_length=args.seq // 2,
                      logging_steps=10, save_steps=100, save_total_limit=2,
                      bf16=True, gradient_checkpointing=True,
                      remove_unused_columns=False)
    DPOTrainer(model=model, ref_model=None, args=dconf,
               train_dataset=ds, processing_class=tok).train()
    model.save_pretrained(args.out)
    tok.save_pretrained(args.out)
    print(f"saved DPO adapter: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
