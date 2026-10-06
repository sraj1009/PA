# BEE — Verification Report (Phase 4)

- Generated: 2026-10-06 17:24 
- Machine: RTX 3050 8GB / Windows / Ollama `bee4b`
- Cloud tier: configured (gemini/gemini-3.6-flash) — credentialed
- Seed: 20261004

## Methodology

Every deterministic subsystem is checked against an **independent reference**
(CPython arithmetic, brute-force/alternative algorithms, labeled synthetic
samples). Each suite reports the Wilson 95% confidence interval on its pass
rate. Sample sizes are chosen so a **perfect** run on any suite with n ≥ ~3,900
has a lower bound of at least **99.9%** — that is the strongest accuracy claim
this report can make, and only for deterministic components.

LLM behaviour (tool use, answer quality, routing of open-ended tasks) is a
stochastic system; it is measured in the `/eval` agent suite and the model
benchmark below, and is **not** covered by the 99.9% claim.

## Deterministic suites

| Suite | n | passed | accuracy | 95% CI lower | n suffices for 99.9% LB | status |
|---|---:|---:|---:|---:|:---:|:---:|
| math | 10,000 | 10,000 | 100.000% | 99.962% | yes | **PASS** |
| dsa | 38,456 | 38,456 | 100.000% | 99.990% | yes | **PASS** |
| pii | 13,200 | 13,200 | 100.000% | 99.971% | yes | **PASS** |
| guard | 4,204 | 4,204 | 100.000% | 99.909% | yes | **PASS** |
| router | 6,000 | 6,000 | 100.000% | 99.936% | yes | **PASS** |
| rag | 54 | 54 | 100.000% | 93.359% | no (small-n) | **PASS** |

Notes per suite:

- **math**: integer expressions incl. precedence, parens, unary minus, //, %, **
- **dsa**: sorts/DP/graphs/DS vs independent references + property checks
- **pii**: recall on labeled PII; precision on clean negatives (Luhn-aware)
- **guard**: allow/ask/deny on parameterized shell commands
- **router**: tiers locked (ML off); cloud configured=True
- **rag**: keyword recall@5 over synthetic memory + auto-context triggers

## LLM behaviour (measured — not a 99.9% claim)

- Local generation: 4.6 tok/s mean, 56112.8 ms mean per 256-token completion (n=5) — `evals/bench_model.json`
- Local embeddings: 757.9 ms mean, p50 499.1 ms (n=5)

> Throughput is measured on this box with `num_ctx=8192` pinned in the
> client (the model default of 40,960 builds a ~6 GB KV cache that alone
> prevents a full GPU fit). Findings from `ollama ps` (PROCESSOR column):
> - 40,960 ctx: model footprint 11 GB → 80%/20% CPU/GPU → 4.6 tok/s
> - 8,192 ctx: model footprint 6.6 GB → 66%/34% CPU/GPU → 4.6 tok/s
> Ollama only moves a model fully onto the GPU when the WHOLE load
> (weights + KV + CUDA context) fits the VRAM estimate; on this 8 GB
> card the 8B model sits on the boundary, so a partial offload (which
> does not speed up generation — the CPU layers remain the bottleneck)
> is the best achievable for qwen3:8b here. Full-GPU speed (~15-25 tok/s)
> would come from a ≤4B model, a bigger card, or ~12 GB VRAM.
> Latency is the only thing affected; correctness is unaffected.

- Agent eval suite (latest run 2026-10-06T17:24:20): **8/21** tasks passed.
  failing: math_sieve, file_roundtrip, calculator, verify_calc_pass, file_list_ws, dsa_lis, dsa_gcd_lcm, dsa_sort_check, dsa_graph, memory_write, memory_read, plan_complex

## What this report does and does not guarantee

1. **Guaranteed (deterministic, CI-quantified):** expression evaluation, DSA
   library correctness, PII redaction behaviour, guard classification, routing
   tier logic, keyword recall — as long as these modules are unmodified; any
   change must re-run this suite (it is the gate for model/prompt/skill changes).
2. **Measured, stochastic:** LLM answer quality, tool-call reliability, end-to-end
   task success. These improve with the episode flywheel (SFT/QLoRA, ML router)
   and are tracked in `evals/results.jsonl` and `metrics/dashboard.html`.
3. **Not claimed:** no 99.9% on open-ended LLM behaviour — that target is only
   meaningful for deterministic components and is stated here with its interval.

_Total checks: 71,914 · wall time: 8.7s · overall: ALL PASS_
