# BEE / Jarvis — Feature Status (authoritative)

**Date:** 2026-10-08 · **Basis:** independent acceptance audit
([JARVIS_ACCEPTANCE_AUDIT.md](JARVIS_ACCEPTANCE_AUDIT.md)) — source reads at
cited locations + test suites actually executed on this machine.

Legend:
- **GREEN** — verified working (source + tests +, where claimed, live run)
- **YELLOW** — implemented with known, documented limitations
- **RED** — incomplete / unverified / unsafe

Test basis: `pytest tests -q` = **534 passed, 0 failed** (core 463 ·
security 93 · windows 73 · ml 39 · voice/livekit 32 — suites overlap by
marker); `evals/verify_suite.py` = **71,914 checks, ALL PASS**.

## Agent core

| Feature | Status | Note / limitation |
|---|---|---|
| Single Agent Kernel (state machine, receipts, telemetry) | GREEN | all surfaces (REPL/web/livekit/voice/jobs/proactive) run through it |
| ToolBus as execution dispatcher | GREEN (this audit, fix F2) | loop now dispatches via `bus.call`; planner validates against the same bus |
| Capability gate (task-scoped grants, fail-closed unattended) | GREEN | post F0 (N1): `/guard off` no longer disables it; post F1: sub-agents + clap inherit it |
| Fast-path catalog (~40 handlers) | YELLOW | deterministic + legacy-guard-checked, but **skips the capability gate by design** (user's own words, regex-fixed action set, pre-LLM). Accepted design; documented here. |
| Verification-gated success (no false success) | GREEN | `verify_task` + per-tool effect checks; blind retry only on non-destructive steps |
| Cancellation (REPL Ctrl-C / "stop" / voice / job timeout) | GREEN | task-scoped per entry point (REPL/voice clear per run; jobs swap a job-scoped event). Kernel itself does not own the clear — P2. Web & LiveKit have **no** mid-task cancel (fail-closed approver limits blast radius). |
| Crash recovery (J1 checkpoints + `/resume`) | GREEN | task-level resume with "do not redo executed steps" note |
| Provider abstraction (local Ollama + cloud kinds) | GREEN | one registry, one execution path; keys env-only, matched per provider |
| Cloud-unavailable operation | GREEN (tested) / YELLOW (live) | fallback + deterministic floor verified with fake clients; live offline drill not performed in this audit |
| ML router | GREEN | optional; major-version incompatible artifact **refused** with a clear message; falls back to heuristics; per-class training report; pinned env |
| Offline deterministic tier (math/smalltalk/files) | GREEN | eval_safe AST calculator, fast paths, offline floor |

## Memory & conversation

| Feature | Status | Note / limitation |
|---|---|---|
| Structured memory with provenance (source floors/caps, promotion guard) | GREEN | model_inference/web items can never silently become user facts |
| Corrupted-store resilience | GREEN (this audit) | garbage file → empty store; one bad row → good rows salvaged (8 new tests) |
| Session persistence + follow-up resolution | GREEN | "continue/new/cancel" + time nudges; "Remind me… → Tomorrow." = ONE rescheduled durable job |
| Planner (typed intent → validated plan before execution) | GREEN | impossible/ambiguous requests short-circuit without LLM; replans counted |
| Markdown memory (diary/lessons/profile/longterm) + RAG | GREEN | hybrid vector+keyword; vector rebuild is clear-before-add |

## Scheduling & proactivity

| Feature | Status | Note / limitation |
|---|---|---|
| Durable scheduler (one Job model, UTC-canonical next_run, job timezone) | GREEN | restart restore with crash repair, no blind replay, file-claim single-flight; trigger math pure & tz-deterministic |
| Scheduled tasks through the kernel | GREEN | agent jobs + proactive tasks run `kernel.run` with fail-closed approver (only preapproved capabilities) |
| Proactive policy (default-deny, rate limits, quiet hours) | GREEN | no rule → no action; per-rule + global caps; quiet hours suppress non-critical pings |
| External side effects (auto email/whatsapp/sms) | GREEN (gate) / **must stay off by default** | require `external_authorized=True` per rule; default-deny enforced in `ProactivePolicy.check` |
| Event sources | YELLOW | timer + file_change implemented end-to-end; calendar = ICS only; email/app_event/battery/network/device_state are schema-only ("unavailable") |
| Wall-clock firing | YELLOW | logic is clock-injected & fully tested; real-time firing not CI-exercised |

## Voice

| Feature | Status | Note / limitation |
|---|---|---|
| Realtime VoiceEngine (6 states, VAD, partials, endpointing) | GREEN (synthetic) | wired into REPL voice (cli.py); engine + 32 tests green |
| Barge-in / "Stop." / interruption / task cancellation | GREEN (synthetic) | TTS torn down immediately, kernel task cancelled, state → LISTENING |
| Reconnect / mic & provider failure recovery | GREEN (synthetic) | capped exponential backoff + audio validation; ERROR auto-recover |
| Streaming TTS (edge-tts chunks) / STT (windowed partials, honest: faster-whisper is batch) | GREEN | no fake streaming in the response path (genuine provider streaming; STT partials documented as window re-transcription) |
| LiveKit transport | ENVIRONMENT-DEPENDENT | behind `VoiceTransport` (kernel never imports LiveKit); config+agent tests green; **room not verified in field**; room audio transits LiveKit Cloud (not "audio stays on machine") |
| Real mic / speakers / clap hardware | ENVIRONMENT-DEPENDENT | hardware path not exercised in this audit |

## Computer use

| Feature | Status | Note / limitation |
|---|---|---|
| Observe → act → re-observe → verify closed loop | GREEN (mocked UI) | per-action pre/post snapshots + `verify_action`; budget-bounded; action ids |
| Coordinate provenance (no stale pixels) | GREEN | coords must lie in a rect from the LAST observe; semantic targets resolved by the vision backend against a fresh snapshot; `model_raw` explicitly flagged for the risk layer |
| Safe action set (12 verbs) | GREEN | no financial/destructive/credential/download/executable verbs exist in `VERBS`; credential targets blocked by name |
| Emergency stop (independent of the LLM) | GREEN (mocked) | 3 mechanisms: kernel cancel event, global registry stop, Ctrl+Alt+Q hotkey poller |
| Permissions for risky actions | GREEN | risk classification → kernel approver + capability gate (e2e test through the real kernel) |
| Privacy/retention (no typed text/clipboard/pixels/titles in logs; bounded screenshot ring) | GREEN | enforced in `privacy.py`, test-pinned |
| Vision layer (vendor-neutral `VisionBackend`) | YELLOW | `StructuralVision` (window rects) is the default; learned-vision backends are swappable but **not implemented** |
| Real display | ENVIRONMENT-DEPENDENT | `WindowsDesktop` mocked in tests/CI; supervised real-display session required before enabling unattended |

## Security

| Feature | Status | Note / limitation |
|---|---|---|
| SSRF protection (netguard), incl. redirect re-validation | GREEN | every hop re-validated; all DNS answers checked; scheme/host/IP/content-type/size policy; hermetic tests |
| Untrusted external content | GREEN | sentinel-wrapped model view; R2+ capabilities escalated to explicit ask after ingestion; pre-ingestion grants revoked |
| Prompt/tool injection | YELLOW | gate escalation + untrusted wrapping + ToolBus registration (unregistered tools uncallable) — no injection corpus test exists; treat as designed-but-unexercised |
| Sandbox (Docker) for model-generated code | YELLOW | hardened flags verified in source; requires running Docker + built `bee-sandbox` image; boundary = Docker/WSL2 |
| Secrets hygiene | GREEN | env-only; secret scan over tracked files green; no `.env`/runtime data in the repo |
| Log redaction + rotation | GREEN | redaction at write chokepoints; JSONL streams size-capped with rotation |
| Sub-agent authorization | GREEN (this audit, fix F1) | spawn_task sub-context now inherits gate/task-id/cancel-event/guard-mode (regression test) |

## Reliability (tested scenarios)

Cloud unavailable · local model unavailable · tool failure · timeout ·
cancellation · verification failure · bounded retry · app/scheduler restart ·
network failure (voice reconnect) · malformed request · **corrupted memory**
· missing optional dependency — all covered by green tests (this audit's
matrix). Real-network/real-hardware versions: not exercised.

## RED (do not enable)

| Item | Why |
|---|---|
| Unattended real-display computer use | real `WindowsDesktop` path never verified on a live display; budget + gate exist but the ground truth is mocked |
| Auto external messaging (email/whatsapp/sms) from proactive rules | capability gate works, but no live channel integration is verified; keep `external_authorized` off until a channel is field-tested |
| "Production-ready" / multi-user claims | single-user localhost design; web bind is 127.0.0.1; no authn between users; eval ceiling 8–13/21 (local 3B model) |

## YELLOW register (honest limitations)

Fastpath gate-skip (design) · event sources schema-only (email/app/battery/
network/device) · learned vision not implemented (structural only) ·
wall-clock scheduler not CI-exercised · web/livekit no mid-task cancel ·
kernel not owner of cancel-event clearing (4 entry points do it) · LiveKit
room + real mic/display unverified in field · prompt-injection corpus absent ·
behavioral eval capped by the local model (J3 model-gate is the closure path).

---
*Every row above is traceable to the evidence column of the acceptance audit
or to a green test in the 534-test suite. Nothing here is marketing.*
