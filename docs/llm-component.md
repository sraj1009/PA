# BEE LLM Component — Design & Implementation

> **Status (2026-10-08):** this is the PLAN for the optional `bee-8b` fine-tune
> route (J3 model gate). The pipeline exists (`training/qlora/`), the nightly
> quality gate exists (`bee/evals/gate.py`), and no fine-tuned model has been
> promoted yet — the active local model is stock Ollama (`qwen3:8b`).

The dedicated LLM for BEE: what it is, how it's trained on your data, what hardware it
needs, how it's deployed, monitored, and kept safe — and how it plugs into the assistant.

This is the **local brain** of the hybrid architecture. It is *one* component among many
(`docs/training-plan.md` covers the full system; this doc covers the LLM itself).

---

## 1. Architecture

```
                        BEE LLM Component (local brain)
┌─────────────────────────────────────────────────────────────────────────┐
│  Base model:    Qwen/Qwen3-8B  (tool-calling capable, 8B)               │
│  Adapter:       QLoRA  (4-bit NF4 base + LoRA r=16, bf16 compute)       │
│  Output:        GGUF q4_k_m (~5 GB) → served by Ollama as `bee-8b`      │
│  Context:       8192 (fits 3050 8 GB with room for tool schemas)        │
└─────────────────────────────────────────────────────────────────────────┘
```

- **Why Qwen3-8B**: best tool-calling per GB on an 8 GB card, native function-calling
  format that matches BEE's 30-tool schema, strong enough as an orchestrator. The
  loop's *text tool-call recovery parser* already rescues weaker 7–8B outputs (7/7 tests).
- **Why QLoRA (not full FT) at this tier**: full-precision FT of 8B needs ~100 GB
  (weights+grads+Adam states). QLoRA trains ~200 M LoRA params (~0.2 GB) on a frozen
  4-bit base — the whole thing fits the 3050 with margin. Quality for *domain adaptation*
  (your tasks, your tool discipline) is near full-FT for ≤ ~50k samples.
- **Hybrid role**: `bee-8b` is the *local* route. Hard/long tasks still escalate to the
  cloud model (`docs/training-plan.md` §1). The LLM is **one** tier — the assistant's
  reliability comes from the whole stack (deterministic tools, verifier, guard, RAG).

### VRAM budget (RTX 3050 8 GB), inference
| Item | Size |
|---|---|
| q4_k_m 8B weights | ~4.9 GB |
| KV cache @ 8192 ctx | ~0.8 GB |
| overhead / CPU offload headroom | ~2 GB |
| **Total** | **~6–7 GB — fits** |

If you ever want 16k context on this card, drop to q3_k_m or a 4B base.

---

## 2. Training / fine-tuning strategy

**Supervised fine-tuning on step-by-step reasoning trajectories** (the SFT stage of the
plan), done as QLoRA. No RL in this tier (RL needs the 8×GPU node — Phase B of the plan).

Key choices (all in `training/qlora/train.py`):
- **4-bit NF4** base, **bf16** compute, double quantization — standard QLoRA.
- **LoRA r=16, alpha=32, dropout 0.05** on q/k/v/o + gate/up/down projections.
- **Loss masking**: only *assistant* turns (its speech + its tool calls) carry loss;
  user text and tool **outputs** are `-100`. This is what makes the model learn *what to
  say/call*, not *memorize environment output*.
- **seq ≤ 4096**, batch 1 + grad-accum 8, cosine LR 1e-4, 2 epochs, early-stop on val.
- **Data = BEE's own verified episodes** (see §3) — the flywheel.

### Reproducing a run
```powershell
pip install -r training\requirements.txt          # + cu124 torch wheel (see file)
python -m bee.pipeline.build_sft                  # episodes -> train/sft_v1.jsonl
python training\qlora\train.py --data train\sft_v1.jsonl --out models\bee-qlora-v1
python training\qlora\merge_export.py --adapter models\bee-qlora-v1 --out models\bee-merged-v1
```
`train.py --dry-run` validates data+config with no GPU.

---

## 3. Data pipeline (the flywheel)

BEE logs **every** task as an *episode* (`bee/episodes/logger.py` → `train/episodes/`).
The pipeline turns episodes into training data with a verification gate:

```
episodes (JSONL)
   │
   ├─ validate.py   ── per-type verifier (math recompute, file-state recheck, exec ok)
   │                    → pass | unknown | fail        (fail NEVER trained on)
   ├─ sanitize.py   ── PII redaction (bee/privacy.py) + size bounds   (data leaves
   │                    machine only scrubbed — training plane is rented HW)
   └─ build_sft.py  ── dedupe by task, chat-format w/ loss flags → train/sft_v1.jsonl
```

```powershell
python -m bee.pipeline.build_sft            # SFT dataset
python -m bee.pipeline.train_router         # ML router (separate, sklearn)
python -m bee.pipeline.report               # train/PIPELINE_REPORT.md (flywheel health)
```

