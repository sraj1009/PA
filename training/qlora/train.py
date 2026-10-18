"""QLoRA fine-tuning of Qwen2.5-3B-Instruct for BEE — single 4 GB GPU friendly.

Data:    train/sft_v1.jsonl  (bee.pipeline.build_sft output; messages w/ loss flags)
Out:     models/<name>/  (adapter + config.json)
Hardware: RTX 3050 4 GB — 4-bit base (~1.9 GB) + LoRA (~0.2 GB) +
          grad-ckpt activations, seq <= 2048. seq 4096 OOMs on 4 GB: the
          loss's fp32 logits alone are 4096x151936x4 ~= 2.5 GB.
Time estimate (honest ranges, 3050): 10k samples ≈ 1–3 days; 2k samples ≈ 4–10 h.

Usage:
  python train.py --data ../../train/sft_v1.jsonl --out ../../models/bee-qlora-v1
  python train.py --data ... --dry-run        # validate data/config, no torch needed
  python train.py --data ... --r 32 --seq 2048 --epochs 3 --val-frac 0.1

Loss masking: only turns flagged loss=True (assistant speech + tool calls)
carry loss; user/tool-output turns are -100 (never trained on environment text).
Samples longer than --seq are SKIPPED, not truncated (a tail cut removes the
supervised answer; the count is reported before training starts).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


def load_samples(path: Path) -> list[dict]:
    out = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        try:
            row = json.loads(ln)
            msgs = row.get("messages")
            assert msgs and isinstance(msgs, list), "missing messages"
            assert all(m.get("role") in ("system", "user", "assistant", "tool") for m in msgs)
            assert any(m.get("loss") for m in msgs), "no loss=True turns"
            out.append(row)
        except Exception as e:
            print(f"  [skip] bad row: {e}")
    return out


def summarize(samples: list[dict]) -> dict:
    n = len(samples)
    n_tools = sum(len([m for m in r["messages"] if m.get("role") == "assistant" and m.get("tool_calls")])
                  for r in samples)
    n_chars = sum(len(json.dumps(r["messages"])) for r in samples)
    n_sys = sum(1 for r in samples if r["messages"] and r["messages"][0].get("role") == "system")
    return {
        "samples": n,
        "samples_with_system_prompt": n_sys,
        "tool_call_turns": n_tools,
        "approx_chars": n_chars,
        "avg_chars": round(n_chars / n) if n else 0,
        "note": f"~{n_chars // 3} training tokens (chars/3 rule of thumb)",
    }


def main():
    # Windows consoles default to cp1252: the final "done → ..." print crashed
    # with UnicodeEncodeError AFTER a successful 10-minute training run
    # (exit 1). Force UTF-8 with replace so progress output can never fail the
    # job; same fix cli.py applies to its own stdio.
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--base", default="Qwen/Qwen2.5-3B-Instruct")
    ap.add_argument("--r", type=int, default=16)
    ap.add_argument("--alpha", type=int, default=32)
    ap.add_argument("--seq", type=int, default=4096)
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--accum", type=int, default=8)
    ap.add_argument("--val-frac", type=float, default=0.1)
    ap.add_argument("--fast", action="store_true",
                    help="quick-iteration preset (3-5x faster): r=8, alpha=16, seq=2048, "
                         "epochs=1, accum=4, cap 500 samples")
    ap.add_argument("--max-samples", type=int, default=0,
                    help="train on at most N most-recent samples (0 = all)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.fast:
        args.r, args.alpha = 8, 16
        args.seq, args.epochs, args.accum = 2048, 1, 4
        args.max_samples = args.max_samples or 500
        print("FAST preset: r=8 alpha=16 seq=2048 epochs=1 accum=4 (quick, lighter adapter)")

    data = Path(args.data)
    if not data.exists():
        print(f"ERROR: dataset not found: {data}\n  build it first: python -m bee.pipeline.build_sft")
        return 1
    samples = load_samples(data)
    if args.max_samples and len(samples) > args.max_samples:
        print(f"  capping samples {len(samples)} -> {args.max_samples} (most recent)")
        samples = samples[-args.max_samples:]
    stats = summarize(samples)
    print("dataset:", json.dumps(stats, indent=1))
    if stats["samples"] < 50:
        print("WARNING: < 50 samples — QLoRA on this size will overfit; keep using BEE to collect episodes.")

    print("config:", json.dumps({k: getattr(args, k) for k in
          ("base", "r", "alpha", "seq", "epochs", "lr", "accum", "val_frac")}, indent=1))

    if args.dry_run:
        # over-seq honesty: chars/3 estimate (the real tokenizer is exact but a
        # dry run must not need torch). Over-seq samples are SKIPPED at training
        # time because truncation cuts their tail — including the answer the
        # loss should learn from.
        over = sum(1 for r in samples if len(json.dumps(r["messages"])) / 3 > args.seq)
        if over:
            print(f"  NOTE: ~{over} sample(s) likely exceed seq={args.seq} (chars/3 estimate) — "
                  "they will be skipped at training; raise --seq or rebuild the dataset.")
        print("\nDRY RUN OK — data + config valid. Remove --dry-run to train "
              "(needs training/requirements.txt installed).")
        return 0

    # ------------------------------------------------------------ real training
    try:
        import torch
        from transformers import (AutoModelForCausalLM, AutoTokenizer,
                                  DataCollatorForSeq2Seq, Trainer, TrainingArguments)
        from peft import LoraConfig, get_peft_model
        from datasets import Dataset
    except ImportError as e:
        print(f"ERROR: training deps missing ({e}).\n  pip install -r training/requirements.txt")
        return 1
    if not torch.cuda.is_available():
        print("ERROR: CUDA not visible. On the 3050 host: install the cu124 torch wheel "
              "(see training/requirements.txt). Or train inside the GPU sandbox image.")
        return 1

    # tokenizer + masked encoding (prefix-stable chat template)
    tok = AutoTokenizer.from_pretrained(args.base, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    tok.padding_side = "right"

    def encode(row):
        msgs = row["messages"]
        ids, labels, prev = [], [], 0
        for i, m in enumerate(msgs):
            text = tok.apply_chat_template(msgs[: i + 1], tokenize=False,
                                           add_generation_prompt=(i == len(msgs) - 1 and not m.get("loss")))
            cur = tok(text, add_special_tokens=False).input_ids
            new = cur[prev:]
            keep = bool(m.get("loss", m.get("role") == "assistant"))
            ids.extend(new)
            labels.extend(new if keep else [-100] * len(new))
            prev = len(cur)
        # P1: over-seq samples are SKIPPED (not tail-truncated) — truncation
        # cuts the supervised answer and silently trains on unmasked prompt
        # geometry. The caller filters on this flag and reports the count.
        return {"input_ids": ids, "labels": labels,
                "attention_mask": [1] * len(ids),
                "truncated": len(ids) > args.seq}

    enc_all = [encode(s) for s in samples]
    enc = [e for e in enc_all if not e.pop("truncated", False)]
    over = len(enc_all) - len(enc)
    if over:
        print(f"  skipped {over} sample(s) longer than seq={args.seq} "
              "(their supervised tail would have been cut)")
    if not enc:
        print("ERROR: every sample exceeds --seq. Raise --seq, drop --parity at "
              "build time, or collect shorter episodes.")
        return 1
    keep = max(1, int(len(enc) * (1 - args.val_frac)))
    train_ds = Dataset.from_dict({k: [e[k] for e in enc[:keep]] for k in enc[0]})
    val_ds = Dataset.from_dict({k: [e[k] for e in enc[keep:]] for k in enc[0]}) if keep < len(enc) else None
    print(f"encoded: {len(train_ds)} train / {0 if val_ds is None else len(val_ds)} val (seq<={args.seq})")

    model = AutoModelForCausalLM.from_pretrained(
        args.base, torch_dtype=torch.bfloat16,
        quantization_config=__import__("transformers").BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True),
        device_map="auto", trust_remote_code=True)
    lora = LoraConfig(r=args.r, lora_alpha=args.alpha, lora_dropout=0.05,
                      target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                                      "gate_proj", "up_proj", "down_proj"],
                      task_type="CAUSAL_LM")
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()

    args_out = Path(args.out)
    args_out.mkdir(parents=True, exist_ok=True)
    (args_out / "config.json").write_text(json.dumps(vars(args), indent=1, default=str), encoding="utf-8")

    # transformers>=5 dropped warmup_ratio; keep the same 5%-of-steps intent
    # with explicit steps (computed from the encoded training split).
    warmup_steps = max(5, int(0.05 * len(train_ds) * args.epochs / max(1, args.accum)))
    save_strategy = "no" if args.fast else "epoch"
    # transformers>=5 validates: load_best_model_at_end needs matching
    # save/eval strategies — with save off there is nothing to select.
    use_best = (val_ds is not None) and save_strategy != "no"
    ta = TrainingArguments(
        str(args_out),
        per_device_train_batch_size=1, gradient_accumulation_steps=args.accum,
        num_train_epochs=args.epochs, learning_rate=args.lr, lr_scheduler_type="cosine",
        warmup_steps=warmup_steps, bf16=True, gradient_checkpointing=True,
        logging_steps=10, save_strategy=save_strategy, save_total_limit=2,
        eval_strategy="epoch" if val_ds is not None else "no",
        per_device_eval_batch_size=2,
        load_best_model_at_end=use_best,
        report_to=[], seed=42, dataloader_pin_memory=True)

    # Ragged sequences need padding: the default collator stacks raw lists
    # (works only at train batch=1; eval batches crashed with
    # "expected sequence of length 349 at dim 1 (got 112)"). The seq2seq
    # collator pads inputs and labels (-100 keeps padding out of the loss).
    collator = DataCollatorForSeq2Seq(tok, padding=True, label_pad_token_id=-100)
    trainer = Trainer(model, ta, train_dataset=train_ds, eval_dataset=val_ds,
                      data_collator=collator)
    trainer.train()
    model.save_pretrained(str(args_out))
    tok.save_pretrained(str(args_out))
    print(f"\ndone → {args_out}\nnext: python merge_export.py --adapter {args.out} --base {args.base}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
