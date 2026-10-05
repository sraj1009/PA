# BEE → JARVIS Roadmap

Phase-1 audit output (2026-10-05). Companion docs:
`docs/JARVIS_ARCHITECTURE.md` (how it works / where it's going),
`docs/TECHNICAL_DEBT.md` (every finding with file:line).
No code was changed while producing this roadmap.

---

## 0. Phase status (updated 2026-10-05, end of Phase 3)

| Phase | Status | Evidence |
|---|---|---|
| 0 — Safety net (git, .gitignore, baseline) | **DONE** | git baseline commit 3548dbc (202 pytest / 71,914 verify / 10-21 eval recorded) |
| 1 — Security (web auth, AST risk layer, eval_safe limits, episode redaction, archive-not-delete, sandbox hardening) | **DONE** | see `docs/SECURITY.md`; netguard 19 SSRF cases; risk/audit suites |
| 2 — Kernel | **DONE** | `bee/kernel/` (13 modules): TaskState machine, Plan/Action/Observation, PermissionDecision, ExecutionReceipts, AgentEvent+EventBus, AgentSession (persistent follow-ups), RetryPolicy, effect verification, ToolBus; REPL+web+slash-commands unified. 45 kernel tests; 308 pytest / verify ALL PASS 71,914 |
| 3 — Permissions + structured memory (capability policy, confirmations, memory architecture) | **DONE** | `bee/security/capabilities.py` (19 capabilities, R0–R5, task-scoped grants, pre-execution gate in loop.py); `bee/memory/store.py` (remember/recall/update/forget/summarize/expire + entity memory + provenance governance); kernel memory commands. tests/test_capabilities.py + tests/test_structured_memory.py. Remaining from original roadmap Phase 3: **real user-job scheduling (B1/M8)** — still open |
| 4 — Memory & config | PARTIAL | Session store (Phase 2) + structured store (Phase 3); vector rebuild dup (B2/M12), config precedence doc (M14), metrics caps (M13) still open |
| 5 — Provider abstraction | **DONE early (Phase 1, item 6)** | `bee/agent/providers.py` — ProviderRegistry/ProviderConfig/ProviderHealth, env-key centralization, provider-matched cloud availability |
| 6 — Observability & UX | OPEN | real SSE (B3), /voice contract (B4 — docstring half-fixed), dashboard live data, eval expansion |

## 1. Completed capabilities (working, tested)

| Capability | Evidence |
|---|---|
| Local-first 3B model pipeline (`bee4b` on Ollama, `num_ctx=8192` pinned for 8 GB VRAM) | client.py; model bench in `evals/bench_model.json` |
| Dual routing: 536-line regex fastpaths + ML router (TF-IDF/LogReg, 408 episodes, CV 0.9975, complexity floor) | fastpaths.py; brain/mlrouter.py; router suite 6,000 checks 100% |
| Think/act/observe loop with repeat guard, fail-streak breaker, empty-completion retry, forced wrap-up | loop.py (636); 202 pytest green |
| Permission guard (allow/ask/deny, 3 modes) | guard.py; 4,204 guard checks 100% |
| PII redaction on cloud payloads (Luhn CC, keys, Aadhaar, phones) | privacy.py; 13,200 pii checks 100% |
| Verifier with one bounded fix round (math/file/URL) | brain/verifier.py; in verify suite |
| RAG: LanceDB 768-dim + keyword fallback + RRF | brain/rag.py; memory/search.py; rag suite 100% |
| 14 tool modules incl. files (workspace jail), shell, code (eval-free), web multi-engine, calculator (AST `eval_safe`), sandbox (Docker), planner, skills, systemctl, spawn | tools/*; zero eval/exec confirmed by grep |
| Memory flywheel: episodes JSONL → router retrain → SFT build → QLoRA; golden teach-back → skills | pipeline/, train/, training/ |
| Voice: faster-whisper STT (CPU-first Windows), clap wake (double-clap 60–400 ms, adaptive floor), pyttsx3 SAPI + edge-tts fallback | voice/* |
| LiveKit realtime worker (free tier): BeeSTT/BeeTTS, 2 h JWT mint, unattended guard | livekit/* |
| Nightly scheduler (consolidation, vector rebuild, retrain, teach-back, SFT) | scheduler.py |
| Web UI: chat, engine switch, skills, LiveKit page, face state | webapp.py; setup.ps1 "All core checks passed" |
| Full-stack launcher `bee-runfull` (`python -m bee.cli full` / bee-runfull.ps1): web + livekit children (unbuffered logs), browser open, foreground REPL, teardown | cli.py `_full` (467+) |
| Monitoring: metrics, health, dashboard, Go native telemetry daemon (127.0.0.1:8790, WMI fallback) | monitor/*, native/ |
| Deterministic verification harness with Wilson 95% CIs | evals/verify_suite.py — 71,914 checks ALL PASS |
| Agent end-to-end eval (21 tasks) + per-run results.jsonl | evals/tasks.yaml, bee/evals/ — 10/21 |

## 2. Broken capabilities (verified defects)

| # | Capability | Defect | Location |
|---|---|---|---|
| B1 | User cron scheduling | Every job (restored and newly added) is a `_noop` that logs one line; jobs never execute | tools/scheduler_tool.py:39-40, 50-57, 82 |
| B2 | Vector store rebuild | `rebuild()` appends (`t.add`) to the existing table each 12 h → duplicate rows accumulate, search quality degrades over time | memory/search.py:55 |
| B3 | Web "SSE" chat streaming | Events buffered and flushed only after the turn completes — not streaming | webapp.py:74-96 |
| B4 | Web `/voice` contract | Docstring promises "+tts mp3"; endpoint returns JSON text only; fixed temp filename `bee_upload{suffix}` races on concurrent uploads | webapp.py:101, 108 |
| B5 | 11/21 agent-eval tasks fail | Local 3B "missing substring" quality ceiling (file/DSA/memory/plan tasks) — model quality, not loop bugs | evals/tasks.yaml run 2026-10-05 |

## 3. Risky capabilities (work, but can harm user data/system)

| # | Risk | Location |
|---|---|---|
| R1 | Consolidation deletes original diary files after summarizing (`f.unlink()`) — irreversible data loss | scheduler.py:56-60 |
| R2 | `code_run` guard bypass: shell-style regexes over Python text; `shutil.rmtree`, `os.remove`, `Path.unlink`, truncating writes classify `allow` | guard.py:59-65 + tools/code.py |
| R3 | Unauthenticated web endpoints drive the full agent (with shell tools), mint 2 h LiveKit JWTs, and mutate the global engine | webapp.py:68-96, 149-158, 190-210 |
| R4 | `.env` (LiveKit keys) in a OneDrive-synced dir, not in `.gitignore`, no VCS → future `git init` would commit credentials; sandbox workspace mount exposes `.env` to the container | .gitignore (absent entry), sandbox/Dockerfile |
| R5 | Episodes persist unredacted tool output → feeds SFT + cloud teach-back | loop.py:579-580 |
| R6 | `sys.argv` mutation inside a running process (scheduler retrain job; livekit "start" hack) | scheduler.py:98-105, livekit/agent.py:298-306 |
| R7 | `eval_safe` has no depth/size/time limits (DoS surface in calculator) | tools/base.py, tools/calculator.py:35 |
| R8 | LiveKit state shared via temp-JSON file across processes (race/visibility) | livekit/state.py ↔ webapp.py:219-222 |

## 4. Missing capabilities (required for the target architecture)

| # | Missing | Why needed |
|---|---|---|
| M1 | Version control | Incremental, testable changes are impossible to audit without it; also the secret-hygiene fix |
| M2 | `TaskState` + typed task lifecycle | Kernel responsibility #2; resumability, per-task telemetry |
| M3 | `CancellationToken` | Kernel responsibility #7; today only KeyboardInterrupt cancels (loop.py:563-565) |
| M4 | Typed events + EventBus | Kernel telemetry; real SSE; ends stringly-typed dict event soup |
| M5 | Conversation Manager / single Context factory | 3 bootstrap sites (cli `_repl`, webapp.get_ctx:27-39, livekit._build_brain:65-96) duplicate ~20 lines each |
| M6 | Web authentication (token, even a single local secret) | Closes R3 |
| M7 | Policy AST pass for Python payloads | Closes R2 |
| M8 | Real user-job execution + job payload serialization | Closes B1 |
| M9 | Provider ABC + registry | Decouple ~4 files from provider specifics; make adding a provider a 1-file change |
| M10 | Episode redaction at write time | Closes R5 |
| M11 | Consolidation archive-not-delete | Closes R1 |
| M12 | Vector rebuild clear-before-add / upsert | Closes B2 |
| M13 | Metrics rotation + episode size caps | Unbounded growth (metrics history, episodes JSONL, diaries) |
| M14 | Documented config precedence (config.yaml / models.yaml / .env / settings.json) | Hidden assumptions today |
| M15 | `full` target in Makefile; root cleanup (temp/ 27 scratch files; bee.py stub) | Housekeeping |

## 5. Implementation order (incremental; each phase ends green)

**Phase 0 — Safety net (prerequisite for everything)**
1. `git init` + corrected `.gitignore` (add `.env`, `train/`, `metrics/`, `temp/`, `models/` weights, `sandbox` artifacts)
2. Secret scan of the tree (grep for key patterns; values never printed)
3. Baseline test record committed: 202 pytest / 71,914 verify / 10-21 eval
- Tests: full suite re-run; zero diffs expected.

**Phase 1 — Security (the only changes justified now under "audit only")**
1. Web auth: single token (env-derived, never logged) required on `/chat`, `/voice`, `/engine` POST, `/livekit/token`; `/health` stays open; token delivered at startup, printed once to console, file in `temp/` with 0600-ish ACL note
2. `guard.classify` AST pass for `code_run` (import/attribute/name allowlist for `os`, `shutil`, `subprocess`, `pathlib.unlink`, `open(...,'w')` truncation) → ask/deny
3. `eval_safe` limits (AST depth, node count, time budget)
4. Episodes redacted at write (reuse privacy.py)
5. Consolidation: move originals to `memory/diary/archive/` instead of unlink
6. Sandbox: do not mount the project `.env` (mount a secrets-free subpath or copy strategy)
- Tests: new unit tests for AST classifier + web auth; verify_suite guard suite re-run; pytest stays 202+ green.

**Phase 2 — Kernel extraction (wrap, don't rewrite)**
1. `TaskState` dataclass + status enum wrapping `run_agent` internals
2. `CancellationToken` checked per iteration; KeyboardInterrupt path kept
3. Typed events (`TurnStarted`, `ToolCall`, `GuardDecision`, `ToolResult`, `Error`, `TurnDone`) + in-process EventBus; REPL prints from bus
4. Single `Context` factory (Conversation Manager) replacing 3 bootstrap sites
- Tests: existing 202 must pass unchanged (behavioral pin); new transition tests for TaskState; cancel-token test.

**Phase 3 — Tool Bus + Policy + real scheduling**
1. Single dispatch function (loop/web/livekit share); typed `Observation`
2. Per-tool verification policy hooks (generalize verifier)
3. Job payload serialization (task text / command spec) + real execution of user cron via the same Kernel path (guard enforced, unattended)
4. Remove `sys.argv` hacks (explicit args to train_router / worker)
- Tests: job round-trip tests (serialize → execute → observe); guard suite green; no-argv-mutation assertions.

**Phase 4 — Memory & config**
1. Vector rebuild clear-before-add (or upsert by id); delete-count regression test
2. Unify `train/` and `training/` roots (one tree, documented)
3. Session store for Conversation Manager (persist/restore)
4. Config precedence doc + `config.py` single-source resolution
5. Metrics rotation + caps (episodes, diary, metrics history)
- Tests: search.py dup regression (rebuild twice → stable row count); config precedence matrix test.

**Phase 5 — Provider abstraction**
1. `Provider` ABC (chat / embed / models_list / availability) + registry
2. Ollama/Gemini/native adapters over it; engines.py becomes thin
3. Offline engine expressed as a provider state, not a branch
- Tests: provider interface conformance tests; hybrid fallback table test.

**Phase 6 — Observability & UX**
1. Real SSE from EventBus on `/chat` (fix B3); `/voice` contract fixed (B4: either deliver mp3 or fix docstring; unique temp files)
2. Metrics endpoint + dashboard live data; eval expansion (file/DSA/memory tasks split into model-quality vs loop-quality buckets)
3. Makefile `full` target; root cleanup; regenerate stale docs (`docs/llm-component.md`)
- Tests: SSE integration test with TestClient; full-suite green; eval as improvement gate (target ≥ 14/21 before claiming quality progress).

### Per-phase test gates (hard rule)

- `python -m pytest tests -q` — must end **202+ passed, 0 failed**
- `python -m evals.verify_suite` — must end **ALL PASS** after any module it covers is touched
- `/eval` (21 tasks) — run at each phase boundary; regressions are blocking, quality-ceiling fails are tracked, not blocking

## 6. Future Jarvis milestones (post-migration)

- **J1 True multi-step autonomy:** Planner steps bound to TaskState with per-step verification and resumable checkpoints (kill -safe restart).
- **J2 Skill marketplace discipline:** golden teach-back already writes skills/; add skill versioning + eval gate before a skill ships.
- **J3 Local model upgrade path:** QLoRA pipeline exists (training/qlora); add nightly quality gate that only promotes a new local model when eval ≥ baseline + margin.
- **J4 Device mesh:** native Go daemon becomes a first-class telemetry/health provider behind the Provider ABC pattern (daemon = "machine provider").
- **J5 Multi-session:** Conversation Manager supports parallel sessions (web tab + REPL + livekit) with per-session cancellation and memory scoping.
- **J6 Hardened exec:** default exec tools to the Docker sandbox when available, host exec only for allowlisted verbs.

## 7. Explicit non-claims

- The system is **not** production-ready: 8-11/21 end-to-end eval tasks fail
  (model quality ceiling, not loop bugs — structural tasks stable across
  runs), user scheduling is still a no-op (B1), the LiveKit worker and the
  `/eval` runner still call `run_agent` directly instead of the kernel —
  and therefore **do not pass through the Phase 3 capability gate**
  (kernel-only by construction; `ctx.capability_gate` is None there).
- The capability gate is a policy layer OVER the guard; it maps tools to
  capabilities by name + argument heuristics, which a creative command
  phrasing can under-map (e.g. an aliased delete). The guard/AST layers and
  the sandbox remain the deeper protections.
- The kernel verifies effects deterministically (file/edits/mkdir/target
  probes); it does not understand arbitrary intent, and "unverified" work is
  never reported as verified success.
- Structured memory is a flat JSON store with keyword scoring — not a
  vector DB, not graph memory; conflict resolution is key-based upsert,
  not semantic dedup.
- Realtime-voice event streaming and proactive automation are NOT
  implemented; the typed event model that would carry them is.
- Phases 4 (remainder) and 6 above are still the plan.
