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
| H8 (HIGH) | **CLOSED** | `eval_safe` now bounds syntax (nodes 512 / depth 64 / literal 10k), the single-op explosion (`_guarded_pow` exponent cap 10⁴ on both `**` and built-in `pow` — `9**9**9**9` and `pow(2, 10**9)` rejected in ms), and expression-complexity computation (250k-step budget in `_ev` — defense-in-depth; a pathological BUILT-IN call such as `sum(range(10**18))` remains a single C loop the budget cannot interrupt — residual documented, bus timeout N3 unblocks the agent). Regressions `test_h8_*` (3) |
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


Still failing on the eval, all local-model answer quality rather than plumbing: `file_roundtrip`, `dsa_lis`, `dsa_gcd_lcm`, `dsa_graph`, `plan_complex`. Two of them (`dsa_lis`, `plan_complex`) now end in the honest fallback instead of shipping a non-answer, and `dsa_gcd_lcm`/`file_roundtrip` burn 15 tool calls inside one attempt without ever running the snippet they were given — that ceiling is the J1/QLoRA training work, not another regex.

