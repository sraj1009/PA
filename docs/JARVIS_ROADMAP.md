# BEE → JARVIS Roadmap

Phase-1 audit output (2026-10-05). Companion docs:
`docs/JARVIS_ARCHITECTURE.md` (how it works / where it's going),
`docs/TECHNICAL_DEBT.md` (every finding with file:line).
No code was changed while producing this roadmap.

---

## 0. Phase status (updated 2026-10-08, Phase 0 re-audit)

**Row 10 — FINAL 10-ITEM HARDENING BATCH (2026-10-06/08): DONE (uncommitted at re-audit time).**
Kernel routing for all surfaces (gate gap closed); M13 rotation/caps for all
JSONL streams; J1 tree-kill cancellation + crash-recovery checkpoints
(`/resume`); J3 model-upgrade quality gate (`bee/evals/gate.py`, `models.yaml`
promotion layer, nightly `model_gate`); untrusted-context isolation
(sentinel wrap + grant revocation + R2+ escalation); OS toasts + threshold
alerts (`bee/monitor/alerts.py`, nightly `alert_scan`); J2 skill versioning +
eval gate (`bee/evals/skillgate.py`, nightly `skill_gate`); M14
config-precedence matrix (`CONFIG_PRECEDENCE.md`, `Config.precedence`, 12
tests); ONE shared EventBus (`bee/events.py` + 2 facades); LiveKit temp-JSON
bridge replaced by bearer-auth HTTP push. **449 pytest / verify 71,914 ALL
PASS / eval 10-21 (one structural anomaly: `guard_blocked` — finding N6,
unrooted).** Re-audit (2026-10-08, `docs/JARVIS_BASELINE.md`) confirmed the
batch and logged new findings **N1–N9**; N1 (`/guard off` disables the
capability gate) is CRITICAL and blocks the program's Phase 2 security rule.
Statuses below are re-verified against the 2026-10-08 tree.

(Previous header, retained for history:)

## 0a. Phase status (2026-10-06, end of Phase 6)

| Phase | Status | Evidence |
|---|---|---|
| 0 — Safety net (git, .gitignore, baseline) | **DONE** | git baseline commit 3548dbc (202 pytest / 71,914 verify / 10-21 eval recorded) |
| 1 — Security (web auth, AST risk layer, eval_safe limits, episode redaction, archive-not-delete, sandbox hardening) | **DONE** | see `docs/SECURITY.md`; netguard 19 SSRF cases; risk/audit suites |
| 2 — Kernel | **DONE** | `bee/kernel/` (13 modules): TaskState machine, Plan/Action/Observation, PermissionDecision, ExecutionReceipts, AgentEvent+EventBus, AgentSession (persistent follow-ups), RetryPolicy, effect verification, ToolBus; REPL+web+slash-commands unified. 45 kernel tests; 308 pytest / verify ALL PASS 71,914 |
| 3 — Permissions + structured memory (capability policy, confirmations, memory architecture) | **DONE** | `bee/security/capabilities.py` (20 capabilities, R0–R5, task-scoped grants, pre-execution gate in loop.py); `bee/memory/store.py` (remember/recall/update/forget/summarize/expire + entity memory + provenance governance); kernel memory commands. tests/test_capabilities.py + tests/test_structured_memory.py. Original roadmap Phase 3 remainder **real user-job scheduling (B1/M8) — CLOSED in user Phase 6** (durable JobWorker through the kernel) |
| 4 — TRUE REALTIME VOICE (user Phase 4) | **DONE** | `bee/voice/realtime/` (7 modules): 7-state voice machine (IDLE/LISTENING/PROCESSING/THINKING/SPEAKING/INTERRUPTED/ERROR), VAD + endpointing + rate-limited partials, barge-in (TTS stop + kernel.cancel same frame), echo gating, wake word (STT-confirmed), reconnect w/ capped backoff; genuine LLM token streaming → sentence-pipelined edge-tts; LiveKit behind `VoiceTransport` (kernel never imports LiveKit); web `/chat` now real SSE (B3 closed). 12 voice tests incl. all 9 required scenarios; 361 pytest / verify ALL PASS 71,914. **Not claimed:** human-level naturalness; LiveKitTransport unverified against a live room (no credentials in test path) |
| 5 — Memory & config (roadmap §5 Phase 4) | PARTIAL | Session store (Phase 2) + structured store (Phase 3); vector rebuild dup (B2/M12), config precedence doc (M14), metrics caps (M13) still open |
| 6 — Provider abstraction | **DONE early (user Phase 1, item 6)** | `bee/agent/providers.py` — ProviderRegistry/ProviderConfig/ProviderHealth, env-key centralization, provider-matched cloud availability |
| 7 — Observability & UX (roadmap §5 Phase 6) | PARTIAL | real SSE (B3) done in user Phase 4; /voice contract (B4) half-fixed (uuid temp names now; mp3 docstring mismatch remains); dashboard live data, eval expansion still open |
| 8 — SAFE COMPUTER USE (user Phase 5) | **DONE** | `bee/computeruse/` (7 modules): 12-verb safe set behind 4 tools; per-action ComputerAction (target, coords+provenance, description, expected result, timeout, risk, verification strategy); closed loop (one call = act→observe→verify, no open-loop sequences); per-task action budget (15); coordinates never trusted (unproven refused, model_raw requires explicit confirm — risk layer HIGH/ask); 4 new capabilities (desktop.observe/launch/control/clipboard; launch & control ASK); 3 independent emergency stops (kernel.cancel / global / Ctrl+Alt+Q hotkey); privacy in code (typed text length-only, clipboard compare-only, no pixels/titles in logs, screenshot hash ring + bounded retention). 12 tests, ALL on MockDesktop (no real automation in CI). Unsafe set deliberately absent: no deletion/financial/credential/downloads/destructive verbs. **Not claimed:** WindowsDesktop untested-in-field by CI (no display); structural UI understanding, not vision-model pixel reading; Windows only. See docs/COMPUTER_USE.md |
| 9 — DURABLE AUTOMATION + PROACTIVE AGENT (user Phase 6) | **DONE** | `bee/automation/` (8 modules): Job/JobTrigger/JobExecution/JobQueue/JobWorker/Notification/ExecutionHistory; every field persists (id, owner/session, task, structured action, trigger, tz, enabled, permissions, retry, max_runtime, timestamps, next/last_run, state) under `<workspace>/automation/`. Triggers: one_time/daily/weekly/interval/calendar (ICS, `reminder_offset_minutes`). Restart: restore + recompute next_run + crash repair honoring retry budget + NO duplicate execution (execution row before start + cross-process file claims w/ TTL) + missed-job handling (one-time catch-up once within 15 min grace / MISSED beyond; recurring skip+notify, never backfill). Nightly maintenance (consolidate/vector-rebuild/router-retrain/teach-back/SFT) = durable function jobs with stable ids — B1/M8 closed, APScheduler callback model removed (start_scheduler now a shim). Jobs run through the SAME AgentKernel: kernel run-lock (executions serialized), job-scoped cancel event (max_runtime watchdog cancels the job, never user work), unattended fail-closed approver (only job.preapproved_capabilities). Proactive: EventBus (timer/calendar/file_change built-in; email/app/battery/network/device_state schema-supported, honestly 'unavailable'), default-deny ProactivePolicy, user-authorized rate-limited rules persisted (rules.json, created_by='user'). Control: history/retry/failure-notify/disable/enable/cancel/delete; concurrency: JobQueue single-flight + max_parallel cap. `automation.manage` capability (R3 ASK, #20) gates the automation_job tool. 27 tests incl. restart recovery (tests/test_automation.py); 400 pytest / verify ALL PASS 71,914 / eval 9-21 (quality ceiling). **Not claimed:** ICS-only calendar triggers; no live exchange/email/app/battery/network sources; at-least-once replay per retry budget (no transactional outbox); function-job timeout abandons the thread (no kill path). See JARVIS_ARCHITECTURE.md §18 |

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
| True realtime voice: 7-state voice machine, VAD + endpointing + interim partials, barge-in (immediate TTS stop + task cancel), echo gating, STT-confirmed wake word, reconnect w/ capped backoff, genuine token streaming → sentence-pipelined TTS; LiveKit behind VoiceTransport | bee/voice/realtime/*, livekit/transport.py; tests/test_voice_engine.py (12, incl. all 9 required scenarios) |
| LiveKit realtime worker (free tier): BeeSTT/BeeTTS, 2 h JWT mint, unattended guard | livekit/* |
| Nightly maintenance as durable function jobs (consolidation, vector rebuild, retrain, teach-back, SFT) — survive restarts, never no-op | bee/automation/ (Phase 6; scheduler.py start_automation) |
| Durable automation: jobs (one_time/daily/weekly/interval/calendar-ICS) through the kernel, restart recovery, missed-job handling, cross-process claims, proactive EventBus with default-deny user-authorized rules | bee/automation/ (8 modules); 27 tests; ARCHITECTURE §18 |
| Web UI: chat, engine switch, skills, LiveKit page, face state | webapp.py; setup.ps1 "All core checks passed" |
| Full-stack launcher `bee-runfull` (`python -m bee.cli full` / bee-runfull.ps1): web + livekit children (unbuffered logs), browser open, foreground REPL, teardown | cli.py `_full` (467+) |
| Monitoring: metrics, health, dashboard, Go native telemetry daemon (127.0.0.1:8790, WMI fallback) | monitor/*, native/ |
| Deterministic verification harness with Wilson 95% CIs | evals/verify_suite.py — 71,914 checks ALL PASS |
| Agent end-to-end eval (21 tasks) + per-run results.jsonl | evals/tasks.yaml, bee/evals/ — 10/21 |

## 2. Broken capabilities (verified defects)

| # | Capability | Defect | Location |
|---|---|---|---|
| ~~B1~~ | ~~User cron scheduling~~ | **CLOSED in Phase 6 (2026-10-06):** the no-op scheduler tool is superseded by `bee/automation/` — durable JobWorker executes jobs through the AgentKernel; execution row before start + cross-process claims prevent duplicates; nightly jobs are durable function jobs | `bee/automation/worker.py` (tools/scheduler_tool.py remains as a legacy read-only tool, superseded) |
| ~~B2~~ | ~~Vector store rebuild~~ | **CLOSED (audit 2026-10-06):** clear-before-add rebuild + stable-row-count regression test | memory/search.py |
| ~~B4~~ | ~~Web `/voice` contract~~ | **CLOSED (10-item batch):** docstring now matches JSON-only behavior; the endpoint itself is kernel-routed (gate gap closed) | webapp.py `/voice` |
| B5 | 10/21 agent-eval tasks fail (was 11/21) | Local 3B "missing substring" quality ceiling (file/DSA/memory/plan tasks) — model quality, not loop bugs; the J3 gate is the mechanism for closing it once a candidate model exists | evals/tasks.yaml run 2026-10-08: **10/21** |
| **N1** | **`/guard off` disables the capability gate** | **CRITICAL (re-audit 2026-10-08):** the gate check is conjoined with `ctx.guard_on`; disabling the legacy regex guard must never bypass capability authorization — the gate must be mandatory, kernel-owned, not chat-toggleable. Blocks program Phase 2 security rule | cli.py:434-437, loop.py:593 |
| **N6** | `guard_blocked` eval regression candidate | Re-audit 2026-10-08: the task failed (`expect_guard=blocked but no guard block occurred`) while unrelated eval tasks burned their tool budget on denied `automation.manage` asks (repeated `[y/N]` stdin prompts) — suspected kernel/approver reuse in the `/eval` REPL path; guard classifier itself intact (4,204 checks ALL PASS). Not root-caused; must not be normalized | eval run log 2026-10-08 |

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
| ~~M8~~ | ~~Real user-job execution + job payload serialization~~ | **CLOSED in Phase 6:** Job.to_dict() is the payload; the JobWorker executes it through the kernel |
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

- The system is **not** production-ready: 8-13/21 end-to-end eval tasks fail
  (model quality ceiling, not loop bugs — structural tasks stable across
  runs; Phase 6 run 2026-10-06: 9/21), the LiveKit worker and the `/eval`
  runner still call `run_agent` directly instead of the kernel — and
  therefore **do not pass through the Phase 3 capability gate**
  (kernel-only by construction; `ctx.capability_gate` is None there).
  (User scheduling B1/M8 is no longer a no-op — closed in Phase 6.)
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
- **Realtime voice is implemented (user Phase 4) but is NOT claimed to be
  human-level natural.** It is a local, offline, low-latency conversational
  system: energy VAD (not a neural VAD), STT-confirmed wake word (not
  always-on DSP wake), windowed re-transcription partials (faster-whisper is
  a batch model — genuine interim results, not token-level streaming ASR).
   `LiveKitTransport` is unverified against a live room (no credentials in
    the test path); the exercised transport is the local mic. (Proactive
    automation WAS implemented in Phase 6 — default-deny, user-authorized,
    rate-limited rules; see ARCHITECTURE §18.)
- **Computer use (user Phase 5) is SAFE-SET-ONLY by construction.** The
  unsafe verbs (unattended deletion, financial transactions, credential
  entry, arbitrary downloads/execution, destructive system actions) do not
  exist, so no grant, prompt, or mistake can produce them. `WindowsDesktop`
  is untested-in-field by CI (no display in the test path — the verified
  path is `MockDesktop`); UI understanding is structural (window
  titles/classes/rects), NOT vision-model pixel reading; `screen_changed`
  verification proves the screen changed, not that it changed *correctly*
  (stronger `expected` specs or the model's next observation catch the
  rest). Windows 10/11 only — Linux/macOS return a clean `DesktopError`.
- Roadmap §5 Phase 4 (memory & config: B2/M12, M13, M14) and the remainder
  of §5 Phase 6 (dashboard live data, eval expansion, B4 docstring) are
  still the plan.
