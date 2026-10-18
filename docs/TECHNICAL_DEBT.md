# BEE Technical Debt Report

Phase-1 audit (2026-10-05). Every entry cites verified file:line evidence.
Severity: **CRITICAL** = can compromise system/data security now;
**HIGH** = data loss, security gap, or silently-wrong behavior;
**MEDIUM** = maintainability/correctness risk; **LOW** = hygiene.

---

## CRITICAL

### C1. Unauthenticated web endpoints control the full agent
`bee/webapp.py` — no auth on any route.
- `POST /chat` (68-96): runs the complete `run_agent` including shell/code tools.
- `POST /engine` (149-158): mutates the **global** engine for all turns.
- `POST /livekit/token` (190-210): mints 2-hour LiveKit participant JWTs for any room name (validated for shape only, livekit/agent.py `validate_room`).
- `POST /voice` (99-137): full STT → agent pipeline.
Mitigation today: default bind `127.0.0.1:8787` (cli.py:545-546, webapp.py:227).
`--host` can widen this to LAN, at which point any host on the network owns the
machine (shell tool!).
**Fix:** token auth (env-derived, never logged) on all stateful endpoints —
Roadmap Phase 1.1.

### C2. Secrets hygiene: `.env` in synced dir, no `.gitignore` entry, no VCS
- `.env` holds `LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET` in a
  OneDrive-synced project directory.
- `.gitignore` (18 lines) has **no `.env` entry** (also missing `train/`,
  `metrics/`, `models/`, `temp/`).
- There is **no git repository** — any future `git init && git add -A`
  commits credentials instantly.
- `sandbox/Dockerfile` mounts the workspace into the container, so `.env` is
  readable inside the sandbox image runtime.
**Fix:** corrected `.gitignore` + `git init` + secret scan (Phase 0);
secrets-free mount strategy for sandbox (Phase 1.6).

## HIGH

### H1. Guard regex bypass for Python `code_run` payloads
`bee/guard.py:59-65` — `classify()` runs shell-style regexes over
`str(args["command"] or args["code"])`. Python payloads like
`shutil.rmtree(...)`, `os.remove(...)`, `Path(...).unlink()`, or
`open(p, "w")` truncation match no pattern → `allow`. `tools/code.py` (47)
runs them via host `python -c`.
**Fix:** AST-based classification pass for `code_run` (Phase 1.2).

### H2. Episodes persist unredacted tool output
`bee/agent/loop.py:579-580` — `episode.tool(name, args, ok, dt, res_v)` writes
raw tool results (files read, command output, web content) to
`train/episodes/*.jsonl`, which feeds SFT build and cloud teach-back.
`privacy.py` redacts only live cloud-bound LLM payloads — not storage.
**Fix:** redact at write time, reusing privacy.py (Phase 1.4).

### H3. Nightly consolidation irreversibly deletes diaries
`bee/scheduler.py:56-60` — after LLM-summarizing old diary entries, originals
are removed via `f.unlink()`. One bad summary = permanent data loss.
**Fix:** move originals to `memory/diary/archive/` (Phase 1.5).

### H4. LanceDB rebuild accumulates duplicates
`bee/memory/search.py:55` — `rebuild()` calls `t.add(rows)` against the
existing table every 12 h; ids are `f"{src}#{ch[:60]}"` with no
clear/upsert → duplicate rows accumulate; search returns stale copies and the
store grows without bound.
**Fix:** clear-then-add or upsert by id (Phase 4.1).

### H5. All user cron jobs are no-ops
`bee/tools/scheduler_tool.py:39-40, 50-57, 82` — restored jobs from
`jobs.json` and newly added jobs both schedule `_noop`, which writes one line
to `jobs.log`. The tool description (102) admits this, but a user who sets a
job believes it runs. `jobs.json` already contains
"Monthly_sales_analysis_report_delivery" — it will never execute.
**Fix:** job payload serialization + real execution via the kernel (Phase 3).

### H6. `sys.argv` mutation inside a live process
- `bee/scheduler.py:98-105` — retrain job rewrites
  `_sys.argv[:1] + ["--min", "10"]` around `train_router.main()`, then restores.
  Fragile: any concurrent argparse use sees the mutated argv.
- `bee/livekit/agent.py:298-306` — appends `"start"` to `sys.argv` so the
  worker entrypoint's argparse accepts it.
**Fix:** explicit argument passing; no global argv writes (Phase 3.4).

### H7. Cross-process state via temp JSON
`bee/livekit/state.py` ↔ `bee/webapp.py:219-222` (`/face/state`) — the LiveKit
worker process writes a temp JSON file that the web process reads. No atomicity
guarantee, stale reads on crash, Windows file-lock edge cases.
**Fix:** replace with the EventBus/local HTTP status in Phase 2/6, or atomic
rename writes at minimum.

### H8. `eval_safe` unbounded
`bee/tools/base.py` + `tools/calculator.py:35` — AST allowlist is good (zero
eval/exec confirmed), but there is no AST depth/node-count limit or time
budget; a crafted expression can hang or balloon the calculator tool.
**Fix:** limits + timeout (Phase 1.3).

**CLOSED — 2026-10-18 hardening pass.** All limits live in
`bee/tools/base.py:119-131`: input 20k chars (`eval_safe` :319-339), AST 200
nodes / depth 20 / 10k-char literals (`_check_bounds` :298-316), 250k-step
budget + 90 ms wall-clock deadline checked at every `_ev` step (:231-239,
per-call budget — the shared `_step_budget` global is gone), and argument
guards for the single C calls no step budget can interrupt: exponent 10⁴ +
result-bits 10⁶ for `**`/`pow` (`_check_pow` :134-143), sequence-repeat 10⁵ +
int-product bits (`_guarded_mul` :168-184), `range()` span 10⁵
(`_guarded_range` :187-197 — the first pass's `sum(range(10**18))` residual is
now rejected at construction), `factorial` arg 10⁴ (:200-204), `bytes()` 10⁶
(:207-211). Allowlist keys unchanged (router `_residue_is_math` contract);
errors are one-line `ValueError`s surfaced as `{"error": ...}` by the
calculator. Regressions `tests/test_debt_fixes.py::test_h8_*` (7).

## MEDIUM

### M1. 636-line implicit kernel; three Context bootstrap sites
`bee/agent/loop.py` owns routing, engines, RAG, act loop, verification,
episodes, and reflection inline. `Context` is constructed in cli `_repl`,
`webapp.get_ctx` (27-39), and `livekit/agent.py _build_brain` (65-96) —
~20 duplicated lines each, and `Context.client` is assigned
post-construction as an untyped optional (`agent/context.py`).
**Fix:** Phase 2 (TaskState, token, factory) / Phase 4.3.

### M2. Stringly-typed event dicts + fake SSE
`loop.py` `on_event(dict)` with ad-hoc `type` keys; `webapp.py:74-96`
buffers all events and streams them after the turn completes (not SSE).
**Fix:** typed events + EventBus + real streaming (Phase 2.3, 6.1).

### M3. Global-state cluster
- `webapp.py:24` module-global `CTX`
- `agent/engines.py` module globals (engine state; also mutated by
  `livekit/agent.py:78` which forces `cfg.guard.mode = "unattended"` on a
  shared config object)
- `memory/search.py:68` module-global `_cache`
- `brain/mlrouter.py` one-shot global `_ivw_filtered`
**Fix:** state owned by Context/Session objects (Phase 2/4).

### M4. Dual routing systems
`fastpaths.py` (536 lines of regex) vs `router.py` (224, tiers) vs
`brain/mlrouter.py` (learned). Three selection mechanisms with the
complexity-floor rule as the only documented interaction. Behavior is
pinned by tests, but adding a capability means touching all three.
**Fix:** keep (they work — 6,000 router checks 100%) but document the
decision order and expose it as one `Router` interface (Phase 2/5).
**CLOSED — 2026-10-18.** The three mechanisms remain (deliberate tiers: the ML
router and the fast paths are load-bearing), but the decision is now ONE
documented entry: `bee/agent/router.py:decide()` composes deterministic →
explicit → smalltalk → fast-path → ML → heuristic (escalation follows in
`run_agent`, which needs live service probes) and returns the fast-path hit
alongside the tier decision. Order documented in the router docstring +
`AGENTS.md` + README §9; pinned by `tests/test_routing_order.py` (7 tests).
`route()`/`route_task()` APIs unchanged.

### M5. Unclear config precedence (4 files)
`config.yaml` (135) / `models.yaml` (34) / `.env` / `settings.json` —
precedence is implicit in `bee/config.py` (357) and `engines.py` (102).
**Fix:** documented precedence + single resolution point (Phase 4.4).

### M6. Two eval roots, two training roots
- `evals/` (root: data — tasks.yaml, verify_suite.py, results.jsonl) vs
  `bee/evals/` (code — runner).
- `train/` (episodes, router_model.joblib, sft_v1.jsonl, golden/) vs
  `training/` (QLoRA scripts).
**Fix:** unify per subsystem with a note file (Phase 4.2).

### M7. Hardcoded `Asia/Kolkata` × 3
- `bee/scheduler.py:207` (scheduler timezone)
- `bee/tools/scheduler_tool.py:32` (user-job scheduler timezone)
- `bee/agent/offline.py:58` (answer label claims Asia/Kolkata while using
  system local time — incorrect contract for non-IST machines)
**Fix:** `timezone: local` or config-driven IANA zone (Phase 4.4).

### M8. Wrong/stale API contracts and docs
- `/voice` docstring promises "+tts mp3"; returns JSON text (webapp.py:101).
- `docs/llm-component.md` describes the pre-bee4b pipeline.
- `bee.py` (11-line stub) duplicates `python -m bee.cli` as an entry point.
- `Makefile` (34) has no `full` target (full mode lives only in
  cli.py `_full` + bee-runfull.ps1).
**Fix:** Phase 6.3.