**Eligibility**: only `pass` (verified-success) episodes are SFT-eligible by default
(`--loose` adds `unknown`). This is the honesty lever — BEE only learns from what it
provably did correctly.

### Data quality controls
- **Dedup** by task (keep most recent).
- **Verification** before training (math recomputed, files re-read from disk, exec exit codes).
- **PII scrub** with redaction counts recorded in metadata + pipeline report.
- **Min-size guard**: `train.py` warns below 50 samples (overfit risk).

---

## 4. Hardware requirements

| Workload | This machine (RTX 3050 8 GB) | Needed for more |
|---|---|---|
| **Inference** (bee-8b q4, 8k ctx) | ✅ ~6–7 GB | — |
| **QLoRA SFT** (r=16, seq 4096) | ✅ ~6.5 GB | — |
| QLoRA SFT, r=32 / seq 8192 | ⚠️ tight | 12 GB+ |
| Full-precision SFT (8B) | ❌ ~100 GB | 1× 8-GPU 80 GB node |
| Reward model + RL (GRPO/PPO) | ❌ | 1× 8-GPU node |
| 32B–70B (3D parallel) | ❌ | 2–4× 8-GPU nodes |

**Time estimate (QLoRA on the 3050, honest ranges):**
~2k samples ≈ 4–10 h · ~10k samples ≈ 1–3 days. Run overnight; it's embarrassingly
single-GPU. MLflow/logging is optional (`report_to=[]` by default to stay offline).

---

## 5. Deployment

`merge_export.py` produces a ready Ollama `Modelfile` + llama.cpp conversion commands.
Deploy (with the **eval gate** — adopt only if it beats the base):

```powershell
# 1. convert (in a llama.cpp checkout)
#    see models\bee-merged-v1\convert_commands.txt
# 2. create the model
ollama create bee-8b -f models\bee-merged-v1\Modelfile
# 3. point BEE at it
#    config.yaml  →  ollama.model: bee-8b
#    models.yaml  →  fine_tunes: add entry
# 4. GATE
python -m bee.cli eval          # must be ≥ base score, else rollback
# rollback: config.yaml → ollama.model: qwen3:8b
```

Serving stays on Ollama (simplest on this card) — swap to vLLM later for throughput.
The LiteLLM gateway is unchanged: a new checkpoint is a `models.yaml`/`config.yaml`
edit, **not** a code change.

---

## 6. Monitoring

- **Runtime metrics** (`bee/monitor/metrics.py` → `metrics/metrics.jsonl`): per-task
  success, model used, iters, tools, tokens, seconds, escalation, verify verdict.
- **Dashboard** (`python -m bee.cli dashboard` / `/dashboard`): `metrics/dashboard.html`
  — KPIs, 14-day task trend, tool usage/failures, model & route breakdowns, eval history.
- **Health** (`/health` or `python -m bee.cli health`): Ollama/models/cloud/docker/voice/
  disk + 7-day activity summary.
- **Eval history** (`evals/results.jsonl`): every eval run appended — this is the trend
  line that tells you whether a new checkpoint is an improvement.

To watch a new checkpoint: run it in **shadow** — point a second Ollama model at it,
route `cloud:`-tagged or sampled tasks to it, and compare `results.jsonl` before cutover.

---

## 7. Safety

- **Constitution** (`docs/training-plan.md` §3, principle list) is the spec the model is
  steered toward; the **runtime constitution checker** (`bee/brain/verifier.py`) enforces
  a deterministic subset *every turn* (math recompute, file-state, URL cross-check) with a
  bounded fix round.
- **Guard** (`bee/guard.py`): destructive/external commands hit allow|ask|deny gates
  *before* execution — the LLM cannot bypass them.
- **Privacy** (`bee/privacy.py`): PII redaction on any cloud-bound payload; the local
  model is the privacy floor and is never redacted.
- **Data**: training data is PII-scrubbed before it could leave the machine; only
  verified-success episodes are used; min-size guard prevents overfit junk.
- **Rollback**: previous checkpoint + base always retained; the eval gate blocks a
  regression from shipping.

---

## 8. Integration with the assistant

The LLM is **plugged in through the router** — it doesn't own control flow:

```
task → router (explicit > deterministic > ML > heuristic)
         ├─ "det"     → calculator (no LLM)
         ├─ "local"   → bee-8b  ← THIS component
         └─ "cloud"   → frontier model (escalation)
      → ReAct loop (22 tools, guard, RAG context)
      → verifier (claim checks, 1 bounded fix)
      → episode logger (feeds §3 next cycle)
```

So "improving the LLM" and "improving the assistant" are separate dials: the assistant
gets safer/more capable from the guard/verifier/RAG/tools *regardless* of which model
serves, and the model gets better from the data flywheel. That separation is the whole
point of the hybrid design.
