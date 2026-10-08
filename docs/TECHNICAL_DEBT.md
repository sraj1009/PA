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
**Fix:** live endpoint in Phase 6.2.

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
| M8 (stale contracts) | PARTIAL | `/voice` docstring now matches JSON-only behavior; dashboard live data still open |
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
