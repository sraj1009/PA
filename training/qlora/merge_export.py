"""Merge the LoRA adapter into the base model and export for local serving.

Steps:
  1. merge (needs torch + base weights):  merged HF model
  2. print the exact llama.cpp conversion commands (run where llama.cpp is)
  3. write an Ollama Modelfile ready for `ollama create bee4b-ft -f Modelfile`

Usage:
  python merge_export.py --adapter ../../models/bee-qlora-v1 \
                         --base Qwen/Qwen2.5-3B-Instruct --out ../../models/bee-merged-v1
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MODFILE = r'''FROM {gguf}

# Deliberately NO TEMPLATE directive: the GGUF embeds tokenizer.chat_template
# from tokenizer_config.json — the same Jinja template the SFT data was
# rendered with. An explicit Modelfile TEMPLATE would OVERRIDE it and drift
# from the training distribution (verified 2026-10-17: FROM-gguf + no
# TEMPLATE keeps tool-calling intact; see models/bee4b-v2.Modelfile).

SYSTEM """You are BEE, an elite executive & personal assistant: sharp, organized, proactive, direct, warm, and energetic.
- Answer directly and concisely. Begin with the answer or the action.
- No greetings, filler, or step-by-step narration. Just the result.
- Crisp and structured: short bullets; tables for comparisons; owners/deadlines where relevant.
- Be proactive: flag risks early and propose the next step.
- Errors: state what failed, why, and the exact fix. Never invent results.
- If a tool is available and the task needs it, call the tool; otherwise answer directly.
"""

# Speed-tuned for a 3B model on a 4 GB GPU: whole model + KV cache on-GPU
# (same parameters as the production bee4b.Modelfile).
PARAMETER num_ctx 4096
PARAMETER temperature 0.2
PARAMETER num_predict 1024
PARAMETER repeat_penalty 1.15
'''


def main():
    # cp1252 consoles: the "merged → ..." prints killed a successful merge
    # with UnicodeEncodeError at exit; force UTF-8 like train.py does.
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--base", default="Qwen/Qwen2.5-3B-Instruct")
    ap.add_argument("--out", required=True)
    ap.add_argument("--skip-merge", action="store_true",
                    help="only write the Modelfile + commands (no torch needed)")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    if not args.skip_merge:
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
            from peft import PeftModel
        except ImportError as e:
            print(f"ERROR: deps missing ({e}) — pip install -r training/requirements.txt "
                  f"or use --skip-merge to only generate export files.")
            return 1
        print(f"loading base {args.base} (bf16) + adapter {args.adapter} ...")
        # Plain load, deliberately NO device_map="auto": accelerate's dispatch
        # installs offload hooks that break PEFT's merge_and_unload on this
        # adapter (KeyError: 'base_model.model.model.embed_tokens.weight' in
        # accelerate/utils/offload.py). A one-off export fits in CPU RAM
        # (~6 GB bf16) and merging on CPU is deterministic on a 4 GB GPU box.
        model = AutoModelForCausalLM.from_pretrained(
            args.base, torch_dtype=torch.bfloat16, trust_remote_code=True)
        model = PeftModel.from_pretrained(model, str(args.adapter))
        model = model.merge_and_unload()
        model.save_pretrained(str(out))
        AutoTokenizer.from_pretrained(str(args.adapter), trust_remote_code=True).save_pretrained(str(out))
        print(f"merged → {out}")

    # llama.cpp export recipe (verified 2026-10-17 on llama.cpp b11711).
    # Current convert_hf_to_gguf.py --outtype accepts ONLY
    # {f32,f16,bf16,q8_0,tq1_0,tq2_0,auto} — Q4_K_M comes from a second
    # llama-quantize step (Windows binaries:
    # llama-<build>-bin-win-cpu-x64.zip from ggml-org/llama.cpp releases).
    f16 = out / "bee4b-f16.gguf"
    q4 = out / "bee4b-q4_k_m.gguf"
    cmds = [
        f"python convert_hf_to_gguf.py {out} --outfile {f16} --outtype f16",
        f"llama-quantize.exe {f16} {q4} Q4_K_M   # ~1.9 GB, fits the 3050 4 GB fully on-GPU",
    ]
    (out / "convert_commands.txt").write_text("\n".join(cmds) + "\n", encoding="utf-8")

    (out / "Modelfile").write_text(
        MODFILE.replace("{gguf}", q4.as_posix()), encoding="utf-8")
    (out / "DEPLOY.md").write_text(
        f"# Deploy BEE fine-tune to Ollama\n\n"
        f"1. convert to f16 GGUF:  {cmds[0]}\n"
        f"2. quantize to Q4_K_M:   {cmds[1]}\n"
        f"3. ollama create <name> -f {out / 'Modelfile'}   (FROM points at {q4.name})\n"
        f"4. models.yaml -> fine_tunes: add name <name>, trained_on {args.adapter}\n"
        f"5. config.yaml model_gate.candidate: <name>, then run /gate — the J3\n"
        f"   gate adopts the model only on an eval win (writes models.yaml local_model)\n"
        f"6. Rollback: remove `local_model` from models.yaml (config.yaml wins again)\n",
        encoding="utf-8")
    print(f"export files → {out}  (Modelfile, convert_commands.txt, DEPLOY.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
