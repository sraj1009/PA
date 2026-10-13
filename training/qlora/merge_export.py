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

TEMPLATE """{{- if .Messages }}
{{- if or .System .Tools }}<|im_start|>system
{{- if .System }}
{{ .System }}
{{- end }}
{{- if .Tools }}

# Tools

You may call one or more functions to assist with the user query.

You are provided with function signatures within <tools></tools> XML tags:
<tools>
{{- range .Tools }}
{"type": "function", "function": {{ .Function }}}
{{- end }}
</tools>

For each function call, return a json object with function name and arguments within <tool_call></tool_call> XML tags:
<tool_call>
{"name": <function-name>, "arguments": <args-json-object>}
</tool_call>
{{- end }}<|im_end|>
{{ end }}
{{- range $i, $_ := .Messages }}
{{- $last := eq (len (slice $.Messages $i)) 1 -}}
{{- if eq .Role "user" }}<|im_start|>user
{{ .Content }}<|im_end|>
{{ else if eq .Role "assistant" }}<|im_start|>assistant
{{ if .Content }}{{ .Content }}
{{- else if .ToolCalls }}<tool_call>
{{ range .ToolCalls }}{"name": "{{ .Function.Name }}", "arguments": {{ .Function.Arguments }}}
{{ end }}</tool_call>
{{- end }}{{ if not $last }}<|im_end|>
{{ end }}
{{- else if eq .Role "tool" }}<|im_start|>user
<tool_response>
{{ .Content }}
</tool_response><|im_end|>
{{ end }}
{{- if and (ne .Role "assistant") $last }}<|im_start|>assistant
{{ end }}
{{- end }}
{{- else }}
{{- if .System }}<|im_start|>system
{{ .System }}<|im_end|>
{{ end }}{{ if .Prompt }}<|im_start|>user
{{ .Prompt }}<|im_end|>
{{ end }}<|im_start|>assistant
{{ end }}{{ .Response }}{{ if .Response }}<|im_end|>{{ end }}"""

SYSTEM """You are BEE, an elite executive & personal assistant: sharp, organized, proactive, direct, warm, and energetic.
- Answer directly and concisely. Begin with the answer or the action.
- No greetings, filler, or step-by-step narration. Just the result.
- Crisp and structured: short bullets; tables for comparisons; owners/deadlines where relevant.
- Be proactive: flag risks early and propose the next step.
- Errors: state what failed, why, and the exact fix. Never invent results.
- If a tool is available and the task needs it, call the tool; otherwise answer directly.
"""

PARAMETER stop "<|im_start|>"
PARAMETER stop "<|im_end|>"
PARAMETER temperature 0.2
PARAMETER num_ctx 8192
'''


def main():
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
        model = AutoModelForCausalLM.from_pretrained(
            args.base, torch_dtype=torch.bfloat16, device_map="auto", trust_remote_code=True)
        model = PeftModel.from_pretrained(model, str(args.adapter))
        model = model.merge_and_unload()
        model.save_pretrained(str(out))
        AutoTokenizer.from_pretrained(str(args.adapter), trust_remote_code=True).save_pretrained(str(out))
        print(f"merged → {out}")

    # llama.cpp conversion commands (run in a clone of ggml-org/llama.cpp)
    cmds = [
        f"python convert_hf_to_gguf.py {out} --outfile {out / 'bee4b-q4_k_m.gguf'} --outtype q4_k_m   # ~2 GB, best for 3050 4 GB",
        f"python convert_hf_to_gguf.py {out} --outfile {out / 'bee4b-q5_k_m.gguf'} --outtype q5_k_m   # ~2.5 GB, quality bump",
    ]
    (out / "convert_commands.txt").write_text("\n".join(cmds) + "\n", encoding="utf-8")

    (out / "Modelfile").write_text(
        MODFILE.replace("{gguf}", str(out / "bee4b-q4_k_m.gguf")), encoding="utf-8")
    (out / "DEPLOY.md").write_text(
        f"# Deploy BEE fine-tune to Ollama\n\n"
        f"1. llama.cpp: {cmds[0]}\n"
        f"2. ollama create bee4b-ft -f {out / 'Modelfile'}\n"
        f"3. models.yaml → fine_tunes: add name bee4b-ft, trained_on {args.adapter}\n"
        f"4. config.yaml ollama.model: bee4b-ft\n"
        f"5. GATE: python -m bee.cli eval — adopt only if score improves vs base.\n"
        f"6. Rollback: config.yaml ollama.model: qwen2.5:3b\n",
        encoding="utf-8")
    print(f"export files → {out}  (Modelfile, convert_commands.txt, DEPLOY.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
