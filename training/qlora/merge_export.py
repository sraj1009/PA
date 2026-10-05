"""Merge the LoRA adapter into the base model and export for local serving.

Steps:
  1. merge (needs torch + base weights):  merged HF model
  2. print the exact llama.cpp conversion commands (run where llama.cpp is)
  3. write an Ollama Modelfile ready for `ollama create bee-8b -f Modelfile`

Usage:
  python merge_export.py --adapter ../../models/bee-qlora-v1 \
                         --base Qwen/Qwen3-8B --out ../../models/bee-merged-v1
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_TEMPLATE = json.dumps("{% if .System %}{% .System %}{% end %}{% if .Prompt %}{% .Prompt %}{% end %}").replace("{%", "{{").replace("%}", "}}")
MODFILE = f"""FROM {{gguf}}

TEMPLATE {_TEMPLATE}

PARAMETER stop \"<|im_start|>\"
PARAMETER stop \"<|im_end|>\"
PARAMETER temperature 0.2
PARAMETER num_ctx 8192

SYSTEM \"You are BEE, a local-first, tool-using personal assistant. Use the provided tools to complete tasks; verify outputs; be concise.\"
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--base", default="Qwen/Qwen3-8B")
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
        model = AutoModelForCausalLM.from_pretrained(
            args.base, torch_dtype=torch.bfloat16, device_map="auto", trust_remote_code=True)
        model = PeftModel.from_pretrained(model, str(args.adapter))
        model = model.merge_and_unload()
        model.save_pretrained(str(out))
        AutoTokenizer.from_pretrained(str(args.adapter), trust_remote_code=True).save_pretrained(str(out))
        print(f"merged → {out}")

    # llama.cpp conversion commands (run in a clone of ggml-org/llama.cpp)
    cmds = [
        # f"python convert_hf_to_gguf.py {out} --outfile {out / 'bee-8b-f16.gguf'} --outtype f16",
        f"python convert_hf_to_gguf.py {out} --outfile {out / 'bee-8b-q4_k_m.gguf'} --outtype q4_k_m   # ~5 GB, best for 3050",
        f"python convert_hf_to_gguf.py {out} --outfile {out / 'bee-8b-q5_k_m.gguf'} --outtype q5_k_m   # ~6 GB, quality bump",
    ]
    (out / "convert_commands.txt").write_text("\n".join(cmds) + "\n", encoding="utf-8")

    (out / "Modelfile").write_text(
        MODFILE.replace("{gguf}", str(out / "bee-8b-q4_k_m.gguf")), encoding="utf-8")
    (out / "DEPLOY.md").write_text(
        f"# Deploy BEE fine-tune to Ollama\n\n"
        f"1. llama.cpp: {cmds[0]}\n"
        f"2. ollama create bee-8b -f {out / 'Modelfile'}\n"
        f"3. models.yaml → fine_tunes: add name bee-8b, trained_on {args.adapter}\n"
        f"4. config.yaml ollama.model: bee-8b\n"
        f"5. GATE: python -m bee.cli eval — adopt only if score improves vs base.\n"
        f"6. Rollback: config.yaml ollama.model: {args.base.split('/')[-1]}:8b\n",
        encoding="utf-8")
    print(f"export files → {out}  (Modelfile, convert_commands.txt, DEPLOY.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