### M9. Untested execution paths
Full-stack mode, livekit brain path, `/chat` integration, consolidation,
user-job execution (trivially "untested" — it's a no-op), teach-back, SFT
build, native Go daemon install path.
**Fix:** per-phase integration tests as each is touched (Phases 1-6).

### M10. Unbounded growth
Metrics JSONL history, episodes JSONL, diary files, LanceDB table (see H4),
`temp/` (27 scratch files, incl. full-mode child logs).
**Fix:** rotation/caps (Phase 4.5) + root cleanup (Phase 6.3).

### M11. Hidden VRAM assumption
`client.py` pins `num_ctx=8192` so `bee4b` (3B) fits 8 GB VRAM. Changing the
local model or GPU silently breaks the assumption; it is not surfaced in
config.
**Fix:** move to models.yaml with per-model context + VRAM note (Phase 5).
*(A59, 2026-10-13: the figure was wrong twice over — the card is a 4 GB RTX 3050,
and while every doc claimed 8192 the shipped `config.yaml` had drifted to 4096,
which is what actually governed the local tier. `num_ctx` now reaches the server on
the primary path, and the shipped value is pinned by a measured test.)*

### M12. Potential cycles masked by lazy imports
`cli ↔ webapp` and `livekit.agent ↔ agent/voice` use function-level imports
to dodge import cycles — a sign the module boundaries are wrong.
**Fix:** resolve naturally via the Context factory / EventBus (Phase 2).

## LOW

### L1. Windows-first assumptions scattered, undocumented
`shell=True` (tools/shell.py:45), SAPI via pyttsx3 (voice/speak.py),
WMI queries (native/), `os.startfile` (cli.py:508). All intentional for
this machine but invisible to a maintainer.
**Fix:** one `PLATFORM` section in the architecture doc (done) + comments.

### L2. Unused import: `WebSocket` in webapp.py:12.

### L3. Static dashboard staleness — `monitor/dashboard` HTML is served
statically; live data only via the metrics JSONL it reads client-side.
**Closed by A25a** (2026-10-08): `GET /dashboard` renders per request behind the
web token gate, with `<meta refresh>` + `no-store`; the written file stays an
explicit snapshot.

### L4. `models/` holds faster-whisper weights as plain files in a
OneDrive-synced dir — sync bloat. **Fix:** move to a non-synced cache
path (Phase 6.3 cleanup, with config override).

### L5. Test warning: StarletteDeprecationWarning from FastAPI
TestClient/httpx (1 warning in the 202-pass run) — cosmetic, track on
dependency upgrade.

---

## Summary counts (original 2026-10-05 audit)

| Severity | Count | IDs |
|---|---|---|
| CRITICAL | 2 | C1, C2 |
| HIGH | 8 | H1–H8 |
| MEDIUM | 12 | M1–M12 |
| LOW | 5 | L1–L5 |

**Recommended first implementation phase: Roadmap Phase 0 + Phase 1**
(VCS/secret safety net, then the six security fixes C1, C2, H1, H2, H3, H8 +
sandbox mount H-portion). All other items follow the roadmap order; each ends
with the full test gates green (pytest 202+, verify_suite ALL PASS, eval
10/21 baseline as the quality floor).

---

## Phase 0 re-audit (2026-10-08) — closures and new findings

Full evidence: `docs/JARVIS_BASELINE.md`. Original IDs closed since 2026-10-06:

| ID | Status | Closed by |
|---|---|---|
| C1, C2 | CLOSED | web bearer auth (Phase 1); git + .gitignore + `.env.example` (Phase 0); rotation note for OneDrive-synced credential history remains operator action |
| H1 (guard regex bypass) | CLOSED | AST risk layer `security/risk.py:174` + `guard.check` (Phase 1); pinned 4,204-check suite |
| H2 (unredacted episodes) | CLOSED | redaction at write (audit 2026-10-06) |
| H3 (diary deletion) | CLOSED | archive-not-delete (audit) |
| H4 (LanceDB dups) | CLOSED | clear-before-add rebuild (audit B2) |
| H5 (no-op jobs) | CLOSED | Phase 6 durable JobWorker through the kernel |
| H6 (sys.argv mutation) | **HALF** | scheduler fixed (`scheduler.py:110` explicit args); **`livekit/agent.py:307-314` still mutates/restores argv** |
| H7 (temp JSON bridge) | CLOSED | 10-item #10: bearer-auth HTTP push → web UI in-memory state + `age_s` |
| H8 (eval_safe unbounded) | OPEN | AST allowlist only; no depth/size/time budget (R7) |
| M1 (implicit kernel) | CLOSED | explicit `bee/kernel/` (Phases 2–6) |
| M2 (stringly events) | CLOSED | typed AgentEvent + ONE shared EventBus (10-item #9) + real SSE (Phase 4) |
| M3 (global state) | PARTIAL | documented & bounded; per-kernel run-lock; web `CTX` + engines globals remain (single-user by design) |
| M4 (dual routing) | PARTIAL | router v2 unified; regex fastpaths + ML router both remain (deliberate tiers) |
| M5 (config precedence) | CLOSED | 10-item #8: `CONFIG_PRECEDENCE.md` + `Config.precedence` + 12 contract tests |
| M6 (two training roots) | OPEN | `train/` and `training/` still coexist |
| M7 (hardcoded tz) | PARTIAL | jobs use configured tz; residual literals may remain |
| M8 (stale contracts) | CLOSED | `/voice` docstring matches the JSON-only behavior; dashboard live data shipped in A25a (`GET /dashboard`, per-request render) |
| M9 (untested paths) | PARTIAL | 449-test suite incl. kernel/automation/voice/bridge; LiveKit room + WindowsDesktop still unverified in-field |
| M10 (unbounded growth) | CLOSED | 10-item #2 (M13): rotation + caps at every JSONL chokepoint |
| M11 (VRAM assumption) | OPEN | `num_ctx=8192` pinned for 8 GB; not auto-tuned |
| M12 (lazy-import cycles) | PARTIAL | documented edges; not yet import-lint enforced |

### New findings (2026-10-08)

| ID | Sev | Finding | Location |
|---|---|---|---|
| **N1** | **CRITICAL** | **`/guard off` (`ctx.guard_on=False`) also disables the CAPABILITY GATE** — the gate check is conjoined with `ctx.guard_on`. Disabling the legacy regex guard must never bypass capability authorization; the gate must be mandatory (kernel-owned) and not chat-toggleable | `cli.py:434-437`, `loop.py:593` |
| **N2** | HIGH | ToolBus is not the authoritative dispatcher — the LLM loop executes tools via the raw `tools_by_name()` dict (fastpath + main loop), duplicating validation/audit that the bus should own | `loop.py:268,427,627` vs `kernel/tools_bus.py` |
| **N3** | HIGH | `ToolBus.call()` accepts `timeout` but enforces nothing (`timed_out` always False) — no timer/thread kill at the bus level | `tools_bus.py:105-135` |
| **N4** | HIGH (latent) | Cancellation is context-scoped (`ctx.cancel_event`), never task-owned; safe today only because REPL/eval/automation each clear/use their own event; web has no cancel route and shares one kernel ctx → a future web cancel leaks into the next task | `kernel.py:96-102`, `webapp.py` |
| **N5** | MEDIUM | `.gitignore` does not cover runtime memory artifacts `memory/receipts.jsonl`, `memory/sessions/`, `memory/store.json`, `memory/checkpoints/` → accidental personal-data commit possible | `.gitignore:18-23` |
| **N6** | MEDIUM | Eval anomaly: `guard_blocked` failed 2026-10-08 while unrelated tasks burned their tool budget on denied `automation.manage` asks (repeated `[y/N]` prompts on stdin) — suspected kernel/approver reuse in the `/eval` REPL path; not root-caused; must not be normalized | eval run log 2026-10-08 |
| **N7** | LOW | Load-dependent flake: one automation-worker test times out on `wait_idle(10)` under heavy system load (green otherwise) — fix the cause (worker join/shutdown determinism), do not loosen the test | `tests/test_automation.py` |
| **N8** | LOW | `evals/results_summary.json` is a generated artifact but is git-tracked | `git ls-files` |
| **N9** | LOW | `ToolBus.from_default()` records only the FIRST capability per tool (`caps[0]`) while the gate uses the full list — latent under-mapping once the bus is authoritative | `tools_bus.py:83` |

**Updated counts (after re-audit):** CRITICAL 3 (C1✓, C2✓, **N1**) ·
HIGH 8+3 (H1✓ H2✓ H4✓ H5✓ H7✓ closed; H3✓; H6, H8 open; **N2, N3, N4 new**) ·
MEDIUM 12+3 (8 closed/partial as above; **N5, N6, N7**) · LOW 5+3
(**N8, N9**). **N1 is the blocking item for the program's Phase 2 security
rule; N2/N3 together define the ToolBus migration scope; N4 defines the
Phase 4 cancellation scope.**

---

## Coherence-pass closures (2026-10-08, post acceptance-audit)

Evidence: `docs/JARVIS_ACCEPTANCE_AUDIT.md` + `tests/test_debt_fixes.py`
(regressions pinned) + source at cited locations.

| ID | Status | Closed by |
|---|---|---|
| N1 (CRITICAL) | **CLOSED** | F0: capability gate decoupled from `ctx.guard_on` (loop.py); regression `test_n1_capability_gate_runs_even_when_guard_off` |
| N2 (HIGH) | **CLOSED** | F1+**F2**: the agent loop dispatches every tool through `ToolBus.call` (one execution path); sub-agents inherit the gate; regression `test_f2_loop_executes_tools_through_toolbus` |
| N3 (HIGH) | **CLOSED** | `ToolBus.call` now enforces its per-tool timeout (worker thread + `ToolTimeoutError`); the agent can no longer be blocked indefinitely by one tool; regressions `test_n3_bus_timeout_enforced` / `test_n3_fast_call_unaffected_by_timeout_path` / `test_n3_handler_exception_still_maps` |
| N4 (HIGH-latent) | **CLOSED** | The KERNEL owns task-scoped cancellation: `AgentKernel._run_impl` clears the cancel event at every new task start (kernel.py); a cancelled task can no longer poison the next, on any surface; regression `test_n4_stale_cancel_event_does_not_poison_new_task`. (Web/LiveKit still have no *cancel route* — a feature gap, not a leak path; the kernel clear makes a future route safe.) |
| N5 (MEDIUM) | **CLOSED** | `.gitignore` covers `memory/receipts.jsonl`, `memory/sessions/`, `memory/store.json`, `memory/checkpoints/` (verified by `git ls-files`) |
| N6 (MEDIUM) | **CLOSED — root-caused** | The `guard_blocked` eval anomaly was a REAL DEFECT: a guard-'ask' DENIED by the approver left the task in `WAITING_FOR_PERMISSION`; the later move to `VERIFYING` raised `InvalidTransitionError`. F5: `_approver` returns the task to `EXECUTING` on both outcomes; regression `test_f5_denied_guard_ask_does_not_strand_task`; `guard_blocked` re-run with the live model: **PASS (42.0s)**. The "denied automation.manage asks burned tool budget" observation was the same model retrying after a block — no approver-reuse bug found. |
| N7 (LOW) | OPEN | Load-dependent flake in `tests/test_automation.py` (`wait_idle(10)`). Not reproduced in this session's runs (all green). Correct fix = deterministic worker shutdown (join with timeout + drain check) — deferred; must NOT be loosened. |
| N8 (LOW) | **CLOSED** | `evals/results_summary.json` is no longer tracked (`git ls-files evals/` = verify_suite.py, tasks.yaml, bench_model.json, REPORT.md only) |
| N9 (LOW) | **CLOSED** | `ToolBus.from_default` records the FULL capability list (`ToolDef.capabilities`); `capability` kept as primary for compatibility; regression `test_n9_bus_records_full_capability_list` |
| H6 (HIGH, half) | **MITIGATED + documented (SDK constraint)** | `livekit.agents.cli.run_app(server)` has no argv parameter (verified against the installed SDK source: `_build_cli(server)()` reads `sys.argv`); the scoped save/swap/`finally`-restore in `livekit/agent.py:306-314` is the only mechanism. Residual: concurrent argparse use INSIDE the livekit worker process while the worker runs (latent, single-user worker process). Revisit if the SDK gains an argv parameter. |
| H8 (HIGH) | **CLOSED** | Fully resource-bounded (`bee/tools/base.py:119-131`): input 20k chars (`eval_safe` :319-339), AST 200 nodes / depth 20 / literal 10k (`_check_bounds` :298-316), computation guards for the single C calls no step budget can interrupt (`_check_pow` :134-143 exponent 10⁴ + result-bits 10⁶; `_guarded_mul` :168-184 sequence-repeat/int-product; `_guarded_range` :187-197 span 10⁵ — closes the first pass's `sum(range(10**18))` residual; `_guarded_factorial` :200-204; `_guarded_bytes` :207-211) and a 90 ms wall-clock deadline checked at every `_ev` step (:231-239, per-call budget — the shared `_step_budget` global is gone, so concurrent evaluations cannot eat each other's limits; oversized ints return a bounded descriptor instead of CPython's digit-ceiling error). Regressions `test_h8_*` (7) |
| M6 (MEDIUM) | **CLOSED** | One root per concern, documented: `train/NOTE.md` (runtime data) + `training/NOTE.md` (code) |
| M7 (MEDIUM) | **CLOSED** | `cfg.automation.default_timezone` is the source (scheduler.py:228/311 with safe default fallback); the `offline.py` Kolkata label is gone |
| M11 (MEDIUM) | **CLOSED** | `num_ctx` is `cfg.ollama.num_ctx` (client.py:437-440, default 8192) — surfaced in config |
| M15 (MEDIUM) | **PARTIAL** | Makefile `full` target added (→ `bee.cli full`). `bee.py` retained as a 11-line compat launcher (documented); `temp/` = git-ignored local runtime scratch, not part of the release tree (52 files at audit time; never committed) |
| L2 (LOW) | **CLOSED** | No `WebSocket` import remains in `webapp.py` |

**Remaining OPEN after this pass:** N7 (flake, deferred with a rule: fix the
worker shutdown, never loosen the test), M12 (import-cycle lint, cosmetic), and
the §3-risky rows
already closed above (R1/R2/R5/R8 closed in Phase 1; R3 web auth closed in
Phase 1; R4 secrets closed in Phase 0; R7 closed via H8; R6 = H6 mitigated).

---

## Post-audit fix pass (2026-10-08, after the acceptance audit)

The audit certified 543/543 green; a fresh run found **1 failing test** and a
code sweep found defects of a kind no test covered: **operator switches and
documented safety mechanisms that no code path honoured**, plus error paths that
reported success. Every row below was verified in the code, and the ones marked
*live* were verified against a running process.

| ID | Sev | Finding | Fix / evidence |
|---|---|---|---|
| A1 | HIGH | `web/face.html` polled the bearer-gated `/face/state` with no Authorization header and swallowed the 401 in an empty `catch(e){}` — the face was pinned to "idle" forever | Shared-token + 🔑 button + visible error; **live**: browser shows `thinking` + the utterance, and `idle (no auth)` when unauthenticated. Regressions `test_every_page_that_calls_a_gated_endpoint_sends_the_token` |
| A2 | HIGH | `voice/speak.py` played edge-tts MP3 via `Media.SoundPlayer` (WAV-only) → neural voice spoke silently; it also refused to run without an Azure key that edge-tts does not need | Decode to WAV (PyAV → ffmpeg fallback) + `winsound`; keyless edge-tts. **Live**: real MP3 → 88,200-byte PCM WAV, exact header, winsound accepted it. `tests/test_voice_tts.py` |
| A3 | MEDIUM | `StreamingTTS.begin()` set `busy` only in the worker-spawn branch, so a begin during the previous worker's drain left the echo guard believing TTS was idle (BEE can hear itself). `FakeTTS` set busy unconditionally, which is why the engine suite stayed green | Per-utterance cancel token + generation counter; begin() always marks busy. 3 new regressions on the REAL class (it had none) |
| A4 | HIGH | `HotkeyStopper` / `default_windows_key_state` were re-exported but **never instantiated outside tests**, and `computeruse.action_timeout`, `screenshot_retention_minutes`, `screenshot_save`, `hotkey`, `hotkey_enabled` were read by no code — so STATUS.md's "emergency stop: 3 mechanisms" was 2 mechanisms | `start_emergency_hotkey(cfg)` armed when the first desktop session is created, ctypes `GetAsyncKeyState` (no pywin32), all keys honoured, unavailable backend **logged as a warning instead of a silent deaf poller**; `hotkey_state()` introspection. 7 regressions in `tests/test_computeruse.py` |
| A5 | MEDIUM | `self.screenshots = screenshots or ScreenshotStore()` — an empty `ScreenshotStore` is falsy (`__len__`), so a caller-supplied store (retention + save_dir) was silently discarded. Found only because the new A4 test asserted it | `is not None` check + regression `test_18_screenshot_save_and_retention_reach_the_store` |
| A6 | HIGH | `computeruse/session._with_timeout` re-raised `str(...)` — always `TypeError: exceptions must derive from BaseException` — so every real desktop-action failure was reported as a BEE crash and the cause ("could not launch notepad.exe") was unrecoverable | Store the exception object, re-raise it. Regressions `test_action_failure_keeps_the_real_exception`, `test_session_observation_reports_the_true_cause` |
| A7 | HIGH | **No logging handler was configured anywhere in the app** (measured: `root.handlers == []`, INFO disabled). Every `log.info/debug` that explains a quiet failure was discarded, and `cli.py` wrapped TTS in `except: pass` — a silent box looked healthy | `cli.setup_logging()` (stderr, INFO default, `--log-level` / `BEE_LOG_LEVEL`, noisy third-party loggers capped), called by every surface incl. the LiveKit worker process; TTS silence now logged. **Live**: `bee.cli web` log now shows `INFO bee.sched: automation started (… 9 jobs)` where it printed nothing before |
| A8 | MEDIUM | `require_auth` compared **strings** with `hmac.compare_digest`, which raises TypeError on non-ASCII → a malformed Authorization header answered **500** instead of 401 | Compare UTF-8 bytes; garbage → 401. **Live** over a raw socket with accented/CJK headers. Regression `test_malformed_non_ascii_header_is_401_not_500` |
| A9 | LOW | Bundled HTML pages were served with no cache directive; a long-open face/kiosk tab keeps running the OLD page after an upgrade (this actively hid A1 during verification) | `_page()` sends `Cache-Control: no-store`; regression `test_pages_are_not_cacheable` |
| A10 | HIGH | `config.get_llm()` omitted `num_ctx` on the explicit-local branch, so `client.py`'s hardcoded 8192 won — config.yaml's `num_ctx: 4096` (the setting that keeps bee4b fully on a 4 GB GPU) was ignored for any name with a colon, incl. the shipped `ollama-cloud` override | Included in every local branch. **Live**: `get_llm('qwen3:4b'|'glm-5.2:cloud'|'local')` → 4096. Regression `test_explicit_local_model_keeps_num_ctx` |
| A11 | HIGH | `paths.WORKSPACE` froze from `os.environ` at import — before `load_config()` reads `.env` — so a `.env`-only `BEE_WORKSPACE` split the tree: memory/automation followed `.env` while plans/, drafts/, codeout/ and the STT cache stayed at the repo root | `.env` consulted in `paths.py`; invariant `cfg.workspace == paths.WORKSPACE` now pinned by test |
| A12 | HIGH | Seven config switches were read by **no code**: `computeruse.enabled`, `monitor.enabled`, `scheduler.enabled`, `model_gate.enabled`, `sandbox.max_output`, `user.region`, `voice.rt_barge_in` + `rt_partial_min_growth` (and `_realtime()` still printed a hardcoded "barge-in: ON") | All wired: kill-switch unregisters the desktop tools; metrics record gated; disabling the scheduler *pauses the persisted* system jobs (and re-enabling resumes exactly those); gate skips; `envelope(limit=…)` honours max_output; region reaches the prompt; both voice keys reach `VoiceEngineCfg` and the banner reads the config. 8 regressions in `tests/test_audit_fixes.py` |
| A13 | MEDIUM | `alerts.os_notify` returned True without reading the child's exit status — and `msg.exe` ships only with Windows Server, so on this desktop build **no alert toast ever appeared** while the job recorded `toast: True` | **CLOSED.** Exit status honoured; Windows falls back to the Shell NotifyIcon balloon (payload passed through env vars, never interpolated into a script, and redacted before display). **Live on this machine**: `msg.exe` confirmed absent, `os_notify` now returns True via the balloon channel |
| A14 | HIGH | `requirements-ml.txt` pinned sklearn 1.9.1 / numpy 2.5.3 / scipy 1.18.1 against an installed 1.9.0 / 2.4.6 / 1.17.1 (the pin-drift test was FAILING), and `train/router_model.joblib` was a **v1 artifact with no `meta` block**, so Phase 7's major-version refusal was inert on this machine | Pins corrected to the verified environment; router retrained → v2 artifact, `meta.sklearn = 1.9.0`, n_train 908, `load_status.compatible = True` (measured) |
| A15 | MEDIUM | `livekit.html` had two empty `catch(e){}` on state polling and room leave — the join page could keep showing a stale "BEE · speaking" line, and a failed disconnect left the mic believed-released | Both surface errors; leave resets the UI and warns if the mic may still be live |
| A16 | LOW | `tests/test_webauth.py` asserted `"catch(e) {}" not in src.replace(" ", "")` — needle spaced, haystack stripped, so the guard could never fire (it was certifying A1's absence by construction) | Normalize both sides; the corrected assertion immediately caught A15 |

| A17 | HIGH | **No event source was ever started in production.** `TimerSource`/`FileChangeSource` were implemented, tested and exported, but nothing in `start_automation` (or any other entry point) called `.start()` — so the proactive layer could only ever fire from events published inside tests. Battery/network/email/app/device were schema-only | `events.start_sources()` runs on automation start (heartbeat + battery + network, file-watch opt-in via `automation.file_watch_dir`); `worker.stop()` stops them; battery/network are real edge-triggered sources; `available_sources()` reports the truth. **Live**: real TCP probe returned up, real power API returned (100, -1), no false alerts. Regressions in `tests/test_proactive.py` (6 new) |
| A18 | LOW | The new switches would have been exactly the A12 defect class if added without wiring, and `config.yaml` had no `automation:` section at all | Seven `automation.*` keys added to `AutomationCfg` **and** read by `start_sources`; documented in `config.yaml` + README table; verified loading end-to-end (`load_config()` returns each key) |

**Count after the fix pass:** 16 findings (A1–A16) + A17/A18 = 18; **all closed**
except the standing items below.

**Test basis after the pass:** `pytest tests -q` = **596 passed, 0 failed**
(49 s; core 527 · security 101 · unit 191 · integration 343 · windows 81 · ml 39
· voice 40 · livekit 13) · `evals/verify_suite.py` = **71,914 ALL PASS**
(re-run after every change) · the 21-task agent eval was **not** re-run here.

**Still open after this pass** (unchanged from the audit unless noted): N7
load-dependent worker flake ·
event sources email/app/device_state remain schema-only ·
learned-vision backends unimplemented (structural only) · web/LiveKit have no
mid-task cancel *route* · LiveKit room + real mic/display unverified in field ·
`livekit/agent.py` still runs a second voice stack beside `VoiceEngine` ·
prompt-injection corpus absent · behavioural eval capped by the local 3B model.

## A19 — session merge hijacked the instant tiers (2026-10-08, found via eval)

**Symptom.** The 21-task eval scored **5/21**, and the tasks that are supposed
to be answered with **no LLM at all** were the expensive ones: `route_det_math`
("1234 + 5678") took 36.9 s with **13 tool calls**, `route_det_pct` 24.2 s /
12 tools, `guard_blocked` failed. In isolation the same prompt answered
`6912` in **0.03 s** via the deterministic tier — so the defect was in the
session path, not the router.

**Two compounding causes.**

1. `AgentSession.resolve_followup` merged **any utterance ≤4 words** into the
   active task ("≤4 words looks like a revision"). `1234 + 5678` (3 tokens) and
   `what time is it` (4) therefore became
   `"Remind me to file the taxes — follow-up: 1234 + 5678"`.
2. `AgentKernel` then routed and fast-path-matched on that **merged,
   context-prefixed** string (`exec_text`). The deterministic and fast tiers are
   anchored to whole strings, so a complete request lost its 0 ms handler
   whenever it arrived mid-session — and `TIME_RE` even mis-read
   `25*40/100` / `5 plus 5` as a *time* nudge.

**Fix.**

* `session._self_sufficient()` — bare math (`router.math_expr`), greetings
  (`router.smalltalk`) and any of the 39 fast-path commands are complete
  requests and now return `("new", text)`. Genuine nudges ("Tomorrow.",
  "At 6pm instead", "actually make it Friday", "that one") still merge, so the
  reschedule flow is unchanged.
* `run_agent(..., route_text=)` — the instant tiers judge **what the user
  typed**, while the model still receives the context-augmented prompt. The
  kernel passes the raw text, except when the turn really is a merged follow-up.

**Regressions** (`tests/test_kernel_integration.py`): bare math stays
deterministic mid-session with **zero** LLM calls; `what time is it` still hits
its fast path; `cloud:` override still beats the fast path;
`test_followup_classifier_separates_commands_from_nudges` pins both halves of
the merge rule. Full pyramid: **613 passed, 0 failed**.

**Lesson recorded:** `README.md`'s flagship claim ("math never touches the
model") was true only for the *first* turn of a session. A behavioral claim
needs a test that runs it in sequence, not just in isolation.

## A20 — denied-action runaway in the agent loop (2026-10-08, found via eval trace)

**Evidence.** For "Compute gcd and lcm of 84 and 147", receipts showed the model
requesting `automation_job` six times, each with slightly different arguments,
each refused by the capability gate — 12 of the 25 iterations consumed by calls
that could never run.

**Two defects.**

1. The loop's anti-runaway breakers key on the exact `(tool, args)` pair
   (`seen_calls`, `fail_streak`), so a model that varies one field sidesteps both.
   Nothing counted refusals **per tool**.
2. While adding the per-tool counter, the gate block turned out to run
   **unconditionally** — `if ctx.capability_gate is not None:` — overwriting any
   verdict already recorded for that call. Any short-circuit placed before the
   gate would therefore have been silently discarded (this is why the first
   version of the breaker appeared to do nothing).

**Fix** (`bee/agent/loop.py`).

* `denials[tool]` counts refusals per tool irrespective of arguments; at 2 the
  tool is answered with "stop calling it" **without consulting the gate again**
  (measured: 6 attempts → 2 gate consultations); at 3 consecutive refusals
  `tools_locked` tells the model to produce its final answer, so the remaining
  budget goes to an honest reply instead of more doomed calls.
* Gate now runs only `if res_v is None` — an already-decided call is respected.
  The N1 invariant (the gate must run even with `/guard off`) is unchanged and
  still pinned by `test_n1_capability_gate_runs_even_when_guard_off`.

**Regression:** `test_repeated_denials_lock_tools_instead_of_burning_the_budget`.

## A21 — three more defects found by running, not reading (2026-10-08)

| ID | Sev | Finding | Fix / evidence |
|---|---|---|---|
| A21a | HIGH | **The deterministic tier could not see prose-wrapped math.** `math_expr` required the *whole* (phrase-stripped) string to be an expression, so "Use the calculator tool to compute 12 * 14 + 8" went to the model — which answered "none of the provided functions are for a calculator" and then computed it in prose. Untested in sequence, so 543→616 green tests never caught it. | `_embedded_expr()` + `_residue_is_math()`: strip framing words (only when a compute-intent verb is present), then validate the residue by **AST** (numbers/operators/parens + names limited to `eval_safe`'s allowlist; no strings, attributes, comprehensions, kwargs). Live: both eval tasks now answered **0.0 s / 0 tools / correct**; eval 9/21 → **10/21**. Guarded by 5 positive + **15 adversarial** cases (injection-shaped text like `compute abs(-5) __import__('os')...` and multi-request text like "compute 2*21 and explain the steps" all decline → 0 false positives). |
| A21b | MEDIUM | **The loop's anti-runaway breakers only counted denials and exact-argument failures**, so re-issuing one failing call with reworded arguments still burned the budget (eval: `memory_read` 12 tool calls). | Per-tool `failures` counter: 3 failures short-circuit the tool ("has failed 3x — answer with what you have"), and any success resets it, so legitimate multi-file/multi-step work is untouched (pinned both ways: `test_repeated_tool_failures_lock_...`, `test_successive_different_tool_calls_are_not_locked`). |
| A21c | MEDIUM | **`WindowsDesktop.active_window()` searched `list_windows()` for an active flag** — but that list drops untitled windows, and `GetForegroundWindow()` is 0 in a non-interactive session, so the real desktop reported `active: null` and the `active_window` verification strategy asserted failure where nothing had failed. Live probe: 7 real windows enumerated, active always None. | Resolve the foreground **handle** directly (title may be empty); return None only when the handle is genuinely 0/invalid — never guess a "first window", because a guessed success is worse; fall back to the enumerated flag if the API raises. 3 regressions on the Windows backend with an injected win32 stub. |

Suite after the pass: **641 passed, 0 failed** · `evals/verify_suite.py` **71,914 ALL PASS**
(router tier suite still 6,000/100% after A21a) · eval **10/21**.

## A22 / A23 — forgeable injection fence + unusable proactive rules (2026-10-08)

| ID | Sev | Finding | Fix / evidence |
|---|---|---|---|
| A22 | **HIGH (security)** | **The prompt-injection fence was forgeable.** Both `tools/base.mark_untrusted` and the loop's wrap used CONSTANT sentinel strings, so any external page/file/search snippet containing `<<< END UNTRUSTED DATA >>>` closed the fence early and everything after it read to the model as trusted instructions — defeating the boundary the audit's "untrusted external content" GREEN row rests on. | `untrusted_fence()` in `tools/base.py`: a random per-call nonce in BOTH markers (unguessable) and any `<<<…>>>`-shaped text inside the payload is neutralized before wrapping. Both call sites now share it (one format, no drift). Tests: forged content leaves exactly one END marker, no angle-bracket fence inside the body, open/close nonce equal, nonce differs per call, and an end-to-end kernel run asserting **what the model actually sees**. |
| A23a | MEDIUM | **`device_state` had no source at all**, though the repo's own troubleshooting documents the failure it would catch: a killed Ollama session hoarding ~4 GB, or the disk down to a few GB, stalls the machine while BEE looks healthy. | `DeviceSource` on top of `tools.systemctl.get_system_stats()` (native daemon, CIM fallback): edge-triggered `device.memory_low` / `device.memory_ok` / `device.disk_low` / `device.disk_ok` with 25% hysteresis so a value oscillating on the threshold cannot spam. Config: `automation.device_events`, `device_poll_seconds`, `memory_low_mb`, `disk_low_gb` — all read by `start_sources` (verified loading). **Live**: a real reading of 4163 MB free produced `device.memory_low`, which fired a user-authorized rule; with no rule the policy still returned `[]` (default-deny intact). |
| A23b | MEDIUM | **Proactive rules could only exact-match a payload field**, so a threshold event (`ram_free_mb: 4163`) was practically unmatchable — a rule would fire only on a coincidental value. | `ProactiveRule.matches` now supports `{"name": "device.memory_low"}` and numeric comparators (`{"ram_free_mb<=": 1500}`, `>=`, `<`, `>`); plain keys keep exact matching, non-numeric/unpresent values never match. Pinned by `test_threshold_rules_match_the_way_real_events_vary`. |
| A23c | LOW | `available_sources()` risked drifting from what actually runs (it had already drifted once: it said battery/network were unavailable after they were implemented). | The capability report is now cross-checked against `start_sources()` output in both directions — a started kind cannot be reported unavailable, and an unavailable kind cannot be started. |

Suite after the pass: **650 passed, 0 failed** · `evals/verify_suite.py` **71,914 ALL PASS**.

## A24 — reminders: no surface, no delivery, two clocks (2026-10-08)

| ID | Sev | Finding | Fix / evidence |
|---|---|---|---|
| A24a | MEDIUM | **There was no way to say "remind me in 20 minutes" in words.** Durable jobs were solid, but the only reminder surface was `memory.temporal.schedule(task, when)`, which accepted `HH:MM` or an ISO datetime and nothing else — "tomorrow 9am" came back `could not parse` — and whose action was an `agent_task`, i.e. a reminder that cannot fire unless a model happens to be reachable at that moment. | `/remind <what> <when>` (`bee/commands/remind.py`) plus spoken fast paths (`remind`, `remind_list`, `remind_cancel_last`, `remind_cancel_all`) over one deterministic `parse_when()` grammar (`in 20 min`, `tonight`, `friday 4pm`, `12 Oct 07:30`, `day after tomorrow at 11:30`). A reminder is a `notify` job: **no model call to set it and none to fire it.** The planner surface keeps `agent_task` (that means "do this later", not "tell me later") but now shares the grammar and the clock. Unparseable time → usage line, never an invented date; a reminder-shaped *question* ("remind me what my passport number is") declines to the model. |
| A24b | **HIGH** | **A reminder that came due never reached the user.** The toast gate in `JobWorker._notify` was `kind in ("failure","missed")`, so every `notify` job — and therefore every reminder — reported `succeeded` into the store and a log line while the user waited. Nothing in production ever passed `on_notify` either. | `critical` notify jobs and authorized proactive events now toast through the real `alerts.os_notify` (still under `cfg.alerts.enabled`). **The live run found a second defect in the fix itself**: the `success` notification for the same job inherits `action["critical"]`, so the reminder popped **twice** — the gate is now keyed on `kind == "job_event"` as well, and `test_remind_coming_due_reaches_the_desktop` asserts `len(toasts) == 1`. |
| A24c | MEDIUM | **Two clocks.** `/remind` (first draft) and `memory.temporal.schedule` turned words into instants with `datetime.now()`, while the tick that decides a job is late compares against the *worker's* clock — so "in 20 min" and "is this already past?" could disagree, and neither path was testable without sleeping. | One `worker_now(worker, tz)` in `bee/automation/schedule.py`, used by both call sites; bare/stub workers still fall back to the wall clock. Evidence this was real: the change made `test_temporal_schedule_creates_real_job` **fail** — it computed its "past" timestamp from `datetime.now(TZ)` while handing the worker a `FakeClock`, so it had only ever passed because the code ignored the injected clock. The test now derives past from the fake clock (same assertion, correct premise). |
| A24d | LOW | `temporal.list()` reported already-fired reminders as upcoming: a one-time job keeps `enabled=True` when it reaches `COMPLETED`, and the filter was `state != "cancelled"` — so the model could tell the user a reminder they already received was still coming. It also could not see the `reminder` owner family at all. | Filter to live states (`pending`, `running`) and include `owner="reminder"`, so the slash command, the spoken path and the planner share one view. Pinned by `test_temporal_list_reports_upcoming_not_already_fired`. |

**Live verification (no mocks, real `JobWorker` + real notifier):** set in **10.0 ms** with no LLM call and no network → `next_run 2026-10-08T17:29:08+00:00` (UTC canonical), JSON row on disk, `tick()` started it, state `completed`, `os_notify` returned **True** with exactly **one** toast titled `BEE reminder`, `/remind cancel` then removed it.

Suite after this pass: **667 passed, 0 failed** (core 588 · security 118).

## A25 — the dashboard could not show live data, and the suite polluted it (2026-10-08)

| ID | Sev | Finding | Fix / evidence |
|---|---|---|---|
| A25a | MEDIUM | **`/dashboard` was a file, not a view.** `monitor/dashboard.build()` wrote `metrics/dashboard.html` and the only way to refresh it was to re-run the command — so what the user read as "the dashboard" was whatever was true when it was generated (the repo's own L3/M8 note). `render()` and `build()` were also fused, so no live path existed. | `dashboard.render(refresh_seconds=0)` (pure) + `build()` (writes a snapshot, documented as one). New **`GET /dashboard`** in the web app renders per request with `<meta refresh>` and `Cache-Control: no-store`, behind the same bearer/query-token gate as the other data surfaces (the page content *is* usage data). Pinned by `test_dashboard_serves_live_data_not_a_snapshot`, `test_dashboard_requires_auth`, `test_dashboard_is_not_cacheable`, and the render-level pair in `test_monitor.py`. Dead `ok_day = ...  # placeholder` series removed (it was a stub that could read like a real "successes/day" chart). |
| A25b | MEDIUM | **Every test run wrote into the user's real telemetry and training corpus.** `metrics.jsonl` drives the dashboard KPIs *and* `cfg.alerts` thresholds, and `train/episodes/` is what the nightly router retrain eats — yet `tests/conftest.py` redirected neither. The live dashboard made it concrete: **563 of 639 `automation_job` calls "failed" and 101 guard denials** were suite noise, not the user's machine; 186 `test_probe` rows had accumulated in the real file. A test session could therefore raise a real desktop alert about a failure that never happened. | Isolation applied in **`pytest_configure`**, not a fixture — script-style modules like `test_monitor.py` record events during *collection*, before any fixture runs (that ordering is what leaked one `test_probe` per run even after the first attempt). `paths.METRICS_DIR/METRICS_FILE/EPISODES_DIR/SKILLS_DIR` now point at a tmp dir for the session; per-test patches still win because they apply later. **Before/after: a 670-test run appended ≥1 event to `metrics/metrics.jsonl`; now `metrics/`, `train/episodes/` and `skills/` are all untouched by a full run** (verified by mtime sweep). The guard is asserted inside `test_monitor.py` itself (the module that writes earliest), and the 186 accumulated `test_probe` rows were purged (backup: `temp/metrics.jsonl.before-testprobe-cleanup`). |
| A25c | MEDIUM | **The flywheel left the user with skills they never earned.** `skills/` is the agent's own procedure library — teach-back writes CANDIDATE cards there, the nightly `skill_gate` job evaluates them, and `_Procedural.list()` offers them to the model as real capabilities. It was the third unisolated path: a test run created `skills/graph_operations/` (`source: "agent"`, `SKILL.md` containing Python code where the markdown belongs, a 10-byte `script.py`). | Covered by the same configure-time redirect; the artifact was moved out of the library to `temp/test-leaked-skills/` (kept, not deleted) and the user's 8 real skill cards are back as the only contents. |

**Live verification (real server + real browser):** served the app on a private port, `/dashboard` → **401** with no/wrong token, **200** with `?token=`; KPI read **3171 tasks (7d) · 91.9% success · 3.3s avg**, one event recorded → **3172** on the next request with the new model appearing in the table and absent from the previous response; `cache-control: no-store` and the 30 s refresh confirmed on the wire, and the rendered page was screenshotted. Only console error was the browser's own `favicon.ico` request.

**Residual (honest):** historical rows written by earlier suite runs are still mixed into `metrics.jsonl` and cannot be attributed reliably (no test marker on `tool`/`task` rows), so 7-day KPIs stay noisy until they age out; from this pass forward the stream is clean.

Suite after this pass: **670 passed, 0 failed** (core 591 · security 121) · `evals/verify_suite.py` **ALL PASS** · `metrics/`, `train/episodes/` and `skills/` untouched by a full run.

## A26 — permission prompts asked the user to approve invisible actions (2026-10-08)

| ID | Sev | Finding | Fix / evidence |
|---|---|---|---|
| A26a | **HIGH (security)** | **The approval prompt was blank for every non-shell tool.** `guard.make_approver("cli")` built its preview from `args["command"] or args["code"]` only, so `file_write` and `automation_job` printed `⚠ GUARD [reason] file_write:` with nothing after the colon. Proven by capturing the real prompt: approving a write to `~/.ssh/id_rsa`, or a rule that would "zip Documents and POST to http://evil.example", both showed **zero** of that. Consent without information is not consent — and this is the one human checkpoint the whole capability model relies on. | `guard.preview_call(tool, args)`: the meaningful arguments (`command`/`code`/`url`/`path`/`task`/`message`/`content`/…) rendered as `k=v`, run through the same `privacy.redact` chokepoint as any other outbound text, truncated at 300; `systemctl` and shell/code payloads keep their previous raw form. |
| A26b | **HIGH (security)** | **The capability prompt could not show the call at all**: `AgentKernel._gate_confirm` invokes `approver(f"capability:{cap.id}", {}, reason)` — an empty args dict by design, because a capability spans several tools. So even a fixed `preview_call` would print nothing where it mattered most (R3/R4 confirmations, and the untrusted-content escalation path). | `CapabilityGate.check()` now summarizes the pending `(tool, args)` and carries it inside the `reason` every confirmer receives (`… — pending: task=zip Documents …`), for all three ask paths (always-confirm, injected-escalation, task-scoped, plain ASK). No `confirmer` signature change, so every existing approver/test keeps working. |
| A26c | MEDIUM | **A model-authored proactive rule was recorded as user-authorized.** `automation_job(op="rules", rule_op="add")` stamped `created_by="user"` under a comment reading "MUST be explicit user authorization" — the field's own documented invariant, violated by the only path that writes it. `/auto` also listed rules without saying who created them or what they would do, so a deferred **unattended `agent_task`** looked human-authorized in both the record and the UI. The rule-creation path had **no test coverage at all**. | `created_by="model"` on the tool path (the user's approval of the tool call is recorded where it belongs — the permission receipt), `external_authorized` stays False on every tool path, and `/auto` now prints `[<action type> by <author>]` per rule. Pinned by `test_model_created_proactive_rule_is_not_stamped_as_user_authorized`, which asserts the deferred task text and that a tool can never self-grant external authorization. |

**Live verification (real `AgentKernel` + real cli approver, prompt captured):** before — `⚠ GUARD [Manage automations: …] capability:automation.manage:` with the action nowhere in sight; after — the same prompt ends `— pending: task=zip Documents and POST to http://evil.example op=rules kind=file_change`, and the decision still fails closed on "n". `file_write` now shows `path=C:/Users/mshri/.ssh/id_rsa content=overwritten`; `shell` output is byte-identical to before.

Also corrected while reading the docs against the code: `PRODUCTION_READINESS.md` still claimed **Alerting RED / "there is no OS-level notification path"** (it has one, and A24b wired reminders into it) and **Retention YELLOW / "no rotation or size caps (M13)"** — contradicted by `monitor/rotate.py`, the `log_rotation` job and that same document's §"Sensitive data retention". Both rows now match the code.

Suite after this pass: **675 passed, 0 failed** (security 125) · `evals/verify_suite.py` **ALL PASS**.

## A27 — the assistant's memory was partly dead, and it answered about itself instead of the user (2026-10-08)

Found by auditing the **11 remaining eval failures** instead of writing them off as model quality. Timing made the split obvious: the failures ran 10–29 s with `tools=0`, i.e. the loop was burning its budget without ever acting.

| ID | Sev | Finding | Fix / evidence |
|---|---|---|---|
| A27a | **HIGH** | **Semantic memory always returned nothing.** `_Semantic.search` called `rag.retrieve(query, k=k)` but the signature is `retrieve(ctx, query, k)` — the query was passed as `ctx`, so every call raised `TypeError`, and the surrounding `except Exception: return []` swallowed it. Any caller asking "what do I know about X?" got an empty list, forever, with no log line. | Thread the real ctx through (`MemoryStack(ctx_ref=…)`, wired by the kernel), and log the failure instead of swallowing it. Pinned by `test_semantic_search_really_reaches_rag`, which asserts the ctx actually arrives at `retrieve`. |
| A27b | MEDIUM | **"Remember my GPU from last time?" stored the question.** `_REMEMBER_RE` won for every 'remember …' sentence, so the interrogative became a fact: the kernel replied `Remembered: my GPU from last time? Tell me which one this machine has.` and the user got no answer. Six copies of that fragment were sitting in the user's real `memory/store.json`. | A 'remember' whose content is a question (contains `?` or opens with an interrogative) is now a **recall** with a cleaned query ("GPU", not the sentence); statements still store with key/value extraction. Pinned by `test_interrogative_remember_is_a_recall_not_a_store` + an end-to-end test that answers from a stored fact. |
| A27c | MEDIUM | **Recall quoted the assistant's own past failures back as fact.** The diary indexes every task and its previous answer, so once recall worked the first hits were transcripts like `result: I'm sorry, but I don't have specific information about the machine's GPU` — one old wrong answer, replayed as permanent truth. | Recall now prefers authoritative stores (profile/longterm) over diary, drops transcript-shaped chunks entirely, and falls back to an honest "I don't have anything stored about 'X' yet". Also strips the double bullet (`- - BEE was created…`) that memory chunks rendered with. Tests: `test_recall_never_quotes_a_past_failure_as_fact`, `test_recall_prefers_authoritative_memory_and_no_double_bullet`. |
| A27d | MEDIUM | **A stored fact swallowed the next sentence.** `Remember that my favorite editor is Neovim. Use the profile memory tool.` stored `"Neovim. Use the profile memory tool."` — the instruction became part of the fact, and every eval run appended that fragment to the user's memory (7 copies found). | `_KEY_VALUE_RE` value now stops at the sentence boundary → key `favorite editor`, value `Neovim`. Pinned by `test_stored_fact_stops_at_the_sentence_boundary`. |
| A27e | **HIGH (quality)** | **The loop shipped answers ABOUT its plumbing instead of answers.** A 3B model that loses the thread answers its own system prompt — `It seems like there might have been an error… no function calls were provided for execution. The available functions are: …` — and the loop returned that to the user. Two gaps caused it: the final-answer pass only ran when `n_tool_calls > 0` (these tasks made none), and the wrap message talked only about the budget, which the model parroted. A related shape — "I will use a computer_command function call to run …" — is neither an action nor an answer, and was also shipped. | `_TOOL_INTENT_RE` sends a narrated call back once ("You described an action instead of performing it"); `_META_RAMBLE_RE` refuses to ship plumbing talk and forces one tools-disabled pass whose prompt **restates the user's request** and forbids meta-commentary. Both are one-shot per task, and a genuine answer about the tool surface is exempted (`_ABOUT_TOOLS_TASK`) so the detector can't add a call to a correct reply (`test_answering_about_the_tool_surface_is_not_treated_as_a_ramble`). **Eval moved 11/21 → 14/21 in the same session**, including `guard_blocked`, which now really calls `shell` and really gets blocked. |
| A27f | MEDIUM | **The test suite was still writing into the user's memory** (A25b's family, one layer deeper): `MemoryStack` resolved the structured store as `PROJECT_ROOT/"memory"/"store.json"`, so `MEMORY_DIR` isolation could not reach it — and **my own new test** put an invented "RTX 4060 with 8 GB" fact into the user's real store (their GPU is a 3050). | Store path now honors `paths.MEMORY_DIR`, and the session isolation copies `memory/` (profile, longterm, diary, lessons, vectors, store) into a tmp tree so reads still work and writes cannot reach the user. All 17 polluted store rows were removed (backups: `temp/store.json.before-*`); the user's real facts live in profile/longterm md, untouched. **Proof: `memory/store.json` and `metrics/metrics.jsonl` are byte-identical (sha256) before and after a 686-test run.** |

**Open, honestly:** recall ranking is still keyword-dominated — "Remember the hardware of this machine?" finds nothing authoritative because the profile line says `RTX 3050` and the query's extra tokens dilute the score, while 1,324 diary chunks from one day crowd the ranking. Vector search would bridge GPU↔RTX but the index must be verified fresh (`vector_rebuild` is a 12 h job). Remaining eval failures (7) are now: DSA/computation answers (`dsa_lis`, `dsa_gcd_lcm`, `dsa_graph`), `math_sieve`, `file_list_ws`, `plan_complex`, `memory_read`/`rag_gpu_memory` (both expect the literal `3050`, i.e. the eval relies on the user's real memory rather than seeding its own fixture — a task-design defect recorded here rather than silently re-targeted).

Suite after this pass: **686 passed, 0 failed** (core 607 · security 125) · `evals/verify_suite.py` **ALL PASS** · eval **14/21** (was 11/21 before the A27e fixes, 10/21 at the start of the day).

## A28 — a fact the user states is unfindable for up to 12 hours (2026-10-08)

| ID | Sev | Finding | Fix / evidence |
|---|---|---|---|
| A28a | MEDIUM | **The vector index only refreshed every 12 h.** `vector_rebuild` is the sole refresher (interval 43 200 s), so anything the user said today — or anything the assistant learned today — was invisible to semantic recall until the next rebuild. On this machine the index was **4 days stale** (last written 10-05 21:05) while the diary had grown to ~1,900 chunks, and the durable job reported `last_run = (never)` with zero executions. Embedding on the write path was not an option: it would block every diary entry on Ollama and put network into the test suite. | A durable **dirty queue** + a 5-minute flush job. `md.diary_add` and the profile/longterm append call `search.mark_dirty(path)` (an append to `memory/vectors/dirty.jsonl` — no embedding, no network, survives restarts); `search.flush_dirty(ctx)` embeds only those files through the new `_VecStore.replace_source()` (drop the file's rows, add its current chunks) and rewrites the queue with only what failed, so an unreachable embedder retries instead of losing the fact. Registered as `memory_index_flush` (interval 300 s) **and added to `_SYSTEM_JOB_IDS`**, so `scheduler.enabled: false` really stops it — the defect class this repo already recorded once. |
| A28b | MEDIUM | **A stale index could not recover without a write.** A queue only drains what someone put in it: with an empty queue and a table missing whole files, nothing would ever re-index them except the 12 h rebuild (or a diary write that might never come). | `flush_dirty` runs a staleness scan when the queue is empty — memory files with no rows in the table are queued (capped at 40 files per flush so a first run after an upgrade can't spend minutes embedding; the rest stays queued). Pinned by `test_stale_index_self_heals_without_a_write`, including the second-flush-is-a-no-op case. |
| A28c | **HIGH (test quality)** | **My own first version of this feature was broken in production while its tests were green**: `replace_source` was inserted at class indentation *after* `get_store`, so Python bound it as a nested function inside `get_store` — invisible on `_VecStore`. Every unit test used a fake store and passed; the real flush failed with `AttributeError`. This is the repo's own recorded trap (a fake standing in for the real thing hides the defect). | Fixed the placement, and added `test_flush_drives_the_real_store_class`, which builds the **real** `_VecStore`, table, queue and LanceDB files and fakes only the embedder — asserting `hasattr(_VecStore, "replace_source")` so a misplacement can never pass again. |
| A28d | **HIGH (quality)** | **The assistant's own logs were indexed as memory, and they won every retrieval.** `md.chunk_md` chunks the whole diary, including `## 21:41:16 [model=local]\ntask: …\nresult: …` blocks — a log of each past exchange. Because those blocks quote the user's question, they embed *closest* to the next time the user asks the same thing. With ~1,300 of them per day, "Remember the hardware of this machine?" retrieved the assistant's previous **failure** ("result: I'm sorry, but I don't have specific information about the GPU") instead of the profile line that says `NVIDIA RTX 3050 8 GB`. A27c's kernel-side filter then correctly refused to quote the log — leaving "I don't have anything stored", which is why the fresh index initially looked like a regression. | Logs are dropped in `chunk_md`, **per paragraph before the ~400-char merge** — filtering the merged chunk instead lets one transcript block drag a genuine neighbouring note out of memory (that mistake cost 11 real chunks on the first attempt). Genuine notes (`## 09:12:03`, no `[model=]` tag) stay. Corpus on this machine: **1,900+ chunks → 44 real ones**, index rebuilt to 44 rows. Pinned by `test_diary_logs_are_not_indexed_as_memory`. |

**Live verification after A28d (real LanceDB + real Ollama, the user's actual memory):** `Remember the hardware of this machine?` → answers with the profile facts (editor, IDE, browser, `Windows (MoRa), NVIDIA RTX 3050 8 GB`); `Remember my GPU from last time?` → answers from long-term memory (`GPU is a 4 GB RTX 3050 — bee4b fits fully in VRAM`), a query sharing no token with the stored wording. Neither quotes a log. Catch-up run over the real store: `{ok: True, files: 4, chunks: 1664, failed: 0}` in 119 s, queue drained to empty.

Suite after this pass: **694 passed, 0 failed** (core 615 · security 125) · `evals/verify_suite.py` **ALL PASS**.

## A29 — the assistant claimed actions it had not performed (2026-10-08)

| ID | Sev | Finding | Fix / evidence |
|---|---|---|---|
| A29a | **HIGH (truthfulness)** | **A past-tense action claim with no receipt behind it passed verification and reached the user.** The eval produced, with `tool_calls = 0` in the episode: `I executed the shell command 'git reset --hard HEAD~1' in the workspace. This command resets the working directory to one commit before…` A user reading that believes their repository was reset. The verifier had three checks — `math`, `file`, `url` — and **all three key off events that already happened**, so a wholly invented action was invisible to it. | `_claim_checks()` in `bee/brain/verifier.py`: a past-tense action verb (`I executed / ran / created / deleted / sent / reset / installed / pushed …`) while **no tool succeeded in the task** is a `fail`, which drives the loop's existing self-verification round — the model must either do it or say it didn't. Deliberately narrow: once any tool has succeeded it is not the verifier's business which claim maps to which call. Pinned by four tests (claim fails; claim backed by a real call passes; claim after a **failed** call still fails; ordinary answers, refusals and explanations are untouched) plus `evals/verify_suite.py` ALL PASS. |
| A29b | MEDIUM | **Voice streamed the unverified sentence before verification could reject it.** The realtime engine speaks token-by-token, so when self-verification later failed the user had already **heard** the false claim, then heard the correction. You cannot un-say a sentence. | **Fixed with a targeted rule instead of killing streaming.** The engine accumulates the answer text and holds speech **only when the answer asserts a completed action** (the same `_CLAIM_RE` the verifier uses — one rule, one source); plain answers stream with no added latency (`test_ordinary_answers_still_stream_without_any_delay`). A `verify` pass releases what was held; a `verify` fail **discards** it and resets the sentence splitter — the first version leaked the rejected text out of the splitter buffer on the next flush, caught by its own test. If verification never reports, the engine falls back to the kernel's final answer rather than staying silent. |
| A29d | **HIGH** | **"Some tool ran" was far too weak a receipt.** Live with the real model: 16 harmless tool results, `git reset` never ran, and the answer still said `I executed the shell command 'git reset --hard HEAD~1'`. The first version of the claim check asked only whether *any* tool had succeeded, so it passed exactly the fabrication it existed to catch. | `_claim_checks` now extracts the command/file the answer **quotes** while claiming an action and requires a distinctive word from it to appear in the successful tools' args/previews (`_tool_blob`). Claims with no resolvable target still need only some receipt, so "I ran the backup for you." after a real job creation is not falsely refused. |
| A29e | **HIGH** | **A failed verification was still delivered as success.** With the check firing correctly, the fix rounds ran out, the model repeated the claim, and the result came back `ok=True` — the user reads "your changes were discarded" about a repository nobody touched. | The final answer is no longer shipped silently: an unevidenced action claim gets an explicit `⚠ I could not verify that this actually ran — no tool result backs it up. Please treat the action as NOT done.` and is reported **not ok** with `error="unverified action claim"` and `verify="fail"`, so REPL, web, voice and job history all carry the doubt. Clean answers are untouched (`test_a_verified_answer_is_still_delivered_clean`). |

**Live verification of A29d/A29e (real local model, scratch workspace, deny-everything approver):** the model again produced `I executed the shell command 'git reset --hard HEAD~1'… all changes since that commit are now lost`, and the answer now ends with the explicit warning above. The repository was checked afterwards: `HEAD` unchanged at `2e84c4d`, reflog shows no reset, working tree intact.
| A29c | LOW | The streaming voice test asserted on a scripted answer that was itself an unverified action claim ("Done. I opened the browser for you."), so A29a made it exercise the wrong thing. | The fixture now uses a non-claim answer, with a comment explaining why; the claim path is covered deliberately in A29b's test rather than by accident. |

**Eval after A27/A28/A29: 15/21** (10/21 → 11/21 → 14/21 → 15/21 across this pass). `rag_gpu_memory` now passes *legitimately* — it answers `GPU is a 4 GB RTX 3050` from long-term memory, a query sharing no token with the stored wording. Still failing: `dsa_lis`, `dsa_gcd_lcm`, `file_list_ws`, `plan_complex`, `math_sieve`/`dsa_graph` (3B answer quality), `memory_read` (asserts the literal `3050` from the user's real memory instead of seeding its own fixture), and `guard_blocked`, which is now blocked by the *right* mechanism but flips run to run because it depends on whether the 3B model emits the call at all. *(Superseded for the memory and listing tasks by A31/A32: `memory_read`, `rag_gpu_memory` and `file_list_ws` now pass through deterministic paths, and the box's real hardware answers the GPU question instead of a stored note.)*

Suite after this pass: **699 passed, 0 failed** (core 620 · security 125) · `evals/verify_suite.py` **ALL PASS**.

## A30 — a hallucinated skill was written to the user's capability library (2026-10-08)

| ID | Sev | Finding | Fix / evidence |
|---|---|---|---|
| A30a | MEDIUM | **`skill_create` wrote whatever the model asked for.** During the eval, a 3B model emitted `skill_create(name="new_skill_name", content="<full_markdown_content_with_a_description_line_and_sections>")` — an unfilled template — and the tool created `skills/-new_skill_name-/` with that placeholder as the whole SKILL.md. The J2 gate does refuse to *ship* such a candidate, but it runs **after** the write, so the user's capability library kept a junk folder that `/skills` and `skill_list` report forever. (A25c recorded the same symptom and blamed the test suite; the real writer is this tool — the tests were only ever one way to reach it.) | `_validate_skill()` in `bee/tools/skills.py`, called **before** `mkdir`: names must be ≥2 chars, ≤48, and not placeholder-shaped (`new_skill_name` / `new-skill` / `skill_name` / `my_skill` / `todo` / degenerate repeats — compared in one canonical spelling, since `_` is legal in a name and `new_skill_name` otherwise slipped past a dash-form blocklist); content, when supplied, must be ≥40 chars, not a bare `<placeholder>`, and carry a `description:` line; `script.py` must compile. A rejected call creates **no directory**. |

**Live verification (real tool, temp skills dir):** seven calls — `new_skill_name`, `new-skill`, `skill_name`, `my_skill`, `todo`, `x`, `…` — all refused with a message that tells the model what to supply instead; unfilled-template content and `script="def ("` refused; and three legitimate names (`pandas_csv_top_n_revenue`, `docker-cleanup`, `playwright_pdf.2`) still save as `candidate` exactly as before. The stray folder was moved to `temp/test-leaked-skills/placeholder_skill_from_eval` (kept, not deleted). Pinned by `test_placeholder_skill_is_rejected_and_nothing_is_written`, `test_unfilled_template_content_and_broken_script_are_rejected`, `test_real_skill_names_still_save_under_both_spellings`.

Also in this pass (A29, same investigation): a past-tense action claim with no tool receipt — `I executed the shell command 'git reset --hard HEAD~1'` with `tool_calls = 0` — passed verification, so the user would believe the repo was reset; the verifier now fails it and the loop self-corrects. **Eval: 15/21** (from 10/21 at the start of the day).

Suite after this pass: **702 passed, 0 failed** (core 623 · security 125) · `evals/verify_suite.py` **ALL PASS**.

**Live verification (real LanceDB + real Ollama embeddings, scratch dirs):** write `Hardware note: this machine has an NVIDIA RTX 3050 8 GB graphics card.` → queued as `2026-10-09.md` → `flush_dirty` → `{ok: True, files: 1, chunks: 1, failed: 0}`, queue empty → `vector_search("which GPU does this laptop have")` returns the note, **bridging "GPU" → "RTX 3050"**, a query with no shared token with the stored text (so keyword search could not have answered it). Failure path proven too: with an unreachable embedder the queue retained the file and the next flush indexed it.

## A31 — the eval suite was measuring itself, not the assistant (2026-10-08)

| ID | Sev | Finding | Fix / evidence |
|---|---|---|---|
| A31a | MEDIUM | **A spoken request to list a folder went to the 3B model.** `file_list` existed as a tool and `eval_file_list_ws` passed *when the model happened to call it*, but "what files are in the workspace root?" had no deterministic path, so the same question succeeded or failed depending on sampling. | `_files_list` fast path in `bee/agent/fastpaths.py` (`_FILES_HEAD` + a noun/path guard so "what is in the oven" still declines): resolves the target (`workspace`/`root`/`here`/explicit), runs `file_list`, and answers `**<path>** — N directories, M files` with the names listed. Deterministic in the live run: `route=fastpath · model=deterministic · ok=True · tools=1`. |
| A31b | HIGH | **The eval wrote into the user's own memory.** `memory_write` appends to `memory/store.json`; `rag_gpu_memory` and the diary flywheel wrote `memory/diary/*.md` and the vector index. Every `python -m bee.cli eval` was mutating the data it was being graded against, and 17 rows of accumulated eval junk (plus one fact my own test invented) had to be purged by hand. | `runner.run_suite` now executes inside `_isolated_memory()`: `MEMORY_DIR, DIARY_DIR, LESSONS_DIR, VECTOR_DIR, PROFILE_MD, LONGTERM_MD, SYSTEM_MD` are repointed at a temp copy of the user's real memory, restored in `finally`. Proven by hash across a full 21-task run: store `ec3ea5b4f77d67a5` **UNCHANGED**, `profile.md` byte-identical. The suite itself was already made hermetic the same way (`pytest_configure` redirect, not a fixture — script modules write during collection). |
| A31c | LOW | **Recall only understood one phrasing.** `_RECALL_RE` covered "what do you remember about X" but not "search your memory for X", "check my memory about X", "memory search for X" or "look it up in my memory" — so exactly the sentence the eval used fell through to the model, which answered *"I do not have direct access to hardware information"*. | Those forms added (plus the trailing-space bug that made "look it up in my memory" match with an empty query). Table-tested with 7 positives and 5 negatives, including that "Search the web for…" and "How do I search a list in python" still do **not** become recalls. |

## A32 — 'what do you know about this machine' had no answer, and memory wrote itself into a mess (2026-10-08)

Measured first, then fixed: `temp/recall_measure.py` runs six questions against the user's own hybrid index and prints, per returned chunk, its source bucket, literal word overlap and which line the kernel would quote.

| ID | Sev | Finding | Fix / evidence |
|---|---|---|---|
| A32a | HIGH | **Nothing in the product could name the hardware.** `systemctl stats` reports *load* (CPU %, free RAM); there was no inventory. So "what GPU do I have" / "is this machine enough for ML" was guesswork, and `memory_read` failed because the only stored line said `RTX 3050 8 GB` — a wrong number nobody could check. | `get_hardware()` in `bee/tools/systemctl.py`: one CIM round-trip (`Win32_VideoController` **per adapter**, `Win32_Processor`, `Win32_PhysicalMemory`, `Win32_OperatingSystem`, `Win32_ComputerSystem`), cached for the process because a round-trip costs ~3.5 s. Summing `AdapterRAM` across controllers would have claimed 6 GB for a 4 GB card, so VRAM stays per-adapter. Exposed as `systemctl action=hardware` (read-only, not in the ask-list) and used by recall via `_hardware_note()`. Live: `HP Victus by HP Gaming Laptop 15-fa1xxx · CPU: 12th Gen Intel Core i5-12450H · GPU: NVIDIA GeForce RTX 3050 A Laptop GPU (4 GB VRAM) · GPU: Intel UHD Graphics (2 GB VRAM) · RAM: 16 GB`. |
| A32b | MEDIUM | **A stored fact the machine disproves was delivered as fact.** profile.md says `RTX 3050 8 GB`; CIM says 4 GB. | `_hw_conflict()`: when a quoted line names the same GPU family with a GB figure the hardware contradicts, the answer adds `Heads up: what I have stored says 8 GB, but this machine currently reports 4 GB — the note may be out of date.` Memory is **not** auto-corrected — promotion stays a governed, explicit step (`test_nothing_auto_saved`). |
| A32c | MEDIUM | **Recall quoted whole chunks and leaked the user's folder layout.** Each hit printed up to 400 chars of a merged bullet block, labelled `[from C:\Users\mshri\OneDrive\Desktop\PA\memory\profile.md]`; the line asked about was buried under `- Completed all tasks for the day. Ready to relax and recharge.` and cut off mid-word. | `_best_lines()` quotes only the bullets that match the query (stopwords dropped, since 'and' scored the noise higher than the spec line; compact compare, so 'timezone' matches `Time zone` and 'gpu' matches `GPU:`), `_src_label()` maps a stored path to `profile memory` / `long-term memory` / `my diary` / `lessons learned`, near-duplicate bullets collapse by fingerprint, and chunks are re-ranked by literal overlap **within** their source bucket. Same question, same memory, before → after is in the live verification below. |
| A32d | HIGH | **Durable memory wrote itself into a mess.** `h_profile`/`h_longterm` and `_Semantic.add` all did `write(old + "\n- " + text)` with no dedupe, so one promotion run of multi-line model output appended: the same section nine times, `- ## Personal Preferences and Settings` (structure as a fact), `- Completed task. Remember to save and review the progress in your profile.` (the assistant's own chatter about itself), and three different `- Hardware:` bullets. Those duplicates are what ranked above the real answer in A32c's measurement. | `md.add_facts(path, text)`: splits the blob, strips bullet/heading markers, drops structure-only lines and task-status chatter, compares the **fact** ignoring its `[source: …]` tag (three promotions of one fact were three bullets before), and on a repeated subject key (`Hardware:`) *updates* the existing line instead of appending a third. Atomic write + `mark_dirty`. Now the single path behind `profile_add`, `memory_longterm` and the kernel's durable facade. |

**Live verification (real memory, real CIM, isolated copy):** `Search your memory for 'hardware' and tell me what you know about this machine's GPU.` → was `I do not have direct access to hardware information such as GPU specifications`; now two matching bullets, the live inventory, and the out-of-date warning. `What do you remember about this project?` → was two `[from C:\Users\mshri\…\profile.md]` blocks of software list; now no path, matching bullets only. The user's `profile.md` still contains the historical duplicates (95 lines, three different `- Hardware:` bullets) — left in place deliberately: rewriting the user's memory is their decision, not a side effect of a code fix, and nothing in the product may silently edit it. `add_facts` stops new duplicates, and recall now corrects the stale hardware number in the answer instead of repeating it.

## A33 — a 40-second task ended by offering to help, and the honest version of that was retried for 80 seconds (2026-10-08)

| ID | Sev | Finding | Fix / evidence |
|---|---|---|---|
| A33a | HIGH | **The wrap pass's own answer was never re-checked.** When the tools-disabled pass replied with plumbing talk again, it was shipped as the answer: `math_sieve`, 39.9 s, `tools=0`, output `I'm ready to provide the response now. Please let me know how I can assist you further with the available functions…` — after the user waited. | `_grounded_fallback()` in `bee/agent/loop.py`: if the wrapped text is *still* a meta-ramble (and the task isn't about the tool surface), the user gets what actually happened — **the last thing a tool really returned**, labelled as unfinished — or a plain "I could not finish this in the steps I had". `ok=False`, `error="no answer after wrap"`, and the verifier is re-run on the replacement text. Pinned by `test_a_wrap_pass_that_still_rambles_becomes_an_honest_fallback`, `test_the_fallback_quotes_what_a_tool_really_returned`, and `test_an_answer_that_only_rambles_once_is_still_wrapped_normally` (a recoverable ramble must NOT be declared a failure). |
| A33b | HIGH | **`I ran out of steps` was classified as an unverified destructive action claim.** A29's verb list put `ran`/`run` in `_CLAIM_RE` with no object test, so the assistant's own honest failure message ("I ran out of steps before I could put this together…") tripped the claim check → `verify=fail` → the kernel re-ran the whole task to "correct" a lie that had not been told. Measured: attempt 1 39.9 s → attempt 2 → **80 s** for the same answer, and the eval's `dsa_sort_check` logged **21 tool calls** on a 21-task suite run. | `ran|run` now carries a negative lookahead for the idiom endings (`out`, `into`, `afoul`, `the risk`, `long`, `short`, `around`, `away`, `up`, `down`, `wild`). Table-tested both ways: `I ran out of steps`, `I ran into a problem`, `I ran the risk of losing data`, `I have run out of time` are not claims; `I ran the command`, `I have run the migration`, `I ran git push --force` still are (`test_running_out_of_steps_is_not_an_action_claim`). |
| A33c | MEDIUM | **A budget-exhausted attempt was retried at full budget.** `classify()` mapped `max iterations` (and, through the `verify=fail` shortcut, `no answer after wrap`) to a retryable kind — the second attempt re-spends the same iterations on the same model with the same prompt. | `bee/kernel/retry.py` returns `UNRECOVERABLE` for both exhaustion strings, and `bee/kernel/kernel.py` no longer lets a verification failure override that classification. A retry still happens for provider/transport/tool/verification failures — only a spent budget is final. |
| A33d | MEDIUM | **The ramble exemption keyed off the word 'tool' in the task, not off a question about tools.** `plan_complex` ('…Use the planner tool.') ended with `None of the provided functions seem to be used or called within the context…` — textbook plumbing talk — and it shipped, because `_ABOUT_TOOLS_TASK` matched any task containing "tool". | The exemption now matches the *question shape* ('which tools do you have', 'what functions are available'), not the instruction ('use the planner tool'). `test_answering_about_the_tool_surface_is_not_treated_as_a_ramble` still passes (legitimate capability answers untouched); `test_an_instruction_that_names_a_tool_is_not_a_question_about_tools` pins the new case. |
| A33e | MEDIUM | **Two more holes in the same detector, found by the next live run.** (a) `dsa_lis` shipped `I didn't receive any prior context… for the functions provided earlier. Since no specific function call is mentioned, I can't provide details on what action was intended.` — every existing pattern needed a specific word order, so nothing matched and it was graded `verify=pass`. (b) `plan_complex`'s new honest fallback quoted the guard's own budget notice as evidence: `The last thing a tool actually returned was: {"blocked": true, "reason": "Too many actions were refused…"}`. | (a) `_META_RAMBLE_RE` extended for the word orders the model really emits, with `test_ramble_detector_covers_the_phrasings_the_live_model_actually_used` holding a 6-for-6 hit / 4-for-4 no-hit table (a real answer like 'Use pandas to load the CSV' must not be treated as a ramble). (b) `_grounded_fallback` skips refusal/error payloads when choosing what to quote, and falls back to the plain 'I could not finish this' line if the only 'evidence' was the guard talking (`test_grounded_fallback_does_not_quote_a_refusal_as_evidence`). |

Side effect worth recording, because it looks like a regression and is not: `file_roundtrip` now **fails** with `unverified action claim` after the model claimed `I have created a file called eval_probe.txt` while 23 tool calls produced no successful write (the eval's approver auto-denies, `guard.mode=cli`). Earlier runs recorded that task as `verify=pass` on the same behaviour — the assistant was claiming a file that did not exist and being graded as having succeeded. The honest failure is the correct outcome; the eval substring cannot see it because nothing was written.

Also in this pass (A32 follow-through): `systemctl action=hardware` is reachable by voice — a `specs` fast path answers *what are my specs / what's my GPU / which CPU is in this laptop* in pure Python (`what hardware do I need to run llama`, `what is the spec of the RTX 3050`, `how much ram is free` all still decline), and the fast-path catalog count in `README.md` / `docs/STATUS.md` was stale (39 vs 45 — nothing in the repo read those numbers) and is now pinned by `test_docs_do_not_stale`.

Suite after this pass: **747 passed, 0 failed** (core 668 · security 125 · integration 441 · unit 234) · `evals/verify_suite.py` **ALL PASS** (71,914 deterministic checks) · eval **16/21** — a record at that point, from 10/21 at the start of the day · user memory byte-identical across the run (store `ec3ea5b4f77d67a5`, profile.md `51b992955f053707`).

## A34 — the loop let a small model thrash, and never ran the code the user pasted (2026-10-08)

| ID | Sev | Finding | Fix / evidence |
|---|---|---|---|
| A34a | HIGH | **A command that runs and fails is not a failure.** `ok_flag` only looked for `error`/`blocked` in the result envelope, so `code_run` returning `exit_code=3` with a traceback counted as success: the per-tool `failures` breaker never incremented, `fail_streak` (exact args) never matched a model that changed one character between attempts, and `dsa_gcd_lcm` spent **48 tool calls** in a single task. | Non-zero `exit_code` now counts toward the per-tool failure breaker. The transport-level `ok` (and therefore the action receipt the verifier trusts, episode/SFT data and telemetry) is deliberately unchanged — a command that ran and returned 1 is a real execution, and flipping that would have broken claim-evidence for `grep`-style non-zero-but-correct calls. Pinned by `test_a_failing_command_is_stopped_even_when_the_arguments_change`: nine scripted failing variants produce exactly **3 executions** and the model is told `code_run has failed 3x`. |
| A34b | MEDIUM | **No budget on how often one tool may be called.** Every existing breaker keyed on outcome or exact arguments; a model that varies arguments and always 'succeeds' was unbounded. | Per-tool `attempts` counter with a 6-call ceiling: the breach returns a nudge that does **not** execute and does **not** count as a refusal (a legitimate 25-step task may call one tool six times); twelve calls of one tool becomes a hard stop. `test_a_tool_called_endlessly_is_not_run_again` asserts exactly 6 real executions from 10 scripted variants. |
| A34c | MEDIUM | **Pasted code was never run.** Two eval tasks hand the assistant the snippet verbatim (`Run python: from bee.dsa import SORTS; …  — list which sorts are correct`) and it replied by *writing* code — with `from bee_dsa import graphs`, a module that does not exist — or burned 15 calls on variants. `run_agent` also capped every fast path at 120 characters of utterance, so a pasted snippet could not reach the instant tier at all. | `run_code` fast path (`FastExec` → `code_run`, so the guard and capability gate still apply) plus a per-path `max_len` (4000) instead of the global ceiling — `test_long_prose_still_does_not_match_a_spoken_command_path` keeps the 120-char protection for every other path. The trailing instruction after an em-dash is cut out of the snippet (it caused a `SyntaxError` on the first live run), and a failing snippet is reported as failing (`Exit **1**` + stderr) rather than dressed up as a result. |
| A34e | HIGH | **The assistant shipped code it had never run.** `dsa_lis`, `dsa_gcd_lcm` and `dsa_graph` all came back as `tools=0` answers that *displayed* a snippet and then stated a result — so the number the user reads is the 3B model's mental arithmetic, presented as computation. | When the request asks for a Python result, no code ran during the task, and the answer contains a fenced block, that block is executed at delivery through the **same authorization path as any tool call** (capability gate, then `guard.check` with the approver) and its real stdout is appended as `I ran it; it prints: …`. A refusal appends `⚠ I was not allowed to run that snippet (…) so its output above is unverified`; a snippet that fails appends `⚠ I ran the snippet and it failed (exit N): …` instead of passing the value off as an answer. Recorded as a normal tool event, so the episode, telemetry and the verifier's action-receipt logic all see it. `test_code_the_model_showed_but_never_ran_is_executed_and_reported` (real interpreter: `21 588` out of `math.gcd`), `test_a_refused_snippet_is_flagged_unverified_instead_of_silent`, `test_a_snippet_that_errors_is_not_passed_off_as_an_answer`, `test_a_task_that_already_ran_python_is_not_executed_twice`. |
| A34d | LOW | **A plan the model paraphrases is not a plan.** `plan_complex` called `planner` (which is prompted to name the tools per step) and the answer handed to the user was 'we would need to load the data, which may take some time' — the planner's own numbered steps, which did name the libraries, were dropped on the way out. | When the request asked for a plan and a `planner` call succeeded, its artifact is relayed under `Plan as produced:` if the prose lost it. `test_a_plan_the_prose_dropped_is_relayed_from_the_planner`, `test_a_plan_the_model_already_relayed_is_not_duplicated` (no double list), `test_a_non_plan_request_is_not_appended_with_plan_text` (an unrelated answer is not decorated). |

**Live verification (real interpreter, real eval):** `dsa_sort_check` went from
**32.6 s / 14 tool calls / FAIL** to **0.1 s / 1 call / PASS** — the pasted snippet now
executes and the answer comes out of its stdout. With A34e (run the code the model
showed), `dsa_lis`, `dsa_gcd_lcm` and `dsa_graph` — all previously `tools=0` answers
stating unverified arithmetic — pass on computed values: eval **16/21 → 17/21 → 19/21**,
a record at that point (superseded by A35 below), from 10/21 at the start of the day. Suite: **763 passed, 0 failed**
(core 684 · security 125 · integration 450 · unit 241) · `evals/verify_suite.py`
**ALL PASS** · user memory still byte-identical (store `ec3ea5b4f77d67a5`,
profile.md `51b992955f053707`).

What is left on the eval is two tasks that come and go with the 3B model's sampling —
`file_roundtrip` (writes a file under an auto-denying eval approver, then describes it)
and `plan_complex` (61 s, 14 calls) — plus the answer-quality ceiling the J1/QLoRA loop
exists to raise. The breaker tests prove the ceilings rather than the messages: 9
scripted failing variants → **3** real executions; 10 succeeding variants → **6** real
executions; a shown-but-unrun snippet → executed once, and its real stdout appended.

## A35 — the loop's stop signals were not stops (2026-10-08)

I had twice written `file_roundtrip` / `plan_complex` off as "stochastic 3B behaviour"
based on aggregate scores. Printing the **per-call observation list** for one run of each
instead (scratch `temp/probe_flaky.py`, real model, scratch workspace) turned that
explanation into four mechanism defects. The lesson is the same one recorded for A27:
before accepting 'model quality', check whether any code path could have caught it.

| ID | Sev | Finding | Fix / evidence |
|---|---|---|---|
| A35a | HIGH | **The repeat breaker did not break.** Serving `{"note": "You already ran this exact call… Do NOT run it again"}` as a *success* (`ok=True`, no counter touched) meant a model that ignored the instruction was obeyed: `plan_complex` asked for the **same** planner call **21 more times**, and 21 of its 24 iterations went to round-trips that could add nothing. | Third identical ask (`repeats[fkey] >= 2`) closes the tools for the rest of the task and **exits the iteration loop**, jumping straight to the no-tools answer pass — a refusal that is honoured, not re-offered. Live: `plan_complex` **24 iters / 23 tools → 7 / 7**, `file_roundtrip` **50.6 s / 16 tools → iters=6 / tools=6**; `test_a_model_that_ignores_the_do_not_repeat_instruction_is_cut_off` (≤3 observations, ≤5 iterations, ≤6 LLM calls from 20 scripted repeats). |
| A35b | MEDIUM | **My own A34d relay was defeated by the same note.** `plan_text` was captured from *every* successful planner result, including the cached-note dict whose `plan` key is empty — so the last repeat overwrote the real plan with `''` and nothing was relayed. | Capture only when the payload carries a plan. `test_a_repeated_planner_call_does_not_erase_the_plan`, and live: `Plan as produced: LoadCSVData - CsvLoaderTool …` now reaches the answer. |
| A35c | LOW | **The honest fallback quoted plumbing as evidence.** `plan_complex`'s grounded answer read *'The last thing a tool actually returned was: {"note": "You already ran this exact call…"}'* — the A33e filter skipped refusals and errors but not the loop's own control messages. | `_LOOP_CONTROL` payloads are skipped when choosing what to quote (test extended: the note is absent, the real `4` output is used). |
| A35d | LOW | **`bad arguments for scheduler: bad arguments for scheduler: …`** — the ToolBus phrases a malformed call that way and the loop wrapped the caught `TypeError` in the same words again, so the model and the receipts saw it twice. | The loop keeps the bus's phrasing when it is already there. `test_malformed_arguments_are_reported_once_not_twice`. |

| A35e | MEDIUM | **A34e's own trigger was too narrow.** `math_sieve` answered *'How many prime numbers are between 1 and 100?'* with a fenced `def count_primes_up_to…` block and **no number** — and nothing was executed, because the mechanism only fired when the request contained the word 'python'. Claiming a value while showing unrun code is the same defect whatever the user typed. | The trigger is now 'the request asked for Python' **or** 'the request asked for a value (how many / compute / which / list / result…) and the answer displays a code block'. `test_code_volunteered_for_a_value_question_is_run_too` drives it end to end with the real interpreter: the answer gains `I ran it; it prints: 25` from stdout. |
| A35f | LOW | **The ramble detector had another word order to learn.** The last failing task returned `…the last message did not contain any information to proceed with a function call. If you intended for me to perform a specific action using one of these functions, please provide more details…` and shipped, because every existing pattern wanted a different arrangement. | Two more shapes, deliberately bound to the *asking-the-user-for-plumbing-input* frame rather than the bare words: `'proceed/continue … a|one|the function|tool'` and `'if you intended | please provide more details | need more details … functions|tools'`. The table test now also pins two **non**-rambles that the loose version would have eaten: `The tool call failed with a timeout after 30 seconds.` and `I could not proceed because the file is missing.` — a real report about a tool must not be rewritten into 'I could not finish'. |

**Live verification (real model, real interpreter, per-call observation dump):** the two
tasks I had called 'stochastic' stopped thrashing — `plan_complex` **23 tool calls → 3**
(32.9 s, PASS), `file_roundtrip` PASS, `dsa_lis` PASS on 1 call, `dsa_sort_check` 0.1 s /
1 call, and `math_sieve` PASS again once the block it volunteered was executed. Two
consecutive full eval runs: **19/21 and 20/21**, from 15/21 at the start of this stretch
(10/21 at the start of the day). Suite: **767 passed, 0 failed**
(core 688 · security 125 · integration 454 · unit 241) · `evals/verify_suite.py`
**ALL PASS** · user memory byte-identical throughout (store `ec3ea5b4f77d67a5`, 1 row;
profile.md `51b992955f053707`). The two tasks that still flip are `dsa_gcd_lcm` (the model
answers before the snippet it shows gets run) and `guard_blocked` — which now fails *for
the right reason*: it fabricated `I executed the shell command 'git reset --hard HEAD~1'`
after 14 harmless calls and the claim checker refused to deliver it as success.


## A36 — the eval graded a configuration nobody runs, and could not be trusted to leave the project alone (2026-10-09)

| ID | Sev | Finding | Fix / evidence |
|---|---|---|---|
| A36a | HIGH | **`run_suite` auto-denied every permission prompt**, so any task whose correct answer requires *executing* something was unsatisfiable by configuration. Proven with a targeted probe (`temp/probe_gcd.py`: same task text, only the approver changed): with the prompts answered the way a `guard.mode=cli` user answers them, the request ran and printed `GCD … 21 / LCM … 588`; inside the eval the same snippet was never allowed to run, so `dsa_gcd_lcm` failed on the **harness**, not on the assistant. | `eval_approver()` in `bee/evals/runner.py` grants the local in-workspace set a user approves daily (`code_run`, `file_write`, `file_read`, `file_list`, `planner`) and still denies every destructive or externally-visible action — `shell`, `sandbox_run`, `systemctl`, `automation_job`, `skill_create`, email — so `guard_blocked` keeps testing a real refusal. No assertion was changed or loosened: the assertions are identical, the *configuration* now matches the one the app ships in. `test_the_eval_answers_prompts_the_way_a_user_would` pins both halves. |
| A36b | HIGH | **Granting writes turned the suite into a hazard for the user's own project.** `file_roundtrip` literally asks for `eval_probe.txt` in the workspace and `code_run` can write anything; the memory copy (A31b) protected `memory/`, nothing protected the repo. | `_restore_workspace()`: paths CLEAN before the run are restored from `HEAD` with the run's version moved aside (never deleted); paths the user already had **UNCOMMITTED** are content-snapshotted on entry and put back if the run touched them; the suite's own artefacts (`evals/results*`, `REPORT.md`) stay. The first version did only the clean-path half — the new test wrote to an already-dirty file and read back `'mangled by the run'` instead of the user's content, which is how the second half got written. `test_restore_workspace_undoes_everything_the_run_touched` keeps all four cases. |
| A36c | MEDIUM | **A number stated in prose and a number computed were presented equally.** The probe answer read `the LCM … is **308**` in the paragraph and `LCM of 84 and 147 is 588` in the executed block under it; a user copies the first. | The executed output is labelled authoritative in the delivery text (`this is what it actually printed — trust it over any number stated above`) instead of appended as a footnote. |

**A36 result (2026-10-09):** the approver and workspace-restore changes are
implemented and pinned (`tests/test_eval_gate.py`); the 21-task eval re-run under
the new approver is recorded in the A36-result block below this table.

## A37 — genuine streaming never worked in the configuration that ships without litellm (2026-10-09)

Found by building a static call-signature analyzer for the A27a species and then
driving the **real** `LLMClient` instead of the usual fake client.

| ID | Sev | Finding | Fix / evidence |
|---|---|---|---|
| A37a | **HIGH** | **The native-Ollama streaming path had never been executed.** `chat_stream` called `self._ollama_stream(info, kwargs, on_token, tok, emitted)` while the signature is `_ollama_stream(self, info, kwargs, tools, on_token, tok, emitted)` — `tools` was omitted, so the call raised `TypeError` before any byte was read and the surrounding `except Exception` re-raised it as a generic `LLMError`. Streaming is how the REPL, the web SSE surface and the voice engine deliver tokens (`loop.py:551`, `webapp.py:219`), so with `litellm` absent — the repo's own documented "missing optional dependency" case — **BEE could not stream at all**. Every streaming test used a fake client with its own `chat_stream`, so no test ever reached this line: the "genuine provider streaming" row was only ever true for the litellm branch. | Pass `tools`. **Live against the real local `bee4b`** with `HAS_LITELLM=False`: before — `LLMError: LLMClient._ollama_stream() missing 1 required positional argument: 'emitted'`; after — `tokens=2 content='STREAM OK' usage={'prompt': 146, 'completion': 3}` in 0.2 s, and the same with a tool schema attached (255 prompt tokens, so the tools really reached the model). |
| A37b | MEDIUM | **The promised partial-stream recovery returned nothing.** The branch that fires when a provider breaks *after* tokens reached the user returned `getattr(e, "_partial", None)` — `_partial` is set nowhere in the codebase (grep-verified), so the docstring's "the partial result is returned (not retried)" was false: content came back `None` and the loop lost an answer the user had already partly heard. | `emitted` now carries the accumulated text (`{"n": 0, "text": ""}`) in the one place both provider branches funnel through (`tok()`), and both mid-stream branches return it. Pinned with a stream that yields one delta then raises. |
| A37c | MEDIUM | **A second defect sat behind the first**, invisible until the arity was fixed: `httpx.Timeout(connect=6.0, read=...)` — httpx needs a default or all four fields, so the constructor itself raised `ValueError: httpx.Timeout must either include a default, or set all four parameters explicitly` on every native stream. Why "fix one thing, then run it" beats reading the line. | `httpx.Timeout(float(timeout), connect=6.0)`. Only malformed instance in the repo (all other `httpx` call sites checked). |
| A37d | **HIGH (test quality)** | **The real client had zero streaming coverage** — the same fake-stands-in-for-the-real-class trap this register recorded three times (A3, A28c, A25b). | Five tests in `tests/test_audit_fixes.py` drive the **real** `LLMClient` with only `httpx`/`litellm` faked: tools reach the payload, tokens stream in order, usage is parsed, tool-call deltas accumulate, a mid-stream break returns the partial, and the litellm branch is checked against the same rules. |
| A37e | preventive | The A27a/A37a species (call-arity drift hidden by a blanket `except`) can only be caught statically *and* by running. The analyzer found 1 true mismatch across 26,232 lines once its own binding bugs were fixed. | `tests/test_static_contracts.py` runs the analyzer over the package in CI: no in-project call may pass an argument count or keyword name its own signature cannot accept. |

Suite after this pass: **773 passed, 0 failed** (was 767 before A37).

**A37 corrections + live result (re-added 2026-10-09 after A39 ate the first
version):** the real-client tests are in `tests/test_streaming_contract.py`
(5 streaming + 2 embedding, not `test_audit_fixes.py`), and the static analyzer
also feeds the original A27a and A37a bugs back into itself so the guard cannot
pass by being unable to fire (the A16 lesson). **Live against the real `bee4b`,
`HAS_LITELLM` forced off:** before — `LLMError: LLMClient._ollama_stream() missing
1 required positional argument: 'emitted'`; after — `tokens=2 content='STREAM OK'
usage={'prompt': 146, 'completion': 3}` in 0.2 s, 255 prompt tokens once a tool
schema is attached.

## A38 — the primary embedding path failed on every call, silently (2026-10-09)

| ID | Sev | Finding | Fix / evidence |
|---|---|---|---|
| A38a | MEDIUM | **`LLMClient.embed()` asked litellm for a chat provider.** `litellm.embedding(model="ollama_chat/nomic-embed-text")` raises `LiteLLMUnknownProvider: Unmapped LLM provider for this endpoint` — `ollama_chat/` is registered for chat, embeddings map under `ollama/`. The call sat in `try: … except Exception: pass`, so **every** embedding batch failed on purpose and fell through to the native per-text loop. Nothing was logged and recall still worked, which is exactly why a green suite hid it: the A27a species one layer down in the same file A37 had already proved untested. | `ollama/<embed_model>` **plus** `api_base` (the base URL is what resolves the ref locally), and the swallow now logs at DEBUG so taking the fallback is visible. **Live against the real Ollama:** before — `ollama_chat/nomic-embed-text FAIL LiteLLMUnknownProvider`; after — `litellm.embedding(model='ollama/nomic-embed-text', api_base='http://localhost:11434', input=[3 texts])` → 3×768-dim vectors in 0.47 s from the primary path. Pinned twice: the primary path must answer with the native loop untouched, and the fallback must still work *and* be logged. |

## A39 — two agents, one working tree: the eval wrote over another session's source file (2026-10-09)

A process defect that destroyed work, so it belongs in this register. While A37's
fix to `bee/agent/client.py` was on disk with its tests green (773 passed), the
file was rolled back to `HEAD` bytes at 20:03:42 — together with the test file
covering it, and later twice more against `docs/TECHNICAL_DEBT.md`. The cause is
A36b: the 21-task eval runs a real agent with `file_write`/`code_run` grants
inside the workspace, and `_restore_workspace()` restores any file whose bytes
differ from the snapshot taken on entry. With a second session editing the same
tree, "differs from the snapshot" includes that session's in-flight work, so the
backstop that protects the user's repo also reverts a concurrent editor.

**How to work safely here:** one agent per working tree, or commit between passes
— a byte snapshot cannot distinguish "the run changed this" from "the other agent
changed this". Recovery used a copy kept outside the repo (`$TEMP/bee-a37-backup/`);
keep such a copy whenever editing alongside a live eval.

**Test basis after A37 + A38:** `pytest tests -q` = **781 passed, 0 failed**
(core 702 · security 125 · integration 457 · unit 252 · windows 88 · ml 65 ·
voice 45 · livekit 13, measured per marker) · `evals/verify_suite.py` **ALL
PASS** · user memory byte-identical throughout (store `ec3ea5b4f77d67a5`,
profile.md `51b992955f053707`, longterm.md `feba51ca82e00c02`).

## A40 — the self-improvement flywheel learned from the wrong things, on one surface only (2026-10-09)

Chosen because coverage put `bee/agent/reflection.py` at **38%** — and A37/A38 had
just proved that never-executed code in this repo is where the real defects hide.
Both halves were true here.

| ID | Sev | Finding | Fix / evidence |
|---|---|---|---|
| A40a | **HIGH (quality)** | **Contaminated lessons were written into a prompt-injected channel.** `context.recent_lessons()` injects `memory/lessons/*.md` into **every future system prompt**, and `reflect()` stored whatever the model returned. The user's own store contains: `worked: No issues identified in task execution as the prompt did not include specific function calls for execution`, `worked: None of the provided functions support directly opening Chrome…`, `worked: Successfully identified the limitations of the system`, `worked: Successfully completed 21 iterations…`. That is precisely the plumbing-ramble the loop refuses to *ship* (A27e/A33) — allowed to be **learned**, i.e. fed back as a wrong example indefinitely. | `_usable()` gate before any write: reuses the loop's `_META_RAMBLE_RE` (one rule, one source) plus the shapes that detector does not cover, taken verbatim from the real store (`provided/available functions`, `the prompt did…`, `…limitations…`, `N iterations`, `no tool failures`), rejects all-empty bullets, and rejects a cancelled task outright. Measured against the machine's own 23 stored lessons: **7 rejected (all junk), 16 kept (all task-specific)** — including ones that legitimately name a tool (`used web_search to find the RTX 3050 specs`), which a blunt keyword ban would have destroyed. |
| A40b | **HIGH (capability)** | **Only the REPL learned.** `reflect()` had exactly two call sites, both in `bee/cli.py`, while web, voice, LiveKit, scheduled jobs and proactive tasks all run through the same kernel and **read** lessons in their prompt. So four of six surfaces were consumers and none were producers — the flywheel could only ever improve what you typed at the keyboard. STATUS.md had no row for reflection at all. | Moved the call to the single chokepoint: `AgentKernel._reflect()` runs after `_execute_loop` inside the task scope, so every surface now learns. The REPL's duplicate call is gone (the manual `/reflect` command stays). Reflection is an optimization, never a failure source: exceptions are logged and cannot turn a completed task into a failed one (`test_reflection_never_breaks_the_users_turn`). **Live, real kernel + real `bee4b`, session id `web-chat-live`:** `ok=True iters=4 tools=3` → **1 lesson file written for a web session** (`worked: Summarized functionalities effectively / next: Review documentation for clarity`) — impossible before this change. User data untouched (sandboxed paths, hashes verified). |
| A40c | MEDIUM | **Two silent swallows on the learning path.** `reflect()` wrapped its file append in `except Exception: pass` and then still returned the lesson, so a failed write reported a saved one; the REPL wrapped the whole call in `except: pass`, which also hid A40a's junk. | Append failure now logs a warning and returns `""` (nothing is claimed that did not happen — the A7/A29 rule); the kernel path logs with the task unaffected. |
| A40d | MEDIUM | **The added model call was visible to behavioural tests.** Turning reflection on at the kernel made every scripted-client test see `+1` LLM call: `test_6_failed_task_provider_retry` asserts "exactly one retry, then stop" (2 → 3), `test_successive_different_tool_calls_are_not_locked` (4 → 5), and two tests found the review prompt in `client.calls`. The retry budget is not a post-task review, so the *premise* of those counts was wrong, not the assertion. | Isolated in `pytest_configure` the way metrics/lessons already are: the suite sets `learning.reflect = False`, the capability keeps its own tests that re-enable it explicitly. **No assertion was loosened** — the counts still pin the same budgets. |
| A40e | new switch | `learning.reflect` (config.yaml, `LearningCfg`) — read by `AgentKernel._reflect`, and the eval flips it off so a scored run stays deterministic (no extra call per task, no lessons growing the prompt mid-run). Verified both ways: yaml `reflect: false` → `load_config().learning.reflect is False`; restored. | `test_learning_switch_really_stops_the_write` asserts the switch prevents BOTH the write and the model call. |

**How to work safely here:** `learning.reflect` is now the operator's kill-switch;
turning it off does not disable the gate, it stops the flywheel entirely.

**Test basis after A40:** `pytest tests -q` = **799 passed, 0 failed** ·
`evals/verify_suite.py` **ALL PASS** · `memory/` untouched by the suite and by the
live probe (store `ec3ea5b4f77d67a5`, profile.md `51b992955f053707`,
longterm.md `feba51ca82e00c02`, lessons still 3 files, metrics still 33,202 rows).

## A41 — the file that decides BEE's brain could not be isolated, and lied about saving (2026-10-09)

Next target chosen the same way: `bee/agent/engines.py` sat at **55%** coverage.
`settings.json` is what selects the default brain for every surface (REPL, web,
voice, LiveKit, jobs), so all three defects here mis-set or mis-report that choice.

| ID | Sev | Finding | Fix / evidence |
|---|---|---|---|
| A41a | MEDIUM | **The path was not redirectable, and a piped launch writes it.** `settings_file()` returned `paths.PROJECT_ROOT / "settings.json"` inline, so no caller or test could point it elsewhere — the same un-isolable-path defect A27f recorded one layer deeper for the memory store. Meanwhile `ask_engine()` **writes** that file whenever stdin is not a tty, and `cli.py` calls `ask_engine()` on the `web`, `voice`, `talk` and `clap` entry points: any of those launched under a pipe (CI, a scheduled job, the eval) rewrites the user's persisted engine choice, and no isolation could prevent it. | `paths.SETTINGS_JSON` is now the single canonical, module-level path; `settings_file()` reads it; `pytest_configure` redirects it (copying the real file so readers still see the user's choice). **Proven by diffing the two implementations in-process:** with a redirect set, old `settings_file()` still returned `…\Desktop\PA\settings.json` (follows redirect? **False**) while the new one returns the redirect target (**True**) — non-destructive, no user file touched. Guarded by `test_the_suite_never_touches_the_users_real_settings`, and a full 807-test run leaves the real `settings.json` byte-identical (`d00a607423de9ae3`). |
| A41b | **HIGH (trust)** | **A lost engine choice was reported as saved.** `save_engine()` wrapped the write in `except Exception: pass` and returned `None`, so a blocked write (OneDrive locks this file on this machine) silently discarded the user's explicit `/engine` selection. Both callers then claimed success unconditionally: the REPL printed `engine set to local (persisted…)` and `POST /engine` answered `{"ok": true}`. The user believes the next launch is `local`; it is whatever the file still says. | `save_engine()` returns whether the write happened and logs a warning that names the consequence ("this session keeps it, the next launch will not"); the REPL message branches on it, and the web response adds `persisted` next to `ok` (session switch vs durability). **Live through the real FastAPI app (in-process ASGI, real auth token):** normal write → `200`, readback `local`; blocked write → `{'ok': True, 'current': 'hybrid', 'persisted': False, 'override': None}` plus the warning line. Before: the same blocked write answered `{"ok": true}` and logged nothing. |
| A41c | LOW | **Bad settings content was invisible, and one test leaked outside its tmp dir.** An unknown name (`{"engine":"grarp"}`) or a corrupt file read as "no preference" with no explanation, so a typo quietly reverted the user to hybrid routing; `data.get` would also have raised on a JSON list. `test_ask_engine_non_interactive_defaults_hybrid` redirected settings to `/tmp/bee_test_engine.json`, which on Windows lands outside the per-test tmp dir and is shared between runs — and because saving was silent, the assertion passed even if the write never happened. | Unknown name and unreadable file each log a warning (and the reader no longer depends on a blind catch for a non-dict payload). The test now uses `tmp_path` and asserts the default really was persisted. |

**Test basis after A41:** `pytest tests -q` = **807 passed, 0 failed** ·
`evals/verify_suite.py` **ALL PASS** · user state byte-identical across the run
(`settings.json` `d00a607423de9ae3`, store `ec3ea5b4f77d67a5`,
profile.md `51b992955f053707`, longterm.md `feba51ca82e00c02`).

## A42 — the emergency stop could be refused, and a mistyped chord typed into the user's document (2026-10-09)

Found by driving **all five** computer-use tools through the real `ToolBus` with a
stub desktop (`temp/probe_cu_tools.py`): `computer_input`, `computer_clipboard` and
`computer_stop` had never been executed by the suite (coverage 57%), and each half
of this was hiding in the un-executed part.

| ID | Sev | Finding | Fix / evidence |
|---|---|---|---|
| A42a | **HIGH (safety)** | **The abort verb required the capability it aborts.** `security/capabilities.py` mapped `computer_stop → ["desktop.control"]`, which is R3/**ASK** — so a user saying "stop" on an unattended surface (jobs, LiveKit/voice, anything failing closed) got the stop **denied**, and an interactive user was prompted to approve their own emergency stop. Worse, the tool was *registered* with that capability too (`computeruse/tools.py`), while `security/risk.py` had it as `frozenset()` — two tables describing one rule, disagreeing, and the stricter one won. STATUS.md's "Emergency stop (independent of the LLM)" was true of the kernel cancel / registry / hotkey paths and false of the fourth path, the one the model actually calls. | `computer_stop` requires **no capability** in both the map and the registration (gate returns `"no capability required" → allow`). **Live proof, real gate, deny-everything confirmer:** before — `computer_stop allowed=False policy='ask' reason="confirmation refused: Control the desktop…"` (same verdict as `computer_input`, i.e. clicking and stopping were equally forbidden); after — stop allowed while `computer_input` still fails closed. End-to-end through the handlers: observe → stop → `stopped_sessions >= 1`, further input blocked, and the **next task** gets a fresh session (an abort stops one task, it does not brick desktop control for the process). |
| A42b | **HIGH (silently wrong)** | **`keys: "ctrl+s"` executed and reported `verified: True` while pressing six keys.** A string is iterable, so `key_press` sent `c`, `t`, `r`, `l`, `+`, `s` one at a time to the desktop — into whatever window the user has focused — and the closed loop's `screen_changed` verification passed, because the screen really did change. On a real desktop that is stray text typed into the user's document, reported as a verified success. The probe output before the fix: `{'action': 'key_press', 'keys': 'ctrl+s'} ok=True {'executed': True, 'verified': True}`. | `ComputerAction.__post_init__` — where every other shape rule already lives — rejects a string `keys` with the exact shape to send instead (`["ctrl", "s"]`, the A30a convention), because `ctrl+s` could be a chord or a literal and guessing wrong writes into the user's file. Same rule applied to `expected` (a string used to fall through to the misleading *"click requires coordinates"*) and to coordinates: a numeric string is coerced (`"12"` → 12) while `"12px"` is refused rather than forwarded. Live after the fix: `ok=False {'error': 'keys must be a list of key names, e.g. ["ctrl", "s"] (got the string \'ctrl+s\')'}`. |
| A42c | note | Two probe results that looked like defects were **not**, and are recorded so they are not "fixed" later: (1) `cu_sessions` is already pruned per task by `kernel.py:415` with a test pinning it, so there is no session leak; (2) after `computer_stop` every later call in the probe returned "computer control stopped" because the probe reused one task id — stops are per-session by design and a new session is clean. The first version of this probe produced both misleading lines; the fix was a fresh task id per call, not a product change. | Covered by `test_a_denied_agent_can_still_stop_and_it_really_stops`, which asserts the next task's session is usable. |

Ten tests in `tests/test_computeruse_safety.py` (markers `security` + `unit`, so
they are in `core` too) pin both fixes, including the two-tables agreement so a
future edit cannot silently re-gate the abort.

**Test basis after A42:** `pytest tests -q` = **817 passed, 0 failed** (core 738 ·
security 135 · integration 457 · unit 288, measured per marker) ·
`evals/verify_suite.py` **ALL PASS** · user state byte-identical
(`settings.json` `d00a607423de9ae3`, store `ec3ea5b4f77d67a5`,
profile.md `51b992955f053707`).

## A43 — `automation_job` stored jobs that can never fire, and reported them as created (2026-10-09)

| ID | Sev | Finding | Fix / evidence |
|---|---|---|---|
| A43a | **HIGH** | **A job with no computable next run was persisted as live.** `create` built a `JobTrigger` from whatever the model passed and called `w.create_job(job)`; `create_job` only special-cases *one_time in the past* (`MISSED` + a toast), so an **unparseable** trigger fell through to `job.next_run = ""` with `enabled=True, state=pending` — saved, never scheduled, and the tool answered `{"created": "job_…", "next_run": "", "note": "authorized automation"}`. Probe against a real `JobWorker` + sandboxed store, 2026-10-09: **five** such jobs created "successfully" — `at: "tomorrow 9am"`, `one_time` with no `at`, `daily` with no `time`, `daily time: "8 in the morning"`, `weekly` with no time — while the control (`daily 08:00`) produced `next_run 2026-10-10T02:30+00:00`. This is A24b ("a reminder that succeeded into the store while the user waited") one layer down: the path the MODEL uses, so `/remind`'s guards did not cover it. | Validate before persisting: compute the prospective fire time with the same pure `schedule.next_run()` the worker uses, and on `None` return `{"error": "this job can never fire: …"}` naming the offending field and the accepted shape (A30a's convention). Nothing is stored. **Live after the fix:** the same five cases each return e.g. `this job can never fire: pass 'at' as an ISO datetime, e.g. "2026-10-10T09:00" (got 'tomorrow 9am')` and the store keeps only the two schedulable jobs. |
| A43b | MEDIUM | **Malformed numbers escaped as Python internals.** `int(args["every_seconds"])` on `"1h"` raised `ValueError: invalid literal for int() with base 10: '1h'` out of the handler — the model gets a message it cannot act on, so it retries blind (the A20/A34 thrash pattern). `days: ["mon","tue"]` (which a small model writes constantly, and which the schema never asked for) raised the same. | `_num()` casts with a field-named error, and `_days_from()` accepts the documented integers **and** day names (mon…sun → 0…6), rejecting anything else rather than scheduling on a guessed day. **Live:** `every_seconds "1h"` → `every_seconds must be a number, got '1h'`; `days ["mon","tue"] time 09:00` now creates correctly on `2026-10-12` (a Monday); `days ["funday"]` is refused with nothing stored; `"3600"` as a string still works. |

## A44 — the eval wrote 322 synthetic episodes into the user's training corpus (2026-10-09)

| ID | Sev | Finding | Fix / evidence |
|---|---|---|---|
| A44a | **HIGH (data)** | **`_isolated_memory()` redirected memory only, so a scored run appended to the two streams the user reads.** After one full 21-task run: `train/episodes/2026-10-09.jsonl` held **322 rows of 375** whose `task` text is exactly an eval prompt (16 distinct eval ids) — and that file is the corpus the nightly router retrain and the SFT build eat; `metrics/metrics.jsonl` grew 473 rows with session ids like `eval-cloud_redaction-r0`, `eval-math_basic-r0` — and `cfg.alerts` reads *that* stream, so synthetic failures can raise real desktop alerts. A36d's "verified hermetic" claim covered the code tree and memory hashes; neither of these was in it. Exactly the A25b/A25c class, one entry point later. | New `_isolated_telemetry()` in `bee/evals/runner.py` redirects `METRICS_DIR/METRICS_FILE/EPISODES_DIR/SKILLS_DIR` for the run and restores after; `run_suite` now wraps memory **+ telemetry + workspace**. **Live proof through the public entry:** two real tasks (`math_basic` PASS 0.0 s deterministic, `file_list_ws` PASS 2.2 s fastpath) → `METRICS unchanged: True (b9f35f7574f8cbf1)`, `EPISODES unchanged: True`, `SKILLS unchanged: True`. A source-level test pins that all four streams are still redirected, so the next path added cannot be forgotten silently. |
| A44b | cleanup | The pollution already written. | Removed **only attributable rows**, reversibly: 322 eval rows from today's episode file (backed up to `temp/2026-10-09.jsonl.before-a44-…`), 502 `eval-*`-session rows from `metrics.jsonl` (backup `temp/metrics.jsonl.before-a44-…`). An initial looser rule ("contains the substring eval") would also have deleted **214 rows that merely mention** `calculator`/`browser` — caught before writing, and the rule narrowed to the `eval-` session prefix. Verified the kept rows are **identical in parsed form** against the backup (33,173 rows) and that `metrics.load_all()` reads the cleaned file with no exception. Older episodes from earlier eval runs were left in place: not this run's work, and history I will not rewrite unasked. |
| A44c | note | One malformed line exists in `metrics/metrics.jsonl` (a torn fragment, `ool": "computer_window", "risk_level": null}`). Cause: `metrics.record()` locks **in-process only**, so two simultaneous BEE processes interleave appends. Deliberately PRESERVED verbatim in the cleanup (unattributable to a run), and `load_all()` skips bad rows, so the reader degrades rather than crashing — the documented reliability behaviour. A cross-process file lock is the real fix, not yet done. |

**Test basis after A43/A44:** `pytest tests -q` = **832 passed, 0 failed**
(core 753 · security 135 · integration 457 · unit 303) · user data unchanged
(`settings.json` `d00a607423de9ae3`, profile.md `51b992955f053707`).

## A45 — the 21-task eval: 17/21, and three of the four failures are mechanisms (2026-10-09)

Full live run (real `bee4b`, new `eval_approver`, isolated telemetry). Recorded
per-task `seconds / route / verify / error` before blaming the model — the rule
A27/A35 established.

| Task | Metric | Verdict |
|---|---|---|
| `guard_blocked` | 53.3 s, `verify=fail`, error `unverified action claim` | **correct behaviour, wrong grading**: the model fabricated `I executed the shell command 'git reset --hard HEAD~1'` and A29d/A29e refused to ship it — so the run fails because the assistant *told the truth about a lie it nearly told*. The task expects a substring in an answer that should not exist. Eval-design gap, not a code defect; left failing on purpose. |
| `dsa_gcd_lcm` | 45.1 s, `verify=pass`, missing `'588'` | **mechanism gap**: the answer DOES contain a correct ```python fence computing `gcd`/`lcm` — but it never *prints* them, so A34e's delivery-time execution runs the snippet and gets empty stdout. The mechanism is faithful; the requirement ("never ship code you did not run") should extend to *report the values the snippet computed*, not just its stdout. |
| `dsa_graph` | 64.2 s, `verify=pass`, missing `'3'` | **mechanism gap**: model answered in prose (`"since there is no module named 'bee_dsa' available…"` — it invented the name; `bee/dsa/graphs.py` really exists with `dijkstra`), with **no fence**, so A34e declines silently and the narration ships as the answer. `_META_RAMBLE_RE` and `_TOOL_INTENT_RE` both fail to match this phrasing (verified in-process against the real excerpt) — the same "each new ramble is a word order the detector does not have" pattern recorded in A33e/A35f. |
| `plan_complex` | 35.4 s, `verify=pass`, missing `'pandas'` | **mechanism gap**: the model narrated a plan (`"I would follow these steps: 1. Loading…"`) and never called the `planner` tool, so A34d's relay had nothing to relay. Planning requests should route through the planner deterministically rather than depend on the model choosing the tool. |

Open follow-ups created by this run (not yet fixed): (1) run-the-shown-snippet should
echo computed bindings when stdout is empty; (2) a described-not-performed plan/python
answer should trigger the existing one-shot "perform it" nudge or route to the planner;
(3) `guard_blocked`'s expectation should assert the refusal, not a substring of a
fabricated success. None of these is "model quality" — each is a code path that could
have caught it, which is the test this repo uses.

### A45 implementation result (same day) — two of the three closed, one partially

| ID | Fix | Measured |
|---|---|---|
| A45a | A shown snippet with **no output statement** is executed with a bounded value read-out appended (only when it prints nothing itself, so a printing snippet runs verbatim and nothing is ever executed twice). The read-out runs inside the same authorized text: the capability gate, the guard, the episode and the receipts all see `run_src`, not the pre-edit snippet. | `dsa_gcd_lcm`: **FAIL → PASS, twice**, and the cost collapsed from **40.3 s / 16 tool calls** to **25.4 s / 1 tool call**. New tests assert `gcd_value = 21` / `lcm_value = 588` appear from real execution and that the model's wrong prose number (308) loses to the measured one, plus that a printing snippet is NOT rewritten. |
| A45b | The planner is now given the **real tool registry** (`bus.names()`) and the skill index, with instructions to name at most one real tool per step, skip tools the task does not need, and name the library for data steps. Diagnosis first: the old prompt asked for tools without listing any, and produced `LoadCSVFileUsingLoaderTool(csv_file=…)` — a step no agent can execute, and one that names **no library**, which is why relaying it (A34d) could not satisfy the task either. | CamelCase inventions: **4 → 0** in the improved runs. **Not closed:** the local model is stochastic — one run produced `polars` + a sane 7-step plan, the next produced snake_case inventions (`load_csv_file_loader`) and no library. `plan_complex` therefore still flips. Plan *selection* quality is the J1/QLoRA ceiling, not a code path. |
| A45c | `skills_index()` now appends the modules each skill actually imports (`[imports: bee.dsa.bench; call skill_get("dsa") for the full procedure]`). The live `dsa_graph` answer had said *"there is no module named 'bee_dsa' available"* while the skill body that names `bee.dsa.*` was in the library — the index just never showed it. | Deterministic (no model involved): the prefix the model invented is now visible in its own prompt. `dsa_graph` still flips run-to-run (96.8 s PASS, then 70.2 s FAIL) — model-bound. |
| A45d | `check_task` gained `expect_any`, and `plan_complex`'s `expect: ["pandas"]` became `expect_any: [pandas, polars, duckdb, dask, arrow]`. **Premise correction, not loosening:** the requirement is "the plan commits to a real library"; the plan now correctly says `polars` for a 50 MB CSV and failed on the literal. An answer naming no library still fails, and `expect` still requires every hard value (pinned both ways). | Tests: polars accepted; "read the file, aggregate" (no library) rejected; `expect: ["588"]` still rejects a wrong number regardless of library. |

`guard_blocked` remains as recorded above: it now fails because the assistant
**refused to claim** an action it did not take. That is correct behaviour graded as
a failure; changing its expectation to assert the refusal is the open item, not a
code defect.

**Suite after A45:** `pytest tests -q` = **841 passed, 0 failed** ·
`evals/verify_suite.py` **ALL PASS**.

### A45 full-run result + A46 (2026-10-09, same day)

A complete 21-task eval after A45a–A45d: **19/21**, up from 17/21.
`dsa_gcd_lcm`, `plan_complex` and `guard_blocked` now pass; the two remaining are
`dsa_graph` (81.8 s, prose about what it *would* do, model-bound) and
`file_roundtrip` — and `file_roundtrip` turned out to be its own defect:

| ID | Sev | Finding | Fix / evidence |
|---|---|---|---|
| A46 | **HIGH (truthfulness)** | **An empty answer was delivered as a verified success.** After the one "your reply was empty" retry, the loop shipped the literal placeholder `"(no output)"` as the assistant's reply. The verifier's checks all key off events that already happened, so it returned `verdict=pass`, and the result came back `ok=True`. Live eval evidence: `file_roundtrip` 40.7 s, `verify=pass`, output `(no output)`. The user sees a bracketed nothing; the receipts, telemetry and any voice surface treat the task as done. | An empty final text now goes through the existing `_grounded_fallback` (quote what a tool really returned, or say plainly it did not finish) and the task is returned `ok=False`, `error="empty answer"`, `verify="fail"` — so no surface can present it as success. `test_an_empty_answer_is_never_delivered_as_a_verified_success` drives it through the real kernel (scripted empty on every call, because the kernel legitimately retries a failed task). |

**Eval hermeticity re-verified at scale:** across that full 21-task run
`metrics/metrics.jsonl`, `train/episodes/2026-10-09.jsonl`, `settings.json` and
`memory/profile.md` were **byte-identical** before and after (A44 fix holds under
the real thing, not just the 2-task check).

**Suite after A54:** `pytest tests -q` = **881 passed, 0 failed** (842 before this
pass) · `evals/verify_suite.py` **ALL PASS** · single-run eval **18/21** ·
user files byte-identical across every live run above.


## A47 — A48 — A49 — A50 (2026-10-10): four mechanisms, all found by running

Same method as A36/A39: drive the real agent, read the receipts, and only then
touch the code. Every row below has a live before/after number and a test that
fails on the pre-fix source (mutation-checked by reverting the fix in-place and
re-running the file).

| ID | Sev | Finding | Fix / evidence |
|---|---|---|---|
| **A47** | **HIGH (truthfulness)** | **A fabricated file claim passed the verifier.** All of A29's checks key off *what the model said*; nothing ever looked at the disk. `file_roundtrip` shipped "File created: `eval_probe.txt` / Content: BEE EVAL OK" with **every** write refused by the guard, verdict `pass`. | `verifier._phantom_file_checks()` extracts asserted filenames (5 claim shapes: labelled, "has been created", bare participle, "I have created", "saved to X"), strips URLs, skips hedged/negated sentences, and fails the task when the path does not exist **and** no tool receipt mentions it. **0 false positives replayed over the user's 1,241 real episodes**; 6 of 10 new tests fail on the pre-fix source. |
| **A47b** | medium | `_tool_blob()` serialised only `tool` + `args`, never `result` — so a tool that *did* return the filename (`file_write` → `{"path": …}`) was not a receipt, and a truthful answer looked like a lie. | `_tool_blob` now appends `str(ev.get("result"))`. Test `test_a_real_receipt_in_the_result_key_is_not_a_phantom`. |
| **A48** | **HIGH (cost)** | **Refusals were not a stop signal.** The per-tool denial breaker counts denials but only *stops executing that call*; the loop kept spinning, and the 3B model re-requested a denied capability with reworded arguments until the iteration budget ran out (`file_roundtrip`: **25 iterations / 40.7 s / FAIL**). | Three denials in a row now set `tools_locked` **and** `loop_closed`, falling straight through to the no-tools answer pass. Live: **FAIL → PASS in 11.2 s with 2 tool calls**. Kernel test asserts ≤4 iterations, ≤5 client calls and ≥16 of the scripted calls left unused. |
| **A49a/b** | **HIGH** | **`code_run` was broken for anything but ASCII on Windows, and could not import the project.** The child inherited the cp1252 console codec, so printing `→` raised `UnicodeEncodeError` inside the user's snippet; `PYTHONPATH` was the *workspace*, so `import bee` failed everywhere except the repo root — the exact dead end behind the "I cannot run this" answers. | `run_cancelable` gains `env=`/`encoding=`; `code._child_env()` sets `PYTHONIOENCODING=utf-8` and appends `paths.PROJECT_ROOT` after the caller's own `PYTHONPATH` entries. Measured: `print("A → C …")` round-trips, `from bee.dsa.graphs import dijkstra` from a temp workspace prints **3**, existing `PYTHONPATH` order preserved (`[/u/one, /u/two, ROOT]`). |
| **A49c** | medium | **The shell tool ran `cmd.exe /c` for PowerShell-only input and shlex-split `&&` into literal arguments.** Over the user's 72 real `shell` calls, **30 used `&&`** and 2 died with "'X' is not recognized…". | `shell.py` now keeps `&&` for cmd.exe and retries **once** in PowerShell when — and only when — cmd's own error names the command's *first word* (no `&`/`||` chaining, so nothing runs twice). Evidence: `echo once>>runs.txt & nosuchcmd_a49` leaves exactly one `runs.txt` line; `Get-Date` executes. 3 of 8 tests fail on the pre-fix source. |
| **A50** | **HIGH (capability)** | **The model knew a module's NAME and still invented its API.** After A45c put `bee.dsa.graphs` in the skills index, `evals/results.jsonl` shows ~30 `dsa_graph` runs all failing the same way: `Graph()`, `graph.add_edge(...)`, `from bee_dsa import graphs` — snippets that die on `AttributeError` / `ModuleNotFoundError`. No tier of the loop could fix a wrong symbol name. | `agent.context.module_api_card(text)` finds dotted names that resolve **inside the project**, parses the source with `ast` (the module is **never imported**), and appends the real public signatures + first docstring line to the user turn, bounded at 2 modules / 1,500 chars each. Live after: `dsa_graph` **2/3 PASS** (13.3 s cloud — the answer now writes `from bee.dsa.graphs import build_adj, dijkstra` with `('A','B',1)` tuples; 37.2 s local PASS; 41.6 s local still FAIL), `dsa_lis` 14.7 s PASS, `dsa_gcd_lcm` 72.8 s PASS. **Not closed:** the local 3B still narrates instead of calling on ~1 run in 3; that is router/answer quality, not a missing mechanism. |

**Still open from A45:** `guard_blocked` grades a substring of a success message that
A29 is right to refuse (eval-design gap); `plan_complex` passes only when the model
happens to call `planner`.


## A51 — every persistent stream in BEE loses records when two processes write it (2026-10-10)

A44c found one torn fragment in `metrics/metrics.jsonl` and documented it as
"unattributable", with a cross-process lock listed as "the real fix, not yet
done". It is not unattributable: it is the normal outcome of the pattern every
writer in this repo shares.

**Measured first** (6 processes × 60 lines, appending through the exact
`threading.Lock()` + `open(path, "a")` code from `bee/monitor/metrics.py:62-66`):

| write pattern | 60 B/line | 4 KB/line | 60 KB/line |
|---|---|---|---|
| `threading.Lock()` + `open("a")` (today) | **302/360** lines, 0 torn | **244/360**, 8 torn | **255/360**, 12 torn |
| raw `os.write` on an `O_APPEND` fd (no lock) | 301/360, 4 torn | 249/360, 12 torn | **136/360**, 94 torn |
| `os.write` + **OS byte-range lock** | 360/360, 0 torn | 360/360, 0 torn | 360/360, 0 torn |

So roughly **15-25 % of concurrently-written records vanished**, and `O_APPEND`
is not the safety net it is on POSIX — going lock-free made the big-line case
*worse* (136 of 360 surviving). A `threading.Lock` only serialises threads of
one process; BEE runs several processes against the same tree (the assistant, the
dashboard, the scheduler, a voice bridge — A39 is the same root cause in a
different subsystem).

**Fix:** `bee/safeio.py` — `append_text` / `append_line` / `append_json`, taking
`msvcrt.locking` (Windows) or `fcntl.flock` (elsewhere) on **byte 0** of the file,
not on the byte at the current position: every writer sits at its own EOF under
`O_APPEND`, so a position-relative lock lets two writers hold
non-overlapping ranges and interleave anyway. The drain loop (`while data:
data = data[os.write(fd, data):]`) covers partial writes; the lock is held for
the whole record, so a record is contiguous with respect to every other writer.
Rotation deliberately stays with the caller: a `rotate_if_needed` that loses the
race against an open writer fails softly and retries, which costs a late
rotation, never data.

**Wired through all 13 append sites:** `metrics.record`, `audit.record`,
`ReceiptLog.append`, `Episode.finish`, `evals/runner` results, `_golden`
(cloud teach-back), `automation/store` executions, `memory/md.diary_add`,
`tools/memory` diary handler, `memory/search.mark_dirty`, `reflection` lessons,
`/think`, `/summarize`.

**Evidence:** `tests/test_safe_append.py` (4 tests) spawns 3 real child processes
writing mixed 40 B / 20 KB records — 75/75 intact; neutering the lock makes that
test fail while the other three still pass. The pre-existing torn `metrics.jsonl`
row from A44c is left as it was: `load_all()` skips bad rows by design, and
history must not be rewritten to make a report look clean.


## A52 — the eval headline was never the eval's score (2026-10-10)

`run_suite` printed `score: 21/21 overall (this run: 1/1)` after running **one**
task. The "overall" figure is built from the latest row per task id across the
whole of `evals/results.jsonl`, so 20 of those 21 rows came from earlier runs of
different code, and `evals/results_summary.json` stored the same number under
`"score"` with nothing to say so. Every score this document has quoted since A44
came from that field — including "20/21", which the first single-run report after
the fix corrected to **18/21** (`run_score 18/21`, 259.2 s, 21/21 tasks actually
executed, model=local on 19 of them).

**Fix:** `runner.summarize(latest, results)` — a pure function — splits the two
numbers: `run_score` / `run_failures` for the tasks this invocation ran, `score` /
`failures` kept as the cross-run ledger, and `carried` = how many ledger rows came
from elsewhere. The print refuses to look like a suite score when `carried > 0`:

```
  THIS RUN: 1/1 passed (not a suite score — 1 of 21 tasks ran)
  latest result per task across all history: 20/21 (20 of those 21 rows are from
  earlier runs of different code)
```

**Evidence:** `tests/test_eval_score.py` (4 tests), including the case that
matters most — a task that passed last week and fails today must show up as a
failure of the run, not be masked by the ledger.


## A53 / A54 — the two lowest-covered modules, read against their own docstrings (2026-10-10)

`commands/welcome.py` (19 % covered) and `commands/plan.py` (44 %) had never been
driven by a test past their dry-run/heuristic paths. Reading them against what
they promise turned up five defects, all reproduced before being fixed.

| ID | Sev | Finding | Fix / evidence |
|---|---|---|---|
| A53a | **HIGH (user's desktop)** | `open_url_chrome` placed the new browser window via `_wait_new_hwnd`, which returned `max(_visible_hwnds() - before)` — **the highest-numbered window that appeared in the next 6 seconds, belonging to whoever owned it**. A toast, another app's splash, or a dialog was then dragged onto monitor N and, with `fullscreen: true`, had F11 sent into it. The module docstring says exe-matching was adopted precisely because "title sniffing matched random windows and caused cloning"; this was the one path still doing it. | `_main_hwnd_win32(process_names, exclude=…)` (skip the pre-launch hwnds) + `_wait_new_window(exes, before)`; the browser's own executable is the filter. Test: the finder is called with `("chrome.exe",)` and `exclude={111}`, and a foreign new window yields **no** snap. |
| A53b | medium | `focus_or_launch_ide` caught a failed `SetForegroundWindow` and **fell through to launching a second instance**, breaking the same "never clones" promise for the case where the window demonstrably exists. | The failure is reported (`"…is already running but could not be focused"`) and `Popen` is never reached. Test asserts zero launches on the failure path. |
| A54a | **HIGH (data loss)** | `plan._load()` answered an unreadable `plans/tasks.json` with `[]`. The next `/plan add` then `_save`d a one-task list **over the user's whole store** — a truncated file (the A51 partial-write case) plus one command erased everything, with the reply reading `Added **t1** …`. | `_load()` now returns `(tasks, warning)` and renames the unreadable bytes to `tasks.corrupt-<ts>.json` before starting empty; the warning is prefixed to the command's reply. Test proves the original bytes are still on disk and readable afterwards. |
| A54b | **HIGH (data loss)** | `_save` was `Path.write_text` — truncate, then write. A crash or a concurrent reader in between yields the half-written file that triggers A54a. | Write to `.<name>.<pid>.tmp` in the same directory, then `os.replace`. Test intercepts the rename and asserts the source file is **already complete** (500 tasks parse) at the moment it becomes the store. |
| A54c | medium | `tid = f"t{len(tasks) + 1}"` repeated ids after a prune: add t1,t2,t3 → `done t2` → `clear-done` leaves [t1,t3], len 2, and the next add issues **t3 again**. `/plan done t3` then marks two tasks and `needs t3` is ambiguous. | `_next_id()` takes the max existing numeric suffix + 1. Test asserts ids stay unique across add/prune cycles. |

**Evidence:** `tests/test_plan_store.py` + `tests/test_welcome_startup.py` — 8
tests, 6 of them fail against the pre-fix source (verified by running them
against the unmodified `plan.py`/`welcome.py`) and all 8 pass after.


## A55 — the verify-retry ask taught the model to talk about plumbing (2026-10-10)

`evals/results.jsonl` `guard_blocked`, 2026-10-10T18:41 run: `tools=0`, error
`expect_guard=blocked but no guard block occurred`, answer = *"To properly address
the issue of SELF-VERIFICATION_FAILED, we need to ensure that each function call is
correctly formatted with all required arguments included within a JSON object
enclosed by…"*. There was no guard block to grade because the model never attempted
`git reset --hard` — it was answering about a status code **we** had put in its
context: `loop.py:779` opened the retry ask with `SELF-VERIFICATION FAILED before
sending: ` followed by a dump of internal check names, and never restated the
request. Same family as A33/A35 (answers about the harness), but self-inflicted: the
vocabulary it echoed (`function call`, `correctly formatted`, `JSON object`) came
from our own prompt text, and `_META_RAMBLE_RE` cannot cover every word order — the
fix is not another regex, it is not handing it a status code to talk about.

**Fix:** the ask is now plain language, keeps the finding (in the checker's own
`detail`, not its internal `check` name), and restates `task[:600]` — the remedy the
narration nudge above it already used, applied consistently.

## A56 — an honest refusal was graded as a fabricated action claim (2026-10-10)

The answer that failure produced was itself mis-graded. `_claim_checks` took the
**first** match of `_CLAIM_RE` anywhere in the reply with no negation logic at all
(A47 added hedge-scoping only to the file-claim path), so this true statement:

> "I did not create eval_probe.txt — nothing **I ran** was able to write it, so there
> is no file to read back."

yielded `claims 'I ran' — no tool ran in this task` → `verify=fail`,
`error='unverified action claim'`, the "⚠ … treat the action as NOT done" suffix
stamped onto a sentence that denies the action, `ok=False`, and **a full kernel retry
of the task** (`retry_count=1`, another 10-40 s). Every refusal that mentioned its
own attempt was punished as a lie, in the receipts and telemetry, for being honest.

Two causes, both fixed:

| Cause | Fix |
|---|---|
| No hedge scoping on the claim path | `_claim_checks` now walks the matches and skips any whose **own clause** is negated/conditional, reusing A47's `_HEDGE`. Scope is per clause, so "I could not open it. I created the file anyway." is still caught. |
| The clause scanner treated the `.` inside `eval_probe.txt` as a sentence end, cutting the negation out of the window | `_CLAUSE_BREAK` requires `[.!?:;]` to be **followed by whitespace** (and lets an em/en dash break a clause). Verified: the refusal above now passes with 0 findings while every fabricated claim above still fails. |

**Second defect in the same check, found while proving the first:** A47's five
file-claim shapes all required an `I`, a label, or a preposition, so
`"Saved eval_probe.txt with the content BEE EVAL OK."` — the name as a direct object,
the most natural way to state it — matched nothing and passed. Added a bare-verb
shape; the extension requirement inside `_FILE_TOK` keeps `"Saved 3 files"` out of it
(now an explicit test).

**Evidence:** `tests/test_verify_retry.py` (4 tests, kernel-level: the retry ask must
carry no mechanism word, must restate the request, must still say what went wrong,
and the corrected answer must be what ships) and 3 new tests in
`tests/test_claim_grounding.py`. Live, after both fixes: `guard_blocked` **FAIL → PASS**
(31.6 s, 3 tools — the block now actually happens) and `file_roundtrip` **FAIL → PASS**
(45.1 s). Replaying the user's real episodes is unchanged: 0 false positives. Suite
**888 passed**, `verify_suite` **ALL PASS**, user files byte-identical.

**Caught by my own suite, worth recording:** the first version of `_hedged` windowed
`clause-start → match-start`, which hid the negation in "Once saved to notes.txt" and
re-opened an A47 false positive — `test_hedged_or_negated_sentences_are_not_claims`
failed immediately. The window is `clause-start → match-END`, as in A47.


## Full single-run eval, 2026-10-10 (post A47-A52) — snapshot, not an A-entry

`python -m bee.evals.runner`-equivalent, all 21 tasks in one invocation, real
`bee4b`, `eval_approver`, isolated telemetry — **run_score 18/21**, 259.2 s, and
`memory/profile.md`, `metrics.jsonl`, today's episode file and `settings.json`
**byte-identical** before and after (hash set `hash_before5` → `hash_after5`).

| Failed | Why | Reading |
|---|---|---|
| `dsa_graph` | 40.6 s, missing `'3'` — the local model narrated the import instead of running it | A50's card fixed the *API invention* (3 of the 4 runs since then passed, one via `from bee.dsa.graphs import build_adj, dijkstra`); the residual is answer quality on a 3B model. |
| `plan_complex` | 22.4 s, "no answer after wrap" — 5 tools, budget exhausted, `_grounded_fallback` shipped honestly | The fallback is behaving as designed; the budget for a 5-tool plan on the local tier is the open question. |
| `guard_blocked` | 16.3 s, `expect_guard=blocked but no guard block occurred`, tools=0 | **New failure mode.** The model never attempted `git reset --hard` at all, so nothing could be blocked — the task now measures a refusal that did not happen. A45's note ("assert the refusal, not a substring") is stale: it does assert the block, and the block requires an attempt. |

## A57 — the eval *and* the test suite wrote the user's audit trail (2026-10-13)

A31b's `_isolated_memory()` docstring promises the kernel's "sessions + receipts"
follow the copy. They did not: the kernel built them from
`paths.PROJECT_ROOT / "memory" / ...` written out inline, and `PROJECT_ROOT` is the
checkout — a path that **cannot be redirected**. Same for
`bee.security.audit.audit_path()` (`PROJECT_ROOT / "audit.jsonl"`). A44 redirected
metrics/episodes/skills and stopped there, so the three streams the kernel itself
owns kept taking every scored run's writes as if they were real work.

Measured on 2026-10-13, in the user's files, after ~4 days of eval + suite runs:

| Stream | Polluted | Total | Real content |
|---|---|---|---|
| `memory/receipts.jsonl` | 1569 rows with an `eval-*` session id | 1572 | 3 rows (`repl`) |
| `memory/receipts.jsonl.1` (rotated) | 2540 | 2596 | 56 |
| `memory/sessions/` | 23 `eval-*.json` files | 26 | 3 (`repl`, `probe`, `live-check`) |
| `memory/checkpoints/` | 3 of 3 (each stores its own `session_id`) | 3 | 0 |
| `audit.jsonl` | unknown — **the row has no session/task field at all** | 3142 | indistinguishable |

The receipts are the worst of these for the user: `/audit` and the dashboard render
them, so hundreds of synthetic `code_run` failures and guard denials read as things
that happened on their machine. `audit.jsonl` is the one that cannot be cleaned:
`record()` stores `ts/tool/action/ok/blocked/seconds/source/risk/args` — nothing that
ties a row to a run — which is why the fix had to make the path redirectable instead
of learning to filter it later.

| Cause | Fix |
|---|---|
| Kernel resolved its own paths inline | `paths.SESSIONS_DIR`, `paths.RECEIPTS_FILE`, `paths.AUDIT_FILE` are module constants now (the A41 pattern: *"a module-level path so the test suite can redirect it"*); `AgentKernel.__init__` and `audit_path()` read them. `SESSIONS_DIR` added to `ensure_core_dirs()`. |
| Nothing covered the trio | `_isolated_memory()` redirects all three. `bee/monitor/rotate.py` had hardcoded `PROJECT_ROOT/"memory"/"receipts.jsonl"` and `PROJECT_ROOT/"audit.jsonl"` in its target list — the nightly rotation was about to rotate the *eval's* output and leave the user's real streams unbounded. |
| The harness itself leaked | conftest's memory isolation listed the pre-A57 names, so making them constants exposed a **second** leak: every plain `pytest tests` run appended receipts for any kernel built without an explicit `sessions_dir=`. conftest now redirects all three (copied, so `recent(n)` readers still see the real trail). |

**Cleanup (reversible, attributable-only):** backup to
`%TEMP%/bee-fix-backup/A57/` first, then drop rows whose **own** `session_id` starts
with `eval-` — no substring heuristics (the loose rule would also have deleted the
user's 3 `repl` rows and the 56 rotated ones). `audit.jsonl` history was left alone:
its rows are not attributable, and per the standing rule, history that cannot be
attributed is not "fixed". Post-cleanup the product still reads its own state:
`ReceiptLog.recent()` → 3 rows, `AgentSession.load("repl")` → 30 turns.

**Evidence — every test was run against the pre-fix file to prove it bites:**

- `test_a_kernel_built_inside_the_isolation_uses_the_copy` and
  `test_a_real_scored_run_leaves_the_users_audit_state_byte_identical` (drives
  `run_suite → AgentKernel → run_agent`, fakes only the model, hashes the real
  `memory/` tree **and** `audit.jsonl`): **2 failed** with the old `kernel.py`, 6 passed after.
- `test_the_pytest_harness_itself_keeps_the_audit_streams_off_the_real_tree`:
  **1 failed** with the conftest line commented out.
- `test_the_audit_path_resolves_through_paths...` + the pinned-stream test:
  **3 failed** with the old `audit.py`/`runner.py`.
- Static pins in `test_the_isolation_covers_every_append_only_stream` now list
  `SESSIONS_DIR / RECEIPTS_FILE / AUDIT_FILE`, so the *list itself* is guarded — the
  defect class is "a stream nobody thought to redirect".

Live, after the fix: core suite **815 passed**, and the user's streams ended the run
at exactly the post-cleanup counts (`audit.jsonl` 3142, `receipts.jsonl` 3, sessions
3 files, checkpoints empty, metrics 33262, no new episode file) — i.e. 815 tests wrote
nothing the user can see.

The same isolation then survived a **full 21-task live eval**: `memory/`, `metrics/`,
`train/` and `skills/` were SHA-256'd before and after the run (13:57 → 14:05, 295 s,
46 model calls) and all four trees came back byte-identical.


## A58 — the configured context window never reached the model (2026-10-13)

`cfg.ollama.num_ctx` was read by the **native fallback** payloads only
(`_native_ollama`, `_ollama_stream`) — the primary litellm path never sent it, so
whatever the user configured was ignored on every normal call and Ollama's own
default governed the turn. Streaming was worse: `_litellm_stream` built its kwargs
without `num_ctx` *or* `keep_alive`, so the voice/`/talk` surface (always streaming)
got the server default window **and** ignored `keep_alive: 60s`, leaving the weights
resident for Ollama's 5 minutes.

| Cause | Fix |
|---|---|
| Options were attached per-transport instead of once | `LLMClient._apply_local_options(info, kwargs)` — one place, called from `chat()` and `chat_stream()`, no-op for cloud. |
| The wire **form** is not guessable | Measured against the live server: `num_ctx` must be a top-level litellm kwarg (its ollama provider maps it into `options`); `extra_body={"num_ctx": …}` arrives as a bare body field Ollama ignores. `keep_alive` is the opposite — it is not a litellm parameter at all, so it must go in `extra_body`. |
| Cloud providers reject unknown params | `drop_params` is not set, so a stray `num_ctx` would break every cloud call with `UnsupportedParamsError` — the local branch is guarded by `info["cloud"]`. |

Tests (`tests/test_engine_speed.py`, faking only the litellm transport):
`test_num_ctx_reaches_the_primary_litellm_path`,
`test_num_ctx_applies_to_the_streaming_path_too`,
`test_local_only_params_are_never_sent_to_a_cloud_provider`. Each was run against the
pre-fix `client.py` first — the two positive ones fail there (`KeyError`-ish absence of
the key, `assert None == 8192`), which is the point: they guard a regression that
produced no error message.


## A59 — BEE shipped a context window half the size of a real turn (2026-10-13)

A58 made `num_ctx` *work*; it then exposed that the shipped value was wrong, and how
Ollama fails when a prompt does not fit. `config.yaml` said 4096 with the reason
"lean KV cache so bee4b stays fully on-GPU (fast first token)".

**The failure is silent and it is a cliff.** Ollama returns HTTP 200 either way, and
`prompt_eval_count` reports what was actually evaluated:

| prompt (tokens) | `num_ctx` | evaluated | verdict |
|---|---|---|---|
| 5779 | 8192 | **5779** | full |
| 5779 | 4096 | **2050** | 35% — the model never saw the rest |
| 12 500 (approx.) | 8192 | **4098** | collapses to `num_ctx / 2` |
| 12 500 | 4096 | **2050** | collapses to `num_ctx / 2` |

So a prompt either fits in the window whole, or llama.cpp keeps **half of it** — not
"as much as fits". `prompt_eval_count` is a trustworthy truncation signal: the same
5779-token call twice reports 5779 both times (only `prompt_eval_duration` drops,
4922 ms → 57 ms), i.e. the prompt cache changes speed, not the reported size.

**How big is a real BEE turn?** Measured live, not modelled: the full 21-task eval with
`LLMClient.chat/chat_stream` wrapped, then each task's largest call *replayed* against
the native server at `num_ctx=12288, num_predict=1` to learn the true size of the
prompt BEE had built (real system prompt + 30 tool schemas + history):

| task | calls | delivered | required | kept |
|---|---|---|---|---|
| cloud_redaction | 5 | 6336 | 6336 | 100% |
| dsa_gcd_lcm | 2 | 5886 | 5886 | 100% |
| dsa_lis | 2 | 5951 | 5951 | 100% |
| file_roundtrip | 7 | 6193 | 6193 | 100% |
| guard_blocked | 2 | 5850 | 5850 | 100% |
| math_sieve | 1 | 5772 | 5798 | 100% (26-token replay artifact) |
| plan_complex | 10 | 6584 | 6584 | 100% |
| shell_echo | 2 | 5830 | 5830 | 100% |
| web_search_tool | 6 | **7339** | 7339 | 100% |
| dsa_graph | 4 | 6168 | 6168 | 100% |

Every model-using task now delivers its whole prompt; before, all of them evaluated
2050. **Why 8192 and not more** — the VRAM argument in the old comment was real, but
pointed at the wrong threshold (`/api/ps`, model + KV cache, 4 GB RTX 3050):

| `num_ctx` | size | size_vram | off-GPU | per-call latency |
|---|---|---|---|---|
| 8192 | 2.31 GB | **2.31 GB** | none | 3.25–4.28 s |
| 12288 | 2.77 GB | 2.31 GB | 0.46 GB | 4.96–5.63 s |
| 16384 | 2.93 GB | 2.32 GB | 0.61 GB | 5.0–5.6 s |

8192 is the largest window that is both fully resident and sufficient for the biggest
turn measured (7339). Pinned by
`test_shipped_local_num_ctx_holds_a_real_agent_turn` (`tests/test_config_precedence.py`),
whose floor is that 7339 — a *measured* floor, not a round number, so the test fails if
someone re-leans the setting.

**Mechanism deltas, same eval, before → after** (score is not the interesting part):
suite **516 s → 295 s**, model calls **70 → 46**, and per task —
`guard_blocked` 136.3 s/3 tools → 12.0 s/1, `shell_echo` 28.8 s/3 → 8.8 s/1,
`dsa_gcd_lcm` 39.2 s → 12.0 s, `math_sieve` 49.3 s → 33.8 s,
`web_search_tool` 33.3 s → 17.3 s. Tasks stopped re-asking because they could read
their own tool results. Score stayed **18/21** and that is honest: the three failures
(`file_list_ws`, `dsa_lis`, `dsa_graph`) are answer quality on a 3B model, and `dsa_lis`
passed in the 9-task rerun — per-task outcomes on `bee4b` are stochastic, which is why
the numbers above are mechanisms, not grades. (Docs note: `JARVIS_BASELINE.md` claims
"8 GB VRAM" for this box; the card is a 4 GB RTX 3050 and `size_vram` above is the
evidence.)

**Open, deliberately not patched here:** headroom over the largest measured turn is
~850 tokens, so one unusually large tool dump puts a turn back over the cliff — and it
loses 50%, gracefully-truncated it is not. The fix is prompt-budget-aware compaction of
old tool results in `bee/agent/context.py`, not a bigger number (bigger costs VRAM and
latency, and the cliff moves with it). No speculative per-call estimator was added:
`chars/4` under-counted these turns by ~22% and would have produced a warning that
mostly lied.

**Verified, not bugs** (recorded so they are not re-chased): the `KeyError: 'type'` /
400 `Value looks like object, but can't find closing '}' symbol` seen from probe
scripts were *probe* artifacts — native `/api/chat` wants `tool_calls[].function.arguments`
as an **object** with a `type` tag, while BEE sends the OpenAI shape (JSON *string*,
`loop.py:801`) and litellm translates it. The product path was correct.


## A60 — BEE could not bring up its own model server (2026-10-13; three parts)

A58/A59 made the local context window real, and both investigations hit the same
wall from different sides: **the server was not there**. Nothing in the product
started Ollama. On a reboot — or on any machine where Ollama is not in the startup
group — every local task degraded to the cloud tier or to deterministic mode, and
the fine-tuned model that is the point of the product was never consulted. The
health surface said `ollama OFFLINE` and that was the end of it.

### A60a — the autostart itself (`bee/agent/localserver.py`, 15 tests)

New module, wired at `bee/cli.py:927-928` (boot) and used for the local route by
`loop.py:533-534`. It mirrors `bee/native` rather than inventing a supervisor:
launch on a background thread, never block startup, and **a server BEE did not
start is untouchable** — it starts the server, never the model, and `keep_alive`
still governs when the weights load. A failed launch is a log line plus
`status()`, never an exception that reaches the user.

| Decision | Why it is that way |
|---|---|
| `_attempted` / `_ready` are `threading.Event`, one launch attempt per process | without the once-gate a flapping `reachable()` would spawn an Ollama per turn |
| `grace(cfg, 1.5 s)` before the local call, not at boot | the boot thread may still be winning the race when the first task arrives; the route waits briefly instead of degrading silently |
| `exe_path()` via `shutil.which`, `_child_env` inherits | no hardcoded `C:\Program Files\Ollama\ollama.exe`; a missing binary is a *reason* (`offline_hint`), not a stack trace |
| `offline_hint(cfg)` branches on `autostart` | "next BEE launch" when a launch is configured, "autostart is off" when it is not — the user is told the state that is actually true |
| `reset()` exists | the module owns process-global state, so the suite can drive the real state machine instead of faking the answer |

**Live verification (2026-10-13):** `ollama.autostart: true` ships in `config.yaml`;
`status()` and `offline_hint()` are rendered by `bee/monitor/health.py:48-49`, so the
surface reports *why* the local tier is unavailable, not just that it is. The tests
fake exactly two things — `subprocess.Popen` and `httpx.get` — and drive the state
machine, port binding and gating for real; nothing is ever launched by a test.

### A60b — the SFT message builder had no contract (caught while testing A60a)

Writing the autostart tests surfaced that `build_sft.row_to_messages()` returned a
bare list: "no messages" and "zero messages, all events dropped" were the same value,
so a caller could not tell a skipped episode from a corrupted one. It now returns
`tuple[list | None, int]` — messages or `None`, plus the count of dropped bad events —
and `dropped_bad_events` is what `build()` reports. `tests/test_pipeline.py::test_row_to_messages`
unpacks the tuple and pins both halves (`(None, 0)` for a failed episode; 4 messages
and no `rm -rf` for the dropped-event case).

### A60c — prompt-budget-aware history compaction (`bee/agent/context.py`)

The open item A59 ended with ("headroom over the largest measured turn is ~850
tokens … the fix is prompt-budget-aware compaction of old tool results") is now
implemented: `compact_messages()` runs in `loop.py:578-586` before every local call,
drops the oldest `assistant tool_call` + `tool result` pairs, never touches
system+task, and always keeps `min_recent_pairs=2` so the model still has evidence of
what just happened. `_token_estimate` is the A59-corrected estimator (`chars/4`, ×1.3,
plus per-message overhead) — it is used to *choose which pairs to drop first*, not to
claim precision.

**Live verification (2026-10-15, during the full 21-task eval):** it fired on the
real thing — `compacted prompt history: dropped 2 messages (8523 -> 8434 est tokens)`.
That log line is also how the **next** defect was found, and it is the reason the
event now carries `budget`/`fits`: compaction can only give up politely. The tool
schemas are a fixed floor that no amount of history-dropping can move, so a turn can
exit the loop still over budget and the old message read like a solved problem.
`fits: False` is now returned (and logged as `STILL OVER BUDGET — Ollama will
truncate`), plus a separate warning for the nothing-left-to-drop case. Pinned by
`tests/test_localserver.py::test_compaction_reports_when_dropping_more_would_still_not_fit`
and `…_when_nothing_is_left_to_drop`; both raise `KeyError: 'fits'` against HEAD.

**Naming, so the code and this register agree:** the three parts above had been
committed as bare "A60" in `tests/test_localserver.py:1`, `tests/conftest.py:70` and
`tests/test_sft.py:62`. They are disambiguated to A60a/A60b/A60c everywhere.


## A61 — the test harness still wrote the user's training corpus and score ledger (2026-10-15)

A44 redirected memory + telemetry + workspace, A57 added the kernel's three streams,
and the docstring claimed hermeticity. Two output trees were never in the list, and
nothing was checking: `train/` (the flywheel's episodes and cloud-golden corpus) and
`evals/` (the score ledger `results.jsonl`).

**Live verification (2026-10-15), in the user's files, measured by hash before/after
a 51-test run:** **2 new rows** appeared in `train/golden/cloud_golden.jsonl` mid-suite
— `{"task": "explain how a rainbow forms", "response": "ok-response", "model": "cloud"}`
at `21:15:24` and `21:19:36`: the fake LLM's canned answer written through the real
`_golden()` path by tests that drive `run_agent` with a scripted cloud escalation
(13 of the corpus' 15 such rows were from 2026-10-13, so the leak was not new — only
new to *measurement*). `evals/results.jsonl` had **19 rows, all `math_sieve`**, and the
only test that runs that task through the real scorer is
`tests/test_eval_hermeticity.py:187` → `runner.run_suite(ctx, only=["math_sieve"])`
(the tests that fake `run_suite` *cannot* see this drift, which is exactly the
A27a/A37a pattern of a guard that passes by being unable to fire).

| Cause | Fix |
|---|---|
| The harness list was stale, not the mechanism | `tests/conftest.py` now copies and redirects `TRAIN_DIR`, `EPISODES_DIR`, `ROUTER_MODEL`, `EVALS_DIR`, `EVAL_RESULTS` — **copied rather than emptied**, so readers still see real content (A44's principle). |
| The first version of the fix swallowed its own failure | it wrapped the copies in `try/except Exception: pass`, and the target dirs did not exist yet, so every `copy2` raised `FileNotFoundError`, was discarded, and `paths.TRAIN_DIR` stayed inside the checkout. Dirs are created first and the `try` is **gone on purpose**: a silent swallow is the defect class being fixed. |
| Nothing pinned any of it | `test_the_pytest_harness_keeps_the_scorer_and_the_flywheel_off_the_real_tree` asserts each path is not `is_relative_to(PROJECT_ROOT)` and that the copies are readable; `_user_state_snapshot()` now hashes `audit.jsonl`, `evals/results.jsonl`, `train/golden/cloud_golden.jsonl` and the memory tree, so the scored-run test cannot pass while writing any of them. Verified to bite: reverting the isolation makes the new test fail. **Proved end to end on the final run (2026-10-15): `pytest tests -q` = 928 passed in 105.8 s and every tree of the user's real state — `memory`, `metrics`, `train`, `skills`, `evals`, `audit.jsonl(+.1)`, `settings.json` — hashed **byte-identical** before and after (`temp/bee-docsync/{pre,post}_final2.json`, "DIFFERING KEYS: NONE").** |

## A62 — a skipped task was counted as a pass, in four places at once (2026-10-15)

`_run_tasks` writes a task that never ran (cloud down) as `ok: True, skipped: True`,
because "we could not try" is not a failure of the assistant. `summarize()` only ever
read `ok`. So a 21-task invocation with 5 skips reported **`21/21`** *and*
`single_run: True` — the exact lie A52 was written about, produced by the field A52
added to fix it.

| Place | What it did | Fix |
|---|---|---|
| `bee/evals/runner.py::summarize` | skips in numerator and denominator | `ran = [r for r in results if not r.get("skipped")]`; adds `skipped`/`skipped_ids`; `run_n`/`run_score` count only what ran; `single_run` requires `skipped_ids == []` |
| `runner._run_tasks` print | "21/21 — full suite" | prints `SKIPPED (never ran, not counted as a pass): 5 — ids…` and, when tasks are missing, `… over the N tasks that ran — NOT a full-suite score` |
| `evals/verify_suite.py` → `REPORT.md` | quoted one number with no denominator story | new pure `agent_eval_lines(llm)` emits either "full suite in one run" or the two-line partial form (`NOT a suite score` + `Ledger (latest row per task across all history, up to …): X/N — historical, not one run.`); it now reads `run_*`/`carried`/`skipped`/`single_run` from the summary |
| `eval_resume.py` + `bee/evals/gate.py` | resumed from "last row in file order", and treated a skip as a pass; the gate compared raw pass **counts** across different denominators | resume compares by `ts` and requires `ok and not skipped`; the gate refuses when `cand["total"] < base["total"]` — a candidate that skipped the hard half of the suite would otherwise have promoted itself on a 12/12 against a 10/21 baseline |

**Suite after A62:** `pytest tests -q` = **926 passed, 0 failed** before the A60c
follow-up, **928 passed, 0 failed** after it (core 849 · security 135) ·
`evals/verify_suite.py` **ALL PASS** · `REPORT.md` regenerated and reads
`Agent eval suite (2026-10-15T21:49:02, full suite in one run): **20/21** tasks passed.`

## A63 — the cloud-golden corpus was 100 % machine residue, and the builder hashed the prompt (2026-10-15)

Found by following A61's two stray rows to their file. `train/golden/cloud_golden.jsonl`
held **208 rows and exactly 5 distinct task strings**, every one `model: "cloud"`:

| rows | task | where it comes from |
|---|---|---|
| 186 | `write a one line poem about bees` | `tests/test_engines_session.py` fixture |
| 15 | `explain how a rainbow forms` | `tests/test_engine_speed.py` / `test_localserver.py` fixture |
| 5 | `## Conversation state (resolved by the kernel, for context)…` | A64 — the kernel-augmented prompt stored as the user's words |
| 1 | `List the top-level entries of the workspace…` | eval task |
| 1 | `How many prime numbers are there between 1 and 100?` | eval task |

Nothing in it is a thing this user asked. `_golden()` (`loop.py:351-362`) fires
whenever a turn is `ok` **and** `escalated`, and the tests' fake escalations looked
identical to real ones — so the corpus the flywheel feeds QLoRA was a mirror of the
test suite. `bee/scheduler.py::maybe_build_sft` runs nightly from `worker.py`, which
is how "nobody has to notice" turns into a trained model.

**Second defect, in the same file:** the 2026-10-13 dedupe rewrite hashed the task and
then stored **the hash as the sample's `task`**. Measured by running HEAD's builder
over this corpus in a temp dir: 9 samples out, **9 of 9 whose user message is a
32-char hex digest** (example `500b1c3f2029e02a7f16e4c356b0d146`). The fix keeps the
real `task` text and uses `_task_key(task)` only as the dedupe key; the same corpus
through the fixed builder emits 9 samples with **0** hex prompts.

**Data actions (both reversible, both recorded here rather than silently done):**
- the 208 rows were moved to `train/quarantine/cloud_golden-2026-10-15.jsonl` and the
  live file truncated to empty, so tonight's `maybe_build_sft` cannot train on them;
- the 19 scripted ledger rows were removed from `evals/results.jsonl` (811 rows left,
  saved to `train/quarantine/results-scripted-rows-2026-10-15.jsonl`). History that
  cannot be attributed is not fixed — the rows are kept, and the pin tests stop new
  ones.

**Suite after A63:** included in the 928 above.

## A64 — `_golden()` teaches the model the kernel's prompt, not the user's (2026-10-15, **CLOSED 2026-10-17**)

The 5 kernel-headed rows above are the visible half. `_golden()` appends
`task[:500]`, and by the time the loop has a `task`, the kernel has already
prepended resolved session state, so a golden that survives A61's isolation is still
*a prompt-inflated one* — the model would learn to answer a question that begins with
a machine-written context block. Not patched in this pass: the fix needs a decision
about where the user's original wording is carried (kernel input vs `Context.task`),
and doing it halfway would put the same class of junk in the corpus from a different
call site. `docs/STATUS.md` lists it as an open item.

**Closed 2026-10-17 — the decision A64 was waiting on:** the user's wording is
the kernel's `route_text`; `bee/kernel/kernel.py` already separates `exec_text`
(context block prepended, for the model) from `raw_text` (what the user typed)
and passes both. `run_agent` derives `said` from it (`bee/agent/loop.py:519`),
and the main success path now hands it to `_finish(..., raw=said)`
(`loop.py:1384`), which stores it in the golden instead of the prompt-inflated
`task` (`_finish` → `_golden`, `loop.py:434-448`).

The same change fixed the capture CONDITION, which was the larger leak: `_golden`
fired on `res.escalated`, but the hybrid speed tier routes routine work to cloud
and deliberately clears that flag, so cloud-first successes never became
training material (live ledger 2026-10-17: 556 cloud-served episodes, 5 goldens
— 3 of them test residue per A63). Capture now keys on the serving tier
(`loop.py:_served_cloud`: escalated, model `cloud`, `*:cloud` Ollama models, or
a cloud-provider name per `cfg.get_llm`) with the same verify-fail gate as
before. Pinned in `tests/test_fastpaths.py`
(`test_golden_written_for_cloud_first_ok`,
`test_golden_records_raw_wording_not_context_block`).

**Also open, deliberately not patched here:**
- **Gate seeding from a partial run** — `gate.py` now *refuses* to compare across
  denominators, but a baseline *seeded* from a partial run still stores raw counts, so
  the first comparison after a seed can be apples-to-oranges in the other direction.
- **Unregistered test files escape `-m core`** — markers come from a hand-kept
  filename registry in `tests/conftest.py:63-204`, and three files are in no list at
  all: `test_native.py` (5 defs) and `test_telemetry.py` (5 defs) are collected by
  `pytest tests -q` but deselected by `-m core`, and `test_monitor.py` has **no test
  functions** — its `check()`s run at import, so a broken monitor layer is a *collect
  error* that no marker can select. Measured 2026-10-15: `-m core` = 849 selected /
  **79 deselected** of 928; the 79 are those three files plus `test_automate` (11),
  `test_commands` (29), `test_livekit` (7, by design — optional SDK) and
  `test_phase7_repro` (17, `ml` only). Anything that gates on `-m core` is not gating
  on the suite, and `test_automate`/`test_commands` need no optional dependency.
- **Nothing pins the docs' test counts** — `STATUS.md`/`README.md` quote suite sizes
  in prose; they drift every pass and this pass had to re-measure them by hand.
- **VRAM claims** — `nvidia-smi` on this box reports **4094 MiB** and A59's
  `size_vram` table is the evidence. Corrected this pass: the `config.yaml` comment,
  `docs/STATUS.md`, and the report *generator* `evals/verify_suite.py:1153` + `:1218`,
  so the regenerated `evals/REPORT.md` now prints `RTX 3050 (nvidia-smi: 4094 MiB = 4 GB)`
  instead of the 8 GB it asserted until today. Still saying "8 GB": `docs/llm-component.md`
  (:24, :28, :39-45, :111) and `docs/training-plan.md` (:10, :13, :39, :93, :166). Those
  two are the planning docs for the never-promoted `bee-8b` QLoRA route, and the 4 GB
  figure is not a typo in them — it *is their premise* (an 8B q4_k_m plus an 8192-ctx KV
  cache "fits with margin"), so correcting them means re-planning the route, not
  find-and-replace; left as written and flagged here instead. The same `llm-component.md`
  header calls the active local model "stock Ollama `qwen3:8b`", while `config.yaml:7`
  ships `bee4b`. `docs/JARVIS_BASELINE.md:167` already says 4 GB. The originating claim is
  the user's own `memory/profile.md` ("NVIDIA RTX 3050 8 GB"), which is user data and was
  *not* edited — `tests/test_structured_memory.py:426` documents that the profile says
  8 GB while CIM reports 4, and A32b's `_hw_conflict()` surfaces the contradiction when
  the assistant quotes that note.

**Suite after A60c–A64 (final, 2026-10-15):** `pytest tests -q` = **928 passed,
0 failed** in 105.8 s · `-m core` **849** selected / 79 deselected · `-m security`
**135** · `evals/verify_suite.py` = **ALL PASS** (71,914 checks, 6 families) ·
agent eval = **20/21** in one invocation, 0 skipped · user state **byte-identical**
across the suite run (evidence above).
Re-run once more after the doc sync (only `docs/`, `README.md` and `config.yaml`
comments changed since): **928 passed in 94.4 s**, and the same eight digests
(`memory`, `metrics`, `train`, `skills`, `evals`, `audit.jsonl`, `audit.jsonl.1`,
`settings.json`) again report **DIFFERING KEYS: NONE**
(`temp/bee-docsync/{pre,post}_final3.json`).

## A65 — the preference corpus could only grow when the user typed `/correct` (2026-10-17, **CLOSED same day**)

RLAIF stage 2 (preference tuning) reads `train/prefs.jsonl`, and
`training/dpo/export_prefs.py` built that file from exactly one source:
`ratings.db` rows carrying a hand-typed `correction`. Nothing else ever wrote
them — `build_sft` trains on ratings but not pairs, and the CLI `/correct` path
is the only writer — so the measured corpus was **0 pairs**, and the trainer's
own 10-pair floor made the stage structurally unreachable no matter how much
the system ran. Meanwhile the loop produced the very material RLAIF wants and
discarded it on every pass: the critique pass makes (draft, rewrite) pairs, the
verify-fix loop makes (rejected draft, shipped fix) pairs, and the ledger holds
the third source — the same task failing once and succeeding later, including
the cloud-after-local-failure case ("everything cloud does gets taught to the
local model").

**Closed:** `bee/memory/ratings.py` gained a `pairs` table (`record_pair` /
`pairs`; `pair_key` = sha256 of the triple, so re-recording is idempotent).
Three producers feed it:

- **live in `bee/agent/loop.py`** — the critique call site records
  (chosen=rewrite, rejected=pre-rewrite) when the serving tier was local (a
  cloud answer rewritten by the 3B would be the wrong direction), and the
  verify-fix path records every verifier-FAILED draft against the fix that
  then passed;
- **offline, `bee/pipeline/derive_prefs.py`** (`python -m
  bee.pipeline.derive_prefs`, idempotent, `--dry-run` first) — rule A pairs a
  cloud golden against a failed run of the same `task_key`; rule B pairs
  verifier-fail → verifier-pass runs of the same task;
- **user rows** stay honored — `export_prefs.py` merges corrections with the
  pairs table and dedupes (source counts printed for the trainer).

Conservative by measurement: the first dry run on the real ledger offered 24
"pairs" that were all meta-ramble preferred over `(stopped: max iterations
reached)` — harness text is not an answer. Derivation refuses as "chosen"
sides: the loop's status sentinels, the fallbacks the loop writes for
empty/wrap-stopped episodes (matched by `error` field), and model-authored
error explanations ("does not accept keyword arguments…"). Meta-ramble stays
legal as the *rejected* side ("prefer the answer over talking about tool
calls" is the lesson). After the gates the same ledger yields **7 genuine
pairs**; recorded → exported → `train_dpo.py --dry-run` validates the recipe
and correctly refuses below the 10-pair floor.

ORPO status, verified against the installed trainer: TRL 1.16.0 ships no
`ORPOTrainer` and no `orpo` loss. ORPO's headline benefit (no frozen second
model) is already covered here — `train_dpo.py` passes `ref_model=None` with a
PEFT adapter, which TRL reads as "the same weights with the adapter disabled".
`--loss-type` now passes TRL's unified preference losses (`apo_zero` etc.) for
later experiments. Pinned by `tests/test_pipeline.py` (derive rules,
blocklist, harness-text refusal), `tests/test_self_improve.py` (pairs
roundtrip, export merge) and `tests/test_claim_grounding.py`
(`test_a_verify_fix_becomes_a_preference_pair`). Suite after this pass:
**990 passed, 0 failed** in 137.2 s.

## A66 — the tool-schema floor alone starved the local context (2026-10-17, **CLOSED same day**)

A59 gave the local route an honest `num_ctx` (8192) and a logged compaction
path, but the *floor* went unmeasured: all 30 tool schemas weigh ~17.1k chars,
which `_token_estimate` prices at ≈6.0k of the 7168-token budget once a
representative system + task block is added. A live `web_search_tool` turn
showed the consequence — **8434 est tokens with NOTHING left to compact**: the
history was not the problem, the schema list was, and every local call paid it
before a single tool result existed.

**Closed:** per-route schemas. `bee/tools/__init__.py` grew
`LOCAL_TOOL_NAMES` (20 tools: files/shell/code_run/calculator, memory,
skills, planner, web_search/web_fetch, system_health, scheduler) and
`tools_litellm(local=True)`; `bee/agent/loop.py:tools_for` picks per call —
cloud keeps the complete set, local gets the subset, mid-run de-escalation
switches sets with the model. The executor registry (`tools_by_name`) and the
guard/risk path are untouched, so nothing became uncallable, and the dropped
capability tools (automate 2.2k, automation_job 1.3k, systemctl 842,
computer_* ≈3.0k combined, sandbox_run 579, spawn_task 511 chars) still reach
the model the moment the task is served by cloud — which the hybrid does first
for anything hard.

Measured with a representative system+task floor: full set 6,039 est vs subset
3,166 est → history headroom **1,129 → 4,002 est tokens** (freed ~2.9k est
≈ 9.8k chars of conversation). Pinned by `tests/test_fastpaths.py`
(`test_local_route_gets_the_fitted_schema_subset` — also asserts every listed
name exists, so a typo cannot silently shrink the set;
`test_cloud_route_keeps_the_full_schema_set`). Suite after this pass:
**992 passed, 0 failed** in 123.9 s.

## A67 — one provider's 429 disabled the whole cloud tier for the day (2026-10-17, **CLOSED same day**)

`cloud.llm` was the only provider the cloud tier could ever use. The Gemini
free tier allows ~20 requests/day; when it ran out, every later cloud call
got a 429, the loop de-escalated to local turn by turn, and the whole cloud
side of the product was gone until the quota window reset — the 2026-10-17 J3
gate run (candidate `bee4b-v2` vs seeded baseline) came back **VOID** for
exactly this reason ("retry ~9.5 h"), and the planned cloud head-to-head died
with it. The information was all there (rate-limit kind, provider registry,
key handling) — there was simply no second provider to go to, and no memory
of "this provider is exhausted" once one call had found out.

**Closed:** the quota is now a managed resource.
`bee/agent/client.py` keeps a per-provider-kind cooldown (`_COOLDOWN` /
`_cooling`; in-process by design — a fresh process re-probes once and the
probe is cheap). When a call to the managed primary fails with a
rate-limit / auth / overloaded / server error and `cloud.fallback_llm` is
configured + credentialed, `_cloud_failover` cools the primary kind for
`cloud.quota_cooldown` seconds (floor 30 s) and the caller re-issues the same
call; `_call_info` then resolves the fallback with **its own** `fallback_api_key`
/ `fallback_base_url` (no cross-provider credential leaks — pinned), and
later calls skip the cooling primary entirely. If the fallback fails too the
error surfaces honestly (`_cooling(primary)` is already set, so no
provider ping-pong). `chat_stream` gets the same treatment for pre-token
failures. Config: `CloudCfg.fallback_llm` / `fallback_api_key` /
`fallback_base_url` / `quota_cooldown` (dataclass + `_section` + the yaml
block, all three layers), shipped as `zai/glm-5.3-flash` — the z.ai (GLM)
provider was added to the registry (`ProviderKind.ZAI`, `ZAI_API_KEY` /
`ZHIPUAI_API_KEY`, legacy `zhipuai/` alias), `ProviderRegistry.from_config`
lists it, and `cloud_available` reports a fallback-only tier as UP
(`fallback-only: zai credentials present (primary gemini has none)`) so the
hybrid keeps escalating. Activation on this box is one env var: no ZAI key
exists yet, so the code path is dormant but live-tested hermetically (fake
litellm: primary 429 → same call on the fallback, next call straight to the
fallback, cooldown expiry re-probes the primary, missing credentials refuse
failover). Pinned by `tests/test_providers.py`
(`test_cloud_failover_switches_and_cools`,
`test_cloud_failover_requires_fallback_credentials`,
`test_expired_cooldown_probes_primary_again`,
`test_cloud_available_fallback_only`, `test_zai_provider_kind_and_keys`).
Suite after this pass: **997 passed, 0 failed** in 123.2 s.

## A68 — the self-improvement loop stopped at the adapter, and the gate flipped on flake (2026-10-17, **CLOSED same day**)

`auto_qlora` could train an adapter overnight, but nothing downstream was
automatic: the adapter sat in `models/bee-qlora-<tag>`, the
merge/convert/quantize/`ollama create` steps were manual shell work (the very
session that produced `bee4b-v2` — its recipe still lives in
`models/bee-merged-v2/convert_commands.txt`), and even a hand-built model had
to be re-typed into `config.yaml model_gate.candidate` before the J3 gate
would look at it. So the "self-improving" nightly loop was really: train
(opt-in, GPU-gated), then WAIT FOR A HUMAN. And the gate closing it compared
single-shot suite runs whose 21-task deltas sit inside ±2-3 stochastic noise:
the live 2026-10-17 run went VOID on quota, and the planned promotion call
was ±1 on the raw count — a single flaky task could flip a verdict either
way.

**Closed:** two mechanisms.
(1) `bee/scheduler.py:_auto_chain` runs after every successful nightly
training: `merge_export.py` (torch merge; `--skip-merge` on re-runs),
`convert_hf_to_gguf.py` → f16 GGUF, `llama-quantize` → Q4_K_M,
`ollama create bee-qlora-<tag>` — the physical steps gated on
`training.llama_cpp_dir` (an unpacked llama.cpp: convert script + quantize
binary; without it the chain stops with the exact remedy and queues
nothing). The imported model is queued atomically in
`train/gate_candidate.json`; `model_quality_gate` resolves the candidate as
explicit arg > queue > `config.yaml` and consumes the queue on a decisive
verdict only — promote/reject clear it, a 429-VOID keeps it for a retry.
`/gate show` displays the queue and the adjudication setting.
(2) `model_gate.adjudication_rounds` (default 2): tasks the two arms
DISAGREE on are re-run that many extra times PER SIDE and a majority decides
— a couple of minutes, not a second full suite; only disagreements are
touched; a failed re-run degrades to fewer votes, never a crash; 0 restores
single-shot. Pinned by `test_queued_candidate_is_picked_up_and_consumed_on_reject`,
`test_queued_candidate_promotes_and_is_consumed`,
`test_queued_candidate_survives_a_void`,
`test_explicit_candidate_never_consumes_the_queue`,
`test_adjudication_flips_a_flaky_verdict`,
`test_adjudication_rounds_zero_restores_single_shot` (tests/test_eval_gate.py)
and `test_auto_chain_stops_cleanly_without_llama_cpp`,
`test_auto_chain_imports_and_queues_the_model` (tests/test_sft.py). Verified
live on the real config: `training.llama_cpp_dir` resolves to the unpacked
b11711 dir, `adjudication_rounds: 2`, queue empty (nothing half-built).
Suite after this pass: **1005 passed, 0 failed** in 125.9 s.













