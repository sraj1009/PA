# Graph Report - PA  (2026-10-18)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 5061 nodes · 10880 edges · 249 communities (221 shown, 28 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 349 edges (avg confidence: 0.88)
- Token cost: 18,155 input · 2,568 output

## Graph Freshness
- Built from commit: `98e3a0c1`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Component Test Harness
- Ollama Server Management
- Command System Tests
- Group Chat Tests
- Voice Engine Mocks
- Job Queue Management
- Shop Data Filtering
- Self-Critique Gate
- Desktop Risk Audit
- LLM Request Envelopes
- Hybrid Routing Logic
- Memory Recall Tests
- Tool Dispatch Bus
- Model Benchmarking Tools
- Job Store Persistence
- Web Application Endpoints
- Kernel Integration Tests
- Kernel Event Bus
- System Configuration
- Engine Selection Context
- Web Authentication Tests
- Fast Execution Paths
- Realtime Voice Orchestrator
- User Check-in Logic
- Telemetry Data Integrity
- Job Scheduling Adapter
- Training Pipeline Scheduler
- Computer Use Privacy
- Local State Management
- Model Upgrade Gate
- Voice State Machine
- Self-Reflection Loop
- Desktop Abstraction Layer
- Skill Gate Index
- ML Route Classifier
- Deterministic Verification Suite
- SSRF Network Guard
- Chat Topic Management
- Prompt History Budgeting
- Data Structures Library
- ML Route Classifier
- Proactive Event Sources
- Workspace Startup Protocol
- SFT Data Augmentation
- Hardware Event Sources
- Python Automation Recipes
- Streaming TTS Regressions
- Shell Execution Tools
- App Manifest Configuration
- Schema Migration Store
- Schedule Trigger Math
- Icon Rendering Assets
- Tool Call Auditing
- Proactive Action Policy
- Structured Memory Management
- Mood Radar Components
- Automation Test Utilities
- LLM Client Capabilities
- Permission Risk Layer
- Hardware Control Tools
- Tool Effect Verification
- Voice Agent Adapters
- Local STT Device
- Tool Execution Regressions
- Capability Guard Rails
- Markdown Memory Primitives
- Model Training Pipeline
- Vector Memory Search
- Desktop Interaction API
- Session Memory Protocols
- System Configuration Layers
- Task Scoped Policies
- Docker Sandbox Security
- Treehole Post Management
- Post-Answer Verification
- Itinerary Planning Tool
- Context Assembly Logic
- UI Observation Events
- Graph Algorithms Library
- Prompt Injection Guard
- Static Contract Analysis
- Hardware Recall Tests
- Capability Authorization Tests
- Automation Management Tool
- RAG Recall Evaluation
- Agent Kernel Implementation
- Evaluation Logic Regressions
- Capability Authorization Layer
- Evaluation Suite Runner
- Local Model Server
- Voice State Bridge
- Secret Detection Scanner
- LiveKit Audio Transport
- Cancellable Subprocess Execution
- Model Quality Gate
- Windows Desktop Automation
- Evaluation Hermeticity Tests
- Binary Search Tree
- Preference Pair Derivation
- Typed Execution Planner
- Human Feedback Store
- Chat Classification Logic
- Task Plan Store
- Heap and Quickselect
- Agent Session State
- SFT Eligibility Filter
- Mood Radar Visualization
- Deterministic Claim Verifier
- Structural Vision Backend
- Router Training Metadata
- Streaming TTS Engine
- System Health Metrics
- Agent Core Logic
- Native System Telemetry
- Tiered Routing Logic
- Agent Core Loop
- UI Design Assets
- Code Generation Tool
- Deterministic Offline Fallback
- Binary Heap Implementation
- Action Claim Correction
- Structured Retry Policy
- Streaming Client Contract
- Evaluation Scoring Metrics
- Node Test Configuration
- Job Execution History
- Agent Kernel Runtime
- Agent Execution Results
- Streaming STT Implementation
- LLM Prompt Templates
- Logging and Notifications
- Acoustic Trigger Detection
- SSRF Web Security
- Microphone Audio Capture
- Tool Call Extractor
- Vector Store Management
- Text-to-Speech Synthesis
- ML Router Reporting
- Dynamic Programming Recipes
- Structured Memory Store
- Screenshot Retention Policy
- Trie Prefix Tree
- Safe Math Evaluation
- Hybrid Task Routing
- App Manifest Testing
- HTTP Client Testing
- Web Approval Interface
- Modular Slash Commands
- System Audit Status
- Document Summarization Tool
- Cross-Process Safe IO
- Voice Transport Protocol
- LLM Utility Functions
- ML Training Skills
- Windows API Shims
- Idea Analysis Tool
- DSA Benchmark Harness
- Filesystem Security Tools
- Time Formatting Utilities
- Test Isolation Markers
- Isolated Eval Environment
- Union Find Reference
- Planner Logic Regressions
- Semantic Memory Retrieval
- Lexicon Word Lists
- Core Group Management
- Dependency Stack Management
- Voice Command Loop
- App Transition Monitoring
- Web and Voice Endpoints
- Technical Debt Audit
- Execution Receipt Logging
- QLoRA Fine-tuning Script
- Security Model Overview
- Ollama Text Embeddings
- Service Health Checks
- Safety and Guardrail Policies
- Grok Web UI Components
- Process Lifecycle Management
- Architecture Documentation Authority
- State Reset and Fixtures
- Memory and System Principles
- Data Science Skills
- Jest Test Configuration
- Setup and State Management
- Routing Threshold Configuration
- merge_export.py
- agent/__init__.py
- episodes/__init__.py
- evals/__init__.py
- Linux Core CI Job
- Bee4b Primary Orchestrator Model
- Computer Use Desktop Stack
- LiveKit Agent Stack
- requirements-vision.txt Vision Extras
- requirements-voice.txt Voice Stack
- Break down tasks SKILL
- browser SKILL
- DSA sorting graphs DP benchmark harness
- eval_status.py
- Planner Integration Tests
- Constraint Planner Solver
- Windows Core CI Job
- Voice Optional Workflow
- Windows Desktop Optional Workflow
- Insight: unauthenticated Grok session is gated requiring signup to continue
- bee-telemetry
- Agent Query Execution
- Engine Routing Tests
- Response Data Handling
- Planner Logic Utilities
- Hybrid RAG Memory
- Module Layering Contract
- DPO Model Training
- Schema Fitting Optimization
- Module API Discovery
- Global Emergency Hotkey
- Docker GPU Sandbox
- Event Bus Implementation
- Content Drafting Tool
- Local Speech Transcription
- Isolated Test Environment
- Sub-Agent Spawning
- Device Event Bus
- MCP Server Config
- Scripted LLM Mock
- Fake Stream Mock
- Deterministic Memory Requests
- Preference Data Export
- Grounded Fallback Logic
- Startup Protocol Tests
- Scripted Client Verification
- rollback_model
- FrozenDate
- test_rate_limited_baseline_seed_is_refused

## God Nodes (most connected - your core abstractions)
1. `load_config()` - 158 edges
2. `run_agent()` - 92 edges
3. `AgentKernel` - 71 edges
4. `make_kernel()` - 71 edges
5. `Context` - 64 edges
6. `Job` - 62 edges
7. `LLMClient` - 61 edges
8. `JobWorker` - 56 edges
9. `JobStore` - 54 edges
10. `MockDesktop` - 51 edges

## Surprising Connections (you probably didn't know these)
- `OfflineAgent Lexicon Matcher Backend` --semantically_similar_to--> `FastPaths Deterministic Tier`  [INFERRED] [semantically similar]
  campus-life/docs/2026-10-12-design.md → docs/JARVIS_ARCHITECTURE.md
- `StubClient` --uses--> `LLMError`  [INFERRED]
  tests/test_engine_speed.py → bee/agent/client.py
- `test_followup_context_merges_time_hints()` --calls--> `AgentSession`  [EXTRACTED]
  tests/test_phase8_memory_planning.py → bee/kernel/session.py
- `test_pronoun_reference_resolves_against_active_task()` --calls--> `AgentSession`  [EXTRACTED]
  tests/test_phase8_memory_planning.py → bee/kernel/session.py
- `test_07_corrupt_executions_skips_bad_lines()` --calls--> `JobStore`  [EXTRACTED]
  tests/test_phase12_reliability.py → bee/automation/store.py

## Import Cycles
- 4-file cycle: `bee/agent/loop.py -> bee/tools/__init__.py -> bee/tools/spawn_tool.py -> bee/agent/spawn.py -> bee/agent/loop.py`

## Hyperedges (group relationships)
- **One agent interface with auto-selected backends** — campus_life_agent_interface, campus_life_llm_agent, campus_life_offline_agent [EXTRACTED 0.75]
- **Eval quality gate system: verify suite, 21 tasks, J3 model gate** — evals_report_verify_suite_71914, evals_tasks_21_task_gate, docs_production_readiness_model_gate_j3 [EXTRACTED 0.75]
- **Security hardening batch: kernel routing, bearer auth, netguard** — docs_production_readiness_single_kernel_routing, docs_security_bearer_token_auth, docs_security_netguard_ssrf [EXTRACTED 0.75]
- **Shared bearer-token auth across web surfaces** — bee_web_chat_ui, bee_web_face_visualizer, bee_web_live_voice_page, bee_web_auth_token [EXTRACTED 0.75]

## Communities (249 total, 28 thin omitted)

### Community 0 - "Component Test Harness"
Cohesion: 0.05
Nodes (89): resetStore(), storage, { loadComponent, tap, text, count, simulate, wxState, resetWxState }, { loadComponent, text, classes, count, simulate }, { loadComponent, tap, text, allText, count, simulate, wxState, resetWxState }, { loadFixture, tap, text, count }, freeze(), unfreeze() (+81 more)

### Community 1 - "Ollama Server Management"
Cohesion: 0.20
Nodes (23): Bring Ollama up if it is not already. Returns True when the server is reachable…, start_background(), _cfg(), _launched(), Popen, Wait for the boot thread to record its outcome (it always sets `_attempted` in…, Without OLLAMA_HOST the server BEE starts would sit on 11434 while BEE polls…, A flashing console or a pipe that fills up would make the assistant's boot… (+15 more)

### Community 2 - "Command System Tests"
Cohesion: 0.09
Nodes (25): line = full command line (leading '/' ok, e.g. '/draft email ...'). Returns…, run(), ctx(), DeadClient, fixture, BEE command system + Phase-4 hot-path regression tests. Covers: - config.yaml…, Regression: UnboundLocalError (res_v) when the guard ALLOWED an exec tool., Scripted LLMClient stand-in — no network, no model. (+17 more)

### Community 3 - "Group Chat Tests"
Cohesion: 0.09
Nodes (19): groups, INTERESTS, chat, groups, advance(), agent, chat, { freeze, unfreeze, advance } (+11 more)

### Community 4 - "Voice Engine Mocks"
Cohesion: 0.07
Nodes (47): FakeTTS, Test double with the StreamingTTS lifecycle. Mirrors the real pipeline: begin()…, FakeKernel, FakeSTT, make_engine(), Voice engine tests (Phase 4) — true realtime conversation behavior. Required…, Kernel stand-in: run() 'works' for delay seconds (polling the cancel event like…, User barges in while BEE is thinking/speaking: TTS stops immediately, the task… (+39 more)

### Community 5 - "Job Queue Management"
Cohesion: 0.07
Nodes (14): Job, JobQueue, Claim a job for execution. Refused if already inflight or the global cap is…, JobWorker, datetime, PII/secret redaction for anything persisted as job telemetry., Block until no job thread is running (or timeout). Test/teardown helper —…, Restart recovery: load jobs, repair crash state, recompute next_run, handle… (+6 more)

### Community 6 - "Shop Data Filtering"
Cohesion: 0.05
Nodes (50): COMPARATORS, filter(), haversineKm(), isOpen(), toRad(), cats, ORIGIN, shops (+42 more)

### Community 7 - "Self-Critique Gate"
Cohesion: 0.16
Nodes (19): critique_answer(), Pre-finalize self-critique (Chain-of-Thought Verification) for local answers.…, Gate: operator flag, real (non-test) client, substantive draft., One local pass. Returns the corrected answer, or the draft unchanged on…, should_critique(), Mechanical pre-check for one tool call. Returns "" when callable, else a repair…, _validate_call(), _Chat (+11 more)

### Community 8 - "Desktop Risk Audit"
Cohesion: 0.07
Nodes (36): ComputerAction, Risk after provenance: unproven click coordinates escalate to high (the risk…, Log/audit-safe view — NEVER includes the typed text payload, clipboard…, MockDesktop, Simulate the USER (or another app) changing the screen mid-task., Deterministic desktop for tests. Windows: add_window(); launchers:…, test_session_observation_reports_the_true_cause(), make_ctx() (+28 more)

### Community 9 - "LLM Request Envelopes"
Cohesion: 0.07
Nodes (48): LLMRequest, LLMResponse, Typed request envelope (preferred API). `request()` wraps `chat()`; all legacy…, Typed response envelope mirroring the `chat()` dict contract., _cloud_up(), Cloud tier is usable only if enabled, configured AND credentialed. Availability…, cloud_available(), env_key_for() (+40 more)

### Community 10 - "Hybrid Routing Logic"
Cohesion: 0.11
Nodes (28): _is_gemini3plus(), True for Gemini 3+ (gemini-3-flash-preview, gemini-3.6-flash, flash-…, _capture_litellm(), _ctx(), _FakeOllamaResp, _mk_cfg(), Engine speed tier: hybrid cloud-first routing, cloud→local de-escalation, and…, Fake the ONLY external dependency of the primary path, and hand back the kwargs… (+20 more)

### Community 11 - "Memory Recall Tests"
Cohesion: 0.09
Nodes (31): _best_lines(), The bullets inside a memory chunk that actually answer this query. A chunk is…, is_hardware_query(), _kernel(), _mem(), Structured memory tests (Phase 3, Parts C/D): remember/recall/update/forget,…, The store starts empty — only explicit remember() creates items., The rag_gpu_memory eval task failed because the kernel STORED the question:… (+23 more)

### Community 12 - "Tool Dispatch Bus"
Cohesion: 0.10
Nodes (24): MalformedArgsError, ToolBus (Phase 2) — the single dispatch point for agent tool calls. Every tool…, litellm/openai function schemas for the registered tools only., Execute a registered tool. Returns (result, seconds, ok, meta). meta:…, Build from the existing registered tool modules (bee.tools)., ToolBus, ToolDef, ToolTimeoutError (+16 more)

### Community 13 - "Model Benchmarking Tools"
Cohesion: 0.07
Nodes (42): automation_tools(), load_config(), Path, _bench_embed(), _bench_gen(), main(), Local model throughput/latency benchmark → evals/bench_model.json. Run: python…, compare() (+34 more)

### Community 14 - "Job Store Persistence"
Cohesion: 0.10
Nodes (11): _new_id(), Notification, _atomic_write(), JobStore, Path, Execution files OLDEST FIRST (.2 -> .1 -> active) — M13 rotation never loses…, Last row per execution id wins (a crash-repair appends a terminal row for an…, Drop claim tokens older than ttl (crashed processes). Idempotent. (+3 more)

### Community 15 - "Web Application Endpoints"
Cohesion: 0.09
Nodes (44): cancel_task(), chat(), dashboard(), engine_get(), engine_set(), face_page(), face_state(), get_ctx() (+36 more)

### Community 16 - "Kernel Integration Tests"
Cohesion: 0.07
Nodes (54): Acceptance audit P1-1: with a kernel attached, the agent loop must dispatch…, test_f2_loop_executes_tools_through_toolbus(), N4: the KERNEL owns task-scoped cancellation. A cancel event left SET by a…, Loop breaker gap: the exact-args breakers never match when a small model re-…, Retrying one failing call with reworded arguments used to burn the whole budget…, test_n4_stale_cancel_event_does_not_poison_new_task(), test_repeated_denials_lock_tools_instead_of_burning_the_budget(), test_repeated_tool_failures_lock_without_punishing_good_work() (+46 more)

### Community 17 - "Kernel Event Bus"
Cohesion: 0.10
Nodes (17): EventBus, callable, Typed kernel event bus (Phase 2) — a thin facade over the project's ONE shared…, _emit(), AgentKernel (Phase 2) — the single agent runtime. Flow (kernel-owned; the LLM…, Friendly name for where a memory hit came from. The hybrid index stores…, _src_label(), AgentEvent (+9 more)

### Community 18 - "System Configuration"
Cohesion: 0.04
Nodes (47): AlertsCfg, _apply_env(), AutomationCfg, _build_from_yaml(), ClapCfg, CloudCfg, ComputerUseCfg, _dotenv_defines() (+39 more)

### Community 19 - "Engine Selection Context"
Cohesion: 0.06
Nodes (51): create_context(), Single application-context factory (Phase 1: replaces the 7+ duplicated…, ask_engine(), engine_labels(), load_engine(), override_for(), Engine selection: which brain does BEE use by default? Asked once at first…, Human-facing engine labels. The api-cloud label reflects the ACTUAL configured… (+43 more)

### Community 20 - "Web Authentication Tests"
Cohesion: 0.07
Nodes (37): reset_token_for_tests(), test_web_livekit_and_face_endpoints(), _client(), _client_with_kernel(), dash_env(), _page(), fixture, parametrize (+29 more)

### Community 21 - "Fast Execution Paths"
Cohesion: 0.07
Nodes (34): _brightness(), _cim(), _convert(), _date(), FastExec, FastPath, _files_list(), _files_list_reply() (+26 more)

### Community 22 - "Realtime Voice Orchestrator"
Cohesion: 0.09
Nodes (24): VoiceEngine (Phase 4) — the realtime conversation orchestrator. Pipeline (one…, bee.voice.realtime — Phase 4 true-realtime voice. Clean layering:…, InvalidVoiceTransition, Enum, Exception, str, Voice state machine (Phase 4). The VOICE layer owns this state machine — and…, Engine tunables (defaults mirror config.yaml voice: rt_* fields). (+16 more)

### Community 23 - "User Check-in Logic"
Cohesion: 0.06
Nodes (38): locate(), canCheck(), coverage(), dayIndex(), doCheckin(), groupByZone(), latestFor(), list() (+30 more)

### Community 24 - "Telemetry Data Integrity"
Cohesion: 0.29
Nodes (10): _real_kernel(), metrics_file(), fixture, Structured telemetry + data-integrity hardening tests (audit 2026-10-06).…, Point the metrics stream at a temp file for the duration of a test., _rows(), _slow_client(), test_llm_latency_and_provider_failure() (+2 more)

### Community 25 - "Job Scheduling Adapter"
Cohesion: 0.12
Nodes (35): effective_max_attempts(), Retry budget for a job (scheduling unification, 2026-10-08). Destructive/side-…, MemoryStack, Facade: memory.<kind> gives the kernel one object per store. Phase 3:…, _cron_to_trigger(), scheduler tool — ADAPTER over the durable automation system (2026-10-08).…, Return (JobTrigger, note) or raise ValueError with the reason., scheduler_tools() (+27 more)

### Community 26 - "Training Pipeline Scheduler"
Cohesion: 0.09
Nodes (30): _fn_build_sft(), _fn_consolidate(), _fn_rebuild_vectors(), _fn_teach_back(), _fn_train_qlora(), diary_add(), _auto_chain(), consolidate() (+22 more)

### Community 27 - "Computer Use Privacy"
Cohesion: 0.08
Nodes (31): is_credential_target(), Computer-use action model (Phase 5) — one safe desktop action. Every action the…, Heuristic gate for the 'no credential entry' rule (checked on the SEMANTIC…, bee.computeruse — Phase 5: SAFE computer use. Desktop capture -> structured UI…, Computer-use privacy (Phase 5). Rules enforced in code (not just documented):…, Log/audit-safe entry for one executed (or blocked) action., redact_entry(), computeruse_emergency_stop() (+23 more)

### Community 28 - "Local State Management"
Cohesion: 0.06
Nodes (49): { createStore }, { KEY }, request(), save(), store(), tzOffsetMin(), instance(), label() (+41 more)

### Community 29 - "Model Upgrade Gate"
Cohesion: 0.13
Nodes (21): queue_candidate(), Queue `model` for the next gate run (atomic write)., _fake_suite(), J3 — model-upgrade quality gate (contract tests, no live model).…, A62: `run_score` drops skipped rows, so the two sides can have different…, The auto-chain queue (train/gate_candidate.json) feeds the gate exactly once: a…, A 429-dead arm is not an attempt: the queued artifact must stay so the nightly…, `/gate other-model` evaluates the operator's choice; the queued artifact is a… (+13 more)

### Community 30 - "Voice State Machine"
Cohesion: 0.13
Nodes (6): Process one ~100 ms frame. NEVER raises — failures route to ERROR., Resolve a held answer once the verifier has judged it., Owns the voice state machine and timing; delegates all task logic to the kernel…, ERROR -> IDLE (or LISTENING when always-on) once the transport is up., Blocking transport pump with reconnect + capped backoff. stop() (or Ctrl-C)…, VoiceEngine

### Community 31 - "Self-Reflection Loop"
Cohesion: 0.09
Nodes (33): _all_bullets_empty(), Self-improvement loop (Phase 3): post-task reflection. After each completed…, `worked: None / failed: None / next: None` teaches nothing and burns the prompt…, A lesson is not a note to self — `context.recent_lessons()` injects it into…, Trivial tasks (canned replies, one-shot local answers, no tools) yield no…, LLM-based self-review. Returns the lesson text ("" if skipped)., reflect(), time_stamp() (+25 more)

### Community 32 - "Desktop Abstraction Layer"
Cohesion: 0.09
Nodes (37): DesktopError, make_desktop(), RuntimeError, Desktop abstraction (Phase 5). ComputerUseSession talks ONLY to this protocol.…, Default desktop factory — WindowsDesktop on Windows, DesktopError elsewhere…, active_sessions(), computer_clipboard(), computer_input() (+29 more)

### Community 33 - "Skill Gate Index"
Cohesion: 0.07
Nodes (58): Index of SHIPPED skills only. J2: skills in `candidate` status (created/updated…, skills_index(), _fn_skill_gate(), J2: gate candidate skills (structural check + bounded eval probe)., bump_skill(), candidate_names(), eval_probe(), gate_candidates() (+50 more)

### Community 34 - "ML Route Classifier"
Cohesion: 0.14
Nodes (25): full_report(), The last training report (per-class metrics etc.), if any., Artifact + training + runtime in one dict (for /health-style output)., training_report(), _compat_issue(), load(), load_status(), predict() (+17 more)

### Community 35 - "Deterministic Verification Suite"
Cohesion: 0.12
Nodes (28): luhn_ok(), _gen_expr(), _is_subseq(), _load_bench(), _luhn_check_digit(), main(), Path, Random (+20 more)

### Community 36 - "SSRF Network Guard"
Cohesion: 0.10
Nodes (33): FetchResult, _ip_class(), NetGuardError, Exception, SSRF-hardened HTTP fetching for model-driven web tools. The `web_fetch` tool…, Fetch a URL under the full SSRF policy. Raises NetGuardError on any violation.…, Raised when a URL or its fetch violates the SSRF policy., Return a blocking class name for a non-public IP, else None. (+25 more)

### Community 37 - "Chat Topic Management"
Cohesion: 0.10
Nodes (31): byId(), current(), expire(), open(), peer(), push(), reap(), send() (+23 more)

### Community 38 - "Prompt History Budgeting"
Cohesion: 0.15
Nodes (20): compact_messages(), Cheap prompt-size estimator used for history budgeting. A59 showed `chars/4`…, Drop oldest tool-history pairs before the model drops them for us. Ollama…, _token_estimate(), _ctx(), _DownClient, _fat_tools(), _pairs() (+12 more)

### Community 39 - "Data Structures Library"
Cohesion: 0.06
Nodes (30): BEE DSA library — curated, tested building blocks + benchmark harness. Usage:…, Segment tree with range query + point update. O(log n) each. Default op = sum.…, Inclusive range [lo, hi]., SegmentTree, bubble_sort(), counting_sort(), heap_sort(), insertion_sort() (+22 more)

### Community 40 - "ML Route Classifier"
Cohesion: 0.21
Nodes (13): make_mlp(), The DL route model: a **feature-scaled** neural net. Scaling is the crux — TF-…, _features_matrix(), _make_data(), fixture, ML route classifier: feature extraction + ML/DL model round-trip through…, The DL option (feature-scaled MLP) must save + predict exactly like the ML one,…, The DL model must be a Pipeline whose first step is a scaler (the accuracy fix). (+5 more)

### Community 41 - "Proactive Event Sources"
Cohesion: 0.13
Nodes (7): EventSource, FileChangeSource, Path, Internal EventBus + proactive policy (Phase 6). An EventBus carries internal…, Adapter interface: a source PUBLISHES events; it never acts., Polling file-change watcher (no external dependency): fires file_change events…, TimerSource

### Community 42 - "Workspace Startup Protocol"
Cohesion: 0.13
Nodes (27): _chrome_executable(), _due(), focus_or_launch_ide(), _foreground_hwnd(), _ide_executable(), _main_hwnd_win32(), _monitor_rects(), open_url_chrome() (+19 more)

### Community 43 - "SFT Data Augmentation"
Cohesion: 0.07
Nodes (34): build(), load_golden(), main(), _no_tool_single_turn(), paraphrase_augment(), Path, quality_score(), Successful cloud answers (teach-back). {'task','response','model','ts'}. (+26 more)

### Community 44 - "Hardware Event Sources"
Cohesion: 0.14
Nodes (17): available_sources(), BatterySource, NetworkSource, Honest capability report (sources are adapters; missing deps = 'unavailable')., Edge-triggered power events: battery.low / battery.unplugged / battery.charged…, Edge-triggered connectivity events: network.down / network.restored. Probes by…, Start the event sources that actually work on this machine. This is the…, start_sources() (+9 more)

### Community 45 - "Python Automation Recipes"
Cohesion: 0.12
Nodes (30): automate_tools(), _convert(), _count(), _dedupe(), _fill(), _find(), _inventory(), _jsonq() (+22 more)

### Community 46 - "Streaming TTS Regressions"
Cohesion: 0.12
Nodes (22): _speak(), skipif, Streaming-TTS and local-playback regressions (audit 2026-10-08). Two real…, No shell-out player may come back: it only decoded WAV, so MP3 output…, Backend order must degrade, never claim a silent success., (data chunk size field, actual payload bytes)., A streamed (0xFFFFFFFF) header decodes fine in Python but winsound cannot size…, Piping ffmpeg WAV output to stdout produces unknown-size headers; the fallback… (+14 more)

### Community 47 - "Shell Execution Tools"
Cohesion: 0.16
Nodes (19): _child_env(), The snippet's interpreter: UTF-8 stdio, and BEE's own package importable.…, _powershell_retry(), cmd.exe refused the FIRST word, so nothing ran — PowerShell may know it.…, _code(), _ctx(), skipif, A49 — the exec tools run what the model was told they run. a) code_run: a piped… (+11 more)

### Community 48 - "App Manifest Configuration"
Cohesion: 0.06
Nodes (31): lazyCodeLoading, pages, permission, scope.userLocation, requiredPrivateInfos, desc, sitemapLocation, style (+23 more)

### Community 49 - "Schema Migration Store"
Cohesion: 0.11
Nodes (24): migrate(), schema(), clone(), createStore(), load(), persist(), read(), reset() (+16 more)

### Community 50 - "Schedule Trigger Math"
Cohesion: 0.13
Nodes (22): JobTrigger, next_run(), _parse_hhmm(), parse_ics(), _parse_ics_dt(), _parse_local(), datetime, Trigger math (Phase 6) — pure, tz-aware, deterministic. next_run(trigger, tz,… (+14 more)

### Community 51 - "Icon Rendering Assets"
Cohesion: 0.09
Nodes (24): app, fs, path, { render, ICONS, OFF, ON, SIZE }, ROOT, zlib, chunk(), coverage() (+16 more)

### Community 52 - "Tool Call Auditing"
Cohesion: 0.08
Nodes (43): Attribute, _audit_record(), Persistent audit row for one tool call (redacted; never raises)., audit_path(), Path, Record one tool-call audit row. `decision` is a risk.RiskDecision (or None for…, Last n audit rows (for /audit-style inspection + tests)., recent() (+35 more)

### Community 53 - "Proactive Action Policy"
Cohesion: 0.15
Nodes (21): ProactivePolicy, ProactiveRule, Default-deny gate between the event bus and any action (Phase 11). check(event)…, quiet_hours=(start,end) local hours, wrap-aware ((22, 7) = 22:00 to 07:00).…, _ev(), Phase 11 — PROACTIVE JARVIS + EVENT INTELLIGENCE (2026-10-08). The proactive…, When this file appears, tell me' — FileChangeSource -> bus -> policy -> notify,…, The event is information; only an explicitly authorized proactive rule may turn… (+13 more)

### Community 54 - "Structured Memory Management"
Cohesion: 0.09
Nodes (21): MemoryItem, _now(), Path, Delete by id, or (for 'Forget that.') the LAST matched item when a query is…, Compact, source-labeled digest for context injection., Purge expired + long-tombstoned items; returns count removed., Timezone-safe expiry check (fixed 2026-10-08): expiries are stored UTC-…, StructuredMemory (+13 more)

### Community 55 - "Mood Radar Components"
Cohesion: 0.09
Nodes (17): empty(), badge(), { loadComponent, allText, count, simulate }, moodscore, NOW, card(), compile(), container() (+9 more)

### Community 56 - "Automation Test Utilities"
Cohesion: 0.10
Nodes (52): Ctx, due_one_time(), FakeClock, FakeKernel, FakeResult, FakeTask, _force_running(), make_worker() (+44 more)

### Community 57 - "LLM Client Capabilities"
Cohesion: 0.07
Nodes (20): _cooling(), LLMClient, LLMError, Exception, GENUINE streaming completion: `on_token(str)` is called for every content delta…, Native Ollama: POST /api/chat with stream:true (NDJSON deltas)., litellm stream=True — per-chunk deltas (works for Ollama + Gemini)., One LLM completion. Returns the normalized dict: {content: str|None,… (+12 more)

### Community 58 - "Permission Risk Layer"
Cohesion: 0.22
Nodes (8): PermissionDecision, decide(), Permission decisions (Phase 2) — ONE entry point over the existing guard. Does…, (risk_level, capabilities) from the security risk layer; ('low', ()) for non-…, Full gate for one tool call. `approver` — optional (tool, args, reason) -> bool…, risk_info(), test_permission_allow_ask_deny(), test_permission_risk_metadata()

### Community 59 - "Hardware Control Tools"
Cohesion: 0.11
Nodes (30): _battery(), _specs(), format_hardware(), get_battery(), get_hardware(), _keybd(), lock_workstation(), media() (+22 more)

### Community 60 - "Tool Effect Verification"
Cohesion: 0.12
Nodes (32): Observation, What the kernel SAW happen for one tool call (never the model's claim)., VerificationResult, check_effect(), Path, Effect verification (Phase 2). Rule: a task is verified by OBSERVING the world,…, Extract the intended filesystem target from the request, if any. Returns (kind,…, Whole-task verdict. fail — a tool errored, an effect check failed, or the… (+24 more)

### Community 61 - "Voice Agent Adapters"
Cohesion: 0.08
Nodes (34): available(), _build_brain(), _edge_tts_mp3(), make_stt(), make_token(), make_tts(), _pyttsx3_wav(), LiveKit agent — BEE's live realtime voice (free-tier LiveKit Cloud). python -m… (+26 more)

### Community 62 - "Local STT Device"
Cohesion: 0.15
Nodes (14): _voice_once(), _gpu_error(), _load(), _model_dir(), _pick_device(), Exception, Path, Local model home — real files, never the HF cache's symlink layout. (+6 more)

### Community 63 - "Tool Execution Regressions"
Cohesion: 0.09
Nodes (22): _allowing_kernel(), A kernel that grants every permission, so a test can observe the LOOP's own…, dsa_gcd_lcm spent 48 tool calls on one task: a 3B model that re-runs broken…, Same loop, different symptom: six SUCCESSFUL calls of one tool with ever-…, dsa_gcd_lcm / dsa_lis / dsa_graph, live: tools=0 and an answer that DESCRIBES a…, A45a: the model displayed code that stores the results in variables and never…, The read-out must only be appended when there is no output of its own —…, When permission is refused the answer must not pretend the computation happened… (+14 more)

### Community 64 - "Capability Guard Rails"
Cohesion: 0.13
Nodes (17): check(), classify(), make_approver(), mode: cli (prompt), unattended (auto-deny), always (auto-approve). WARNING:…, Full gate. Returns (proceed, action, reason). ask → consults the approver.…, Returns (action, reason) where action in allow|ask|deny., Guard rule table — labeled commands. Run: python tests/test_guard.py, The kernel asks about a CAPABILITY with args={} (a capability spans several… (+9 more)

### Community 65 - "Markdown Memory Primitives"
Cohesion: 0.12
Nodes (24): add_facts(), all_chunks(), chunk_md(), _clean_fact(), _fact_core(), _finger(), is_transcript(), memory_search() (+16 more)

### Community 66 - "Model Training Pipeline"
Cohesion: 0.22
Nodes (10): Bee-8B QLoRA Local Brain, BEE LLM Component Design, J3 Model Upgrade Quality Gate, Constitutional AI and RLAIF Pipeline, Training and Scale Plan, 3D Parallelism TP PP DP Design, Verification Report, Verify Suite 71914 Checks All Pass (+2 more)

### Community 67 - "Vector Memory Search"
Cohesion: 0.14
Nodes (21): _fn_flush_memory_index(), One-line digest of a SUCCESSFUL tool-using task (task -> outcome). Diary…, record_win(), _dirty_file(), flush_dirty(), get_store(), mark_dirty(), memory_search_hybrid() (+13 more)

### Community 68 - "Desktop Interaction API"
Cohesion: 0.09
Nodes (4): Desktop, Protocol, Resolve the foreground window from its handle directly. The old version…, WindowInfo

### Community 69 - "Session Memory Protocols"
Cohesion: 0.07
Nodes (13): EntityMemory, EpisodicMemory, ProceduralMemory, Protocol, Short-horizon state for the active session (kernel-owned, in-process)., What happened, when (tasks, tool calls, outcomes)., Durable facts: profile, long-term notes, RAG corpus., How to do things: skills distilled from novel successes. (+5 more)

### Community 70 - "System Configuration Layers"
Cohesion: 0.18
Nodes (12): Agent Interface chat classify match, Honesty Rules and Labels, LlmAgent Local Ollama Backend, Campus Life Mini Program, Mood Radar Six Axes, OfflineAgent Lexicon Matcher Backend, Page to Component Test Shim, Local Storage Quota Prune Path (+4 more)

### Community 71 - "Task Scoped Policies"
Cohesion: 0.16
Nodes (6): CapabilityStore, Path, User-configurable policies. File format (config/capabilities.yaml):…, Task-scoped grants die with the task — never carried over., test_grant_is_task_scoped_never_inferred(), test_store_loads_user_config()

### Community 72 - "Docker Sandbox Security"
Cohesion: 0.22
Nodes (17): sandbox_tools(), _ctx(), R, GPU fallback tests for the Docker sandbox tool (no docker calls are made —…, Operator knobs: disable read-only + run as image default user (old root image…, Stub subprocess.run: track only `docker run` argv; probes get plain success., A non-'none' network mode silently voids the SECURITY.md boundary — refuse…, If the .env mask cannot be created, fail closed instead of running unmasked… (+9 more)

### Community 73 - "Treehole Post Management"
Cohesion: 0.13
Nodes (21): add(), anonId(), close(), counts(), dayKey(), validate(), WORDS, agent (+13 more)

### Community 74 - "Post-Answer Verification"
Cohesion: 0.08
Nodes (43): _calc_checks(), _claim_checks(), _claimed_targets(), _clause_start(), _file_checks(), _hedged(), _opened_urls(), _phantom_file_checks() (+35 more)

### Community 75 - "Itinerary Planning Tool"
Cohesion: 0.16
Nodes (22): classify(), _daily_blocks(), _dispatch(), _llm(), _load(), _next_id(), _open(), _paths() (+14 more)

### Community 76 - "Context Assembly Logic"
Cohesion: 0.08
Nodes (28): _api_lines(), build_sub_system(), build_system_prompt(), canonical_system_prompt(), Context, _doc1(), Path, Per-turn context assembly: system prompt, skills index, memory pointers. (+20 more)

### Community 77 - "UI Observation Events"
Cohesion: 0.13
Nodes (12): Inspect the visible UI (read-only). Returns the structured snapshot the agent…, EventBus, callable, THE shared EventBus (audit item 9 — one implementation, project-wide). Before…, Convenience: receive every event (the kernel facade uses this)., Routing key: explicit name attr (BusEvent) or kind.value (AgentEvent)., Dispatch; returns the number of handlers INVOKED (a handler that raises is…, _Ev (+4 more)

### Community 78 - "Graph Algorithms Library"
Cohesion: 0.11
Nodes (23): _adj(), bellman_ford(), bfs(), build_adj(), dfs_order(), dijkstra(), floyd_warshall(), has_cycle_undirected() (+15 more)

### Community 79 - "Prompt Injection Guard"
Cohesion: 0.14
Nodes (22): Wrap external content in an UNFORGEABLE data fence. The fence used to be a…, untrusted_fence(), _blocked(), _model_views(), Prompt-injection corpus (acceptance audit YELLOW: "no injection corpus test…, Same rule end-to-end: approve before the fetch, deny after — the post-fetch…, The markers used to be constant, so external content that printed the END…, End-to-end: what the MODEL actually sees must be un-escapable. (+14 more)

### Community 80 - "Static Contract Analysis"
Cohesion: 0.14
Nodes (22): _collect(), _collect_class(), find_mismatches(), _function_contexts(), _lookup_method(), _mismatch(), AST, Call (+14 more)

### Community 81 - "Hardware Recall Tests"
Cohesion: 0.11
Nodes (22): _no_inventory(), _probe_kernel(), End to end: store a fact, then ask for it in 'Remember …?' form and get the…, Diary chunks record the assistant's own past answers, including wrong ones.…, Pin the live CIM round-trip off. These tests are about what memory says; the…, Search your memory for hardware' used to be answerable only if the user had…, profile.md on this box says 'NVIDIA RTX 3050 8 GB' while CIM reports 4 GB.…, Both chunks are 'authoritative' profile/longterm memory, so the source ranking… (+14 more)

### Community 82 - "Capability Authorization Tests"
Cohesion: 0.11
Nodes (29): CapabilityGate, _Entry, IntEnum, Pre-execution authorization. `confirmer(capability, reason) -> bool` is the…, Risk, _gate(), Capability-based authorization tests (Phase 3, Parts A/B). Run: python -m…, Layering: capability gate first, then the guard's per-command layer. (+21 more)

### Community 83 - "Automation Management Tool"
Cohesion: 0.18
Nodes (21): automation_job(), _days_from(), _num(), automation_job tool (Phase 6) — user-facing automation management. The user…, Cast a model-supplied number with a message that names the field and the…, Accept the integers the schema documents and the day names a small model writes…, _trigger_from(), _worker() (+13 more)

### Community 84 - "RAG Recall Evaluation"
Cohesion: 0.10
Nodes (19): Deterministic recall@k: for each (question, answer_key), did a chunk containing…, recall_eval(), _FakeStore, RAG — trigger detection + deterministic recall@k. Run: python tests/test_rag.py, The write path only queues — it must never block on an embedding call., A maintenance job the `scheduler.enabled` switch does not stop is the defect…, Regression against the way this feature was first written wrong:…, A queue is only as good as its last write: an index left stale (empty queue,… (+11 more)

### Community 85 - "Agent Kernel Implementation"
Cohesion: 0.11
Nodes (16): _agent_stub(), AgentKernel, _hardware_note(), _hw_conflict(), _qwords(), Warn when a stored spec contradicts the machine standing in front of us.…, Live inventory for a recall about the box itself ('' / {} if not one)., First-class cancellation: stop the active task safely. (+8 more)

### Community 86 - "Evaluation Logic Regressions"
Cohesion: 0.06
Nodes (41): match(), Remind me what my passport number is' is a question, not a reminder. The fast…, What is in the oven' must not be answered with a directory listing., What hardware do I need to run llama" is a purchase question; 'what is the spec…, Non-Windows or a blocked CIM query must not produce a fake spec sheet., The eval's own sentence: 'Run python: <snippet> — list which sorts are correct…, The 120-char ceiling was global before; the per-path `max_len` must not quietly…, test_empty_snippet_is_not_a_command() (+33 more)

### Community 87 - "Capability Authorization Layer"
Cohesion: 0.18
Nodes (11): capabilities_for(), Capability, GateDecision, Capability-based authorization (Phase 3, Part A/B). Capabilities are coarse…, Capabilities required to run `tool` with these args (base + escalation)., test_code_run_delete_escalation(), test_shell_escalation_delete(), test_shell_escalation_system_and_network() (+3 more)

### Community 88 - "Evaluation Suite Runner"
Cohesion: 0.11
Nodes (19): _module_hint(), A45c: the index line used to carry only the description, so BEE knew a `dsa`…, check_task(), _events_ok(), Eval suite runner — the self-improvement gate. Runs evals/tasks.yaml through…, _ctx(), Planning inputs (A45b / A45c / A45d). The 21-task eval kept failing…, expect_any must not weaken `expect`: computed values stay mandatory. (+11 more)

### Community 89 - "Local Model Server"
Cohesion: 0.15
Nodes (19): _base(), _boot(), _child_env(), exe_path(), _is_local(), _launch(), _model_present(), Start the local model server when the user expects it and it is not running.… (+11 more)

### Community 90 - "Voice State Bridge"
Cohesion: 0.13
Nodes (19): _bearer_token(), get_state(), _push(), Live-voice shared state — HTTP push bridge (replaces the temp-JSON file). The…, Last state recorded in THIS process (debug/diagnostics). The web UI reads its…, Same source the webapp resolves from: BEE_WEB_TOKEN env, else the per-server…, Record the state locally (debug) and push it to the web UI., Best-effort POST to the web UI. Returns True on 2xx. (+11 more)

### Community 91 - "Secret Detection Scanner"
Cohesion: 0.16
Nodes (19): Finding, _is_binary(), main(), mask(), Path, Lightweight secret detection for source / generated-file audits. Usage: python…, Scan the project tree (excluding .env and data dirs). Sorted, stable., Safe form of a credential for logs: prefix + length only. (+11 more)

### Community 92 - "LiveKit Audio Transport"
Cohesion: 0.07
Nodes (17): _agent_token(), _decode_audio(), LiveKitTransport, LiveKit as a VoiceTransport (Phase 4). Implements the transport protocol…, Room JWT for the agent participant (room join + publish/subscribe)., Nearest-neighbor mono s16 resample (good enough for voice)., Decode TTS bytes (mp3 or wav) to mono s16le @ to_rate via PyAV. PyAV ships with…, A LiveKit room behind the VoiceTransport protocol. (+9 more)

### Community 93 - "Cancellable Subprocess Execution"
Cohesion: 0.15
Nodes (17): envelope(), Tool-result dict. `limit` overrides the default truncation cap so a tool's own…, T, _kill_tree(), Cancellable subprocess execution (J1 — audit item 3). The old exec tools used…, Run `cmd`; returns (returncode, stdout, stderr, kind) with kind in {'ok',…, run_cancelable(), code_tools() (+9 more)

### Community 94 - "Model Quality Gate"
Cohesion: 0.10
Nodes (34): _fn_model_gate(), J3: model-upgrade quality gate (candidate vs recorded baseline)., _adjudicate(), baseline_record(), clear_pending_candidate(), load_baselines(), model_quality_gate(), _now() (+26 more)

### Community 96 - "Evaluation Hermeticity Tests"
Cohesion: 0.13
Nodes (18): _digest(), _null, Eval hermeticity for telemetry and the training corpus (A44).…, `_run_suite` documents that the kernel resolves its sessions and receipts at…, Making SESSIONS_DIR/RECEIPTS_FILE module constants is what exposed the second…, A61: `train/` and `evals/` were the two write roots conftest never moved. So a…, Everything a scored run must leave byte-for-byte alone., Drives the REAL stack (run_suite -> AgentKernel -> run_agent) and fakes only… (+10 more)

### Community 97 - "Binary Search Tree"
Cohesion: 0.20
Nodes (19): bst_contains(), bst_insert(), count_nodes(), from_sorted(), height(), inorder(), is_valid_bst(), lca() (+11 more)

### Community 98 - "Preference Pair Derivation"
Cohesion: 0.22
Nodes (13): _bad_chosen(), derive(), derive_candidates(), _is_model_failure(), _is_plumbing(), _load_episodes(), load_goldens(), main() (+5 more)

### Community 99 - "Typed Execution Planner"
Cohesion: 0.10
Nodes (26): Action, Plan, One executable step in a plan. `tool` is a registered ToolBus name; None means…, Kernel-owned execution plan (Phase 8: typed + validated BEFORE ToolBus). kind:…, build_plan(), classify_intent(), Typed planner (Program Phase 8, 2026-10-08). Division of labor, exactly as the…, Kernel-built plan for one execution attempt. The kernel (not the LLM)… (+18 more)

### Community 100 - "Human Feedback Store"
Cohesion: 0.15
Nodes (28): blocklisted(), _conn(), corrections(), _db(), get(), pair_key(), pairs(), Path (+20 more)

### Community 101 - "Chat Classification Logic"
Cohesion: 0.17
Nodes (19): bankFor(), beforeFragment(), bigrams(), chat(), classify(), hits(), idfFactory(), L (+11 more)

### Community 102 - "Task Plan Store"
Cohesion: 0.25
Nodes (10): _plan(), fixture, A54 — /plan owns a JSON task store, and three ways to lose the user's tasks.…, The write goes to a sibling temp file and is renamed over the store, so a…, store(), test_a_save_never_leaves_a_partial_file(), test_an_unreadable_store_is_kept_not_erased(), test_ids_do_not_repeat_after_a_prune() (+2 more)

### Community 103 - "Heap and Quickselect"
Cohesion: 0.24
Nodes (18): median(), quickselect(), Binary heap (min/max) + quickselect — independent of `heapq` internals.…, Median (lower-middle for even n) in expected O(n) via quickselect., k-th smallest (0-indexed) element in expected O(n) via 3-way quickselect.…, _check(), Random, Comprehensive correctness verification for the BEE DSA library.… (+10 more)

### Community 104 - "Agent Session State"
Cohesion: 0.18
Nodes (9): AgentSession, Path, Compact state block the kernel can inject so the model has the conversation…, test_session_context_block(), test_session_followup_resolution(), test_session_persistence_round_trip(), test_05_corrupt_session_file_degrades_to_new(), The voice layer and the REPL are the same session: a voice follow-up resolves… (+1 more)

### Community 105 - "SFT Eligibility Filter"
Cohesion: 0.16
Nodes (20): Chat messages with `loss` flags from a stored episode row. Returns (messages,…, row_to_messages(), label_row(), detect_type(), _last_ev(), Path, Episode validation — the SFT eligibility filter. An episode is training-…, row: parsed episode JSON. Returns {type, verdict, why}. (+12 more)

### Community 106 - "Mood Radar Visualization"
Cohesion: 0.17
Nodes (16): attached(), { polygon }, recompute(), AXES, clamp100(), KEYWORDS, localDay(), mentions() (+8 more)

### Community 107 - "Deterministic Claim Verifier"
Cohesion: 0.12
Nodes (14): _calc(), Verifier — deterministic claim checks against episode events + disk. Run:…, Did any tool run?' is far too weak. Live evidence: the model made 23 harmless…, The rule must not demand evidence for prose it cannot resolve to a target, or…, I ran out of steps…" is ordinary speech, but 'ran' sat in the claim verb list,…, The eval produced `I executed the shell command 'git reset --hard HEAD~1'` with…, test_a_claim_must_match_a_receipt_not_just_any_receipt(), test_a_claim_without_a_quoted_target_needs_only_some_receipt() (+6 more)

### Community 108 - "Structural Vision Backend"
Cohesion: 0.16
Nodes (6): Element, Protocol, One detected UI element (vendor-neutral)., Vendor-free default: 'vision' over the structural desktop snapshot. Elements =…, StructuralVision, VisionBackend

### Community 109 - "Router Training Metadata"
Cohesion: 0.12
Nodes (23): _fn_train_router(), default_meta(), features(), _NUM_FEAT_NAMES(), Path, Training-time environment metadata recorded INTO the artifact (Phase 7). Keys:…, Persist the artifact WITH training metadata (Phase 7). Callers that know the…, save_bundle() (+15 more)

### Community 110 - "Streaming TTS Engine"
Cohesion: 0.15
Nodes (8): Event, Immediate teardown (barge-in): drop queued sentences + flag the in-flight…, GENUINE streaming: consume edge-tts's chunk iterator live., sink(audio_bytes) plays one chunk; on_first() fires at the first chunk of an…, Start a fresh utterance (resets first-chunk tracking). `busy` is set…, StreamingTTS, feed() refuses to enqueue once the utterance is cancelled., test_feed_after_stop_is_dropped()

### Community 111 - "System Health Metrics"
Cohesion: 0.20
Nodes (18): cpuPct(), ftVal(), getBattery(), getDisk(), getRam(), healthHandler(), main(), round1() (+10 more)

### Community 112 - "Agent Core Logic"
Cohesion: 0.17
Nodes (14): createAgent(), chat(), classify(), decide(), explain(), mode(), ready(), setPreference() (+6 more)

### Community 113 - "Native System Telemetry"
Cohesion: 0.08
Nodes (31): _sysstats(), build(), _client(), _create_flags(), ensure(), healthy(), _install_go(), _launch() (+23 more)

### Community 114 - "Tiered Routing Logic"
Cohesion: 0.24
Nodes (11): parametrize, _r(), Routing tiers: explicit > deterministic > ML > heuristic. Run: python…, test_deterministic(), test_deterministic_phrased(), test_explicit(), test_heuristic(), test_legacy_api() (+3 more)

### Community 115 - "Agent Core Loop"
Cohesion: 0.05
Nodes (50): LLM client: LiteLLM primary, native Ollama HTTP fallback. chat(name, messages,…, _offline_result(), BEE core agent loop — production edition (Phase 4). Pipeline per task: route…, _redact_for_cloud(), BEE hybrid brain: routing, privacy, verification, RAG, ML router. The…, Episode, Episode logger — persist complete task episodes for the data pipeline. Each…, Serialize + REDACT before persistence. Episodes feed SFT builds and cloud… (+42 more)

### Community 116 - "UI Design Assets"
Cohesion: 0.18
Nodes (18): Active state design vivid blue outline, explore.png inactive location pin icon gray, explore-on.png active location pin icon blue, Explore tab concept location pin discovery, Inactive state design muted slate gray outline, index.png inactive home house icon gray, index-on.png active home house icon blue, Index Home tab concept house (+10 more)

### Community 117 - "Code Generation Tool"
Cohesion: 0.36
Nodes (8): code(), _debug_fallback(), _detect_lang(), _llm(), /code — production-grade code generation + systematic debugging. Usage: /code…, _save(), _skeleton(), test_code_lang_detection()

### Community 118 - "Deterministic Offline Fallback"
Cohesion: 0.21
Nodes (15): Deterministic offline fallback — real answers for a narrow task class when…, Returns a deterministic answer, or an honest capability message., run_offline(), _try_list(), _try_math(), _try_sort(), Offline deterministic fallback. Run: python tests/test_offline.py, test_fallback_message() (+7 more)

### Community 119 - "Binary Heap Implementation"
Cohesion: 0.19
Nodes (5): Heap, 1-indexed binary heap. min_heap=True gives a min-heap (smallest on top)., True if x has higher priority than y (should sit above it)., Push x then pop the top, atomically. O(log n). Returns min(x, old_top),…, The k largest (default) or k smallest items currently in the heap.

### Community 120 - "Action Claim Correction"
Cohesion: 0.22
Nodes (4): Same shape as tests/test_kernel_integration.py, plus chat_stream so the…, A 3B model says 'I executed git reset --hard' having run nothing. The verifier…, ScriptedClient, test_unverified_action_claim_gets_corrected_before_the_task_ends()

### Community 121 - "Structured Retry Policy"
Cohesion: 0.17
Nodes (9): EventBus, Path, FailureKind, str, Structured retry policy (Phase 2). Failure kinds are classified BEFORE any…, True when a blind re-run could double-act. Read-only exec (ls/cat/ echo/python…, RetryPolicy, test_retry_policy_classification() (+1 more)

### Community 122 - "Streaming Client Contract"
Cohesion: 0.19
Nodes (17): _fake_http(), _local_client(), _nd(), Real-client streaming contract (docs/TECHNICAL_DEBT.md A37). Every previous…, A37b: the recovery branch read `e._partial`, which nothing in the codebase ever…, Same two rules checked on the other provider branch., A38: `ollama_chat/` is a CHAT provider, so litellm raised…, The native loop is the safety net, so it stays reachable — and taking it is… (+9 more)

### Community 123 - "Evaluation Scoring Metrics"
Cohesion: 0.09
Nodes (37): 95% Wilson score interval for k passes in n trials (None when n = 0). P1-3: the…, A52: `score` is the latest row per task id over ALL of results.jsonl, so a…, skip_if contract. `cloud`: the cloud tier is down, so a task that grades it…, _run_tasks(), _should_skip(), summarize(), wilson_interval(), agent_eval_lines() (+29 more)

### Community 124 - "Node Test Configuration"
Cohesion: 0.12
Nodes (15): description, devDependencies, jest, jest-environment-jsdom, miniprogram-simulate, name, private, scripts (+7 more)

### Community 125 - "Job Execution History"
Cohesion: 0.07
Nodes (36): Durable automation + proactive agent (Phase 6). Objects (per the Phase 6 spec):…, display_local(), ExecutionHistory, iso(), JobExecution, parse_dt(), datetime, Durable automation models (Phase 6; UTC-canonical storage, 2026-10-08). Job /… (+28 more)

### Community 126 - "Agent Kernel Runtime"
Cohesion: 0.18
Nodes (16): BEE Agent Kernel (Phase 2) — one coherent agent runtime. Objects: AgentSession,…, Single-shot LLM task for slash commands — SAME kernel infrastructure (provider…, Task, TaskState, _ts(), can_transition(), InvalidTransitionError, Exception (+8 more)

### Community 127 - "Agent Execution Results"
Cohesion: 0.06
Nodes (54): AgentResult, _diary(), _finish(), _fmt_result_text(), _golden(), True when the CLOUD tier produced this answer (teach-back material).…, Teach-back: a successful CLOUD answer becomes training material for the local…, Execute one matched fast path. Returns an AgentResult, or None to fall through… (+46 more)

### Community 128 - "Streaming STT Implementation"
Cohesion: 0.14
Nodes (11): pcm_to_float(), RuntimeError, Streaming STT (Phase 4) — interim + final transcripts. faster-whisper is…, Final transcript over the whole utterance; honors self.timeout., Windowed partials + one final pass, over faster-whisper., Interim transcript of the utterance so far ('' if nothing yet)., StreamingSTT, SttError (+3 more)

### Community 129 - "LLM Prompt Templates"
Cohesion: 0.13
Nodes (10): offline, prompts, timeoutError(), CHAT_BASE, CLASSIFY_SCHEMA, CLASSIFY_SYSTEM, EXPLAIN_SYSTEM, MOODS (+2 more)

### Community 130 - "Logging and Notifications"
Cohesion: 0.07
Nodes (39): Install the app-wide log handler, once, on every BEE surface. Before this…, setup_logging(), _cooldown_ok(), _load_state(), _mark_fired(), _notify_store(), os_notify(), Path (+31 more)

### Community 131 - "Acoustic Trigger Detection"
Cohesion: 0.20
Nodes (4): ClapDetector, Double-clap acoustic trigger (ported from Super JARVIS / Hector). python -m…, Listens on the microphone for double-clap acoustic signatures., run_clap_mode()

### Community 132 - "SSRF Web Security"
Cohesion: 0.16
Nodes (13): BEE security layer (Phase 1). Modules: netguard — SSRF-hardened URL fetching…, mark_untrusted(), Wrap a web-tool result so the model sees it as DATA, never as instructions…, truncate(), _fetch(), _html_to_text(), web_fetch / web_search — SSRF-guarded httpx + HTML->text, DuckDuckGo (no API…, html.duckduckgo.com - verified working from this network (2026-10 probe). (+5 more)

### Community 133 - "Microphone Audio Capture"
Cohesion: 0.27
Nodes (13): _has(), _pcm_to_float(), Path, RuntimeError, Microphone capture with silence detection. Primary: sounddevice (numpy frames).…, Best-effort mic capture across available backends., _read_wav(), record() (+5 more)

### Community 134 - "Tool Call Extractor"
Cohesion: 0.24
Nodes (12): _extract_text_tool_calls(), _iter_json_blocks(), Yield each top-level {...} block (string/escape aware). Handles JSONL-style…, Small local models sometimes emit tool calls as TEXT (JSON / JSONL / fenced).…, Unit tests for the text tool-call extractor (handles JSONL/fenced/array +…, test_args_as_string(), test_array(), test_empty() (+4 more)

### Community 135 - "Vector Store Management"
Cohesion: 0.23
Nodes (6): lancedb renamed table_names() -> list_tables() (0.39 warns on the old…, Clear-before-add (B2/M12 fix, audit 2026-10-06): the old implementation did…, Re-index ONE memory file: drop its old rows, add the current chunks.…, _VecStore, B2/M12: rebuilding twice must NOT double the row count., test_vector_rebuild_no_duplicates()

### Community 136 - "Text-to-Speech Synthesis"
Cohesion: 0.13
Nodes (23): _decode_to_wav(), _edge_tts_speak(), enqueue(), _play_media(), Path, py_voices(), _pyttsx3_speak(), Text-to-speech. Primary: pyttsx3 (offline; SAPI5 on Windows, espeak on Linux,… (+15 more)

### Community 137 - "ML Router Reporting"
Cohesion: 0.07
Nodes (26): _fn_alert_scan(), Daily threshold alerting (audit item 6): evaluate metrics stats against…, _pctl(), ML router report (Program Phase 7, 2026-10-08). One place to answer "how is the…, Recommend router.ml_confidence from measured outcomes (auto-tuning). Joins…, Fallback rate + latency percentiles over the last `window_hours`., runtime_report(), tune_thresholds() (+18 more)

### Community 138 - "Dynamic Programming Recipes"
Cohesion: 0.12
Nodes (15): coin_change(), coin_change_count(), edit_distance(), knapsack(), lcs(), lis(), Classic dynamic-programming recipes with complexity notes., Max revenue cutting a rod of length n (prices[i] for length i+1). O(n^2). (+7 more)

### Community 139 - "Structured Memory Store"
Cohesion: 0.11
Nodes (6): _Entity, _Episodic, _Procedural, Entity memory over the structured store (type='entity')., Kernel's in-memory working set, scoped by task (global notes use "")., _Working

### Community 140 - "Screenshot Retention Policy"
Cohesion: 0.20
Nodes (5): Path, Bounded screenshot retention. Default (save_dir=None): in-memory hash ring only…, Delete ALL saved frames (called on session end / emergency stop)., ScreenshotStore, test_11_screenshot_retention()

### Community 141 - "Trie Prefix Tree"
Cohesion: 0.24
Nodes (3): _Node, Trie (prefix tree) — autocomplete, spellcheck, prefix queries. O(L) per op…, Trie

### Community 142 - "Safe Math Evaluation"
Cohesion: 0.10
Nodes (23): _check_bounds(), _ev(), eval_safe(), _guarded_pow(), _pow_func(), AST, Path, Shared helpers for tools: the T registry type, output envelopes, safe eval,… (+15 more)

### Community 143 - "Hybrid Task Routing"
Cohesion: 0.11
Nodes (25): _embedded_expr(), _heuristic(), _is_det(), math_expr(), needs_vision(), _normalize_expr(), Hybrid routing — four tiers, fused heuristics + learned ML. Tiers (in order of…, True when the residue is arithmetic whose only names are math functions. The… (+17 more)

### Community 144 - "App Manifest Testing"
Cohesion: 0.18
Nodes (8): app, BUILTIN_TAGS, fs, pageDirs, path, ROOT, SOURCE_DIRS, SOURCE_FILES

### Community 145 - "HTTP Client Testing"
Cohesion: 0.20
Nodes (8): http, request(), { URL }, agent, { createLlm }, llm, offline, { request }

### Community 146 - "Web Approval Interface"
Cohesion: 0.13
Nodes (17): client(), _FakeKernel, fixture, Web interactive approvals + /voice event-loop safety (2026-10-17). The web…, Stop (Escape) must not wait out the approval timeout., get_ctx() used to start automation FIRST: start_automation() then installed…, `python -m bee web` goes through cli._web — same live bug, second launcher: it…, While /voice is stuck in STT, other routes must still answer — the blocking… (+9 more)

### Community 147 - "Modular Slash Commands"
Cohesion: 0.15
Nodes (13): _plate(), One implementation for both surfaces: the spoken fast path and /remind share…, _remind(), _remind_cancel(), _remind_cmd(), _remind_list(), _todo(), Command (+5 more)

### Community 148 - "System Audit Status"
Cohesion: 0.25
Nodes (11): JARVIS Acceptance Audit, Agent Kernel run_agent Loop, FastPaths Deterministic Tier, Production Readiness Audit, Single Kernel Routing All Surfaces, Spawn Task Gate Bypass P0, Feature Status Authoritative, Agent Eval 18 of 21 (+3 more)

### Community 149 - "Document Summarization Tool"
Cohesion: 0.33
Nodes (9): _extractive(), _fetch_url(), _llm(), /summarize — articles, papers, reports → executive summary + dense bullets +…, Comparative table of entity→number pairs (metrics, prices, versions)., _read_file(), _sentences(), summarize() (+1 more)

### Community 150 - "Cross-Process Safe IO"
Cohesion: 0.16
Nodes (15): _acquire(), append_json(), append_line(), append_text(), Cross-process-safe line appends for BEE's JSONL / markdown streams. Every…, Write `text` (bytes exactly as given) at the end of the file, with no other…, Append one JSONL record (the newline is added here)., _release() (+7 more)

### Community 151 - "Voice Transport Protocol"
Cohesion: 0.20
Nodes (5): Protocol, Establish capture/playback. Raises TransportError on failure., Blocking read of one ~100 ms 16 kHz mono s16le frame. Returns None on timeout…, Render a TTS audio chunk (format is transport-specific)., VoiceTransport

### Community 152 - "LLM Utility Functions"
Cohesion: 0.40
Nodes (10): createLlm(), chat(), clamp(), classify(), contentOf(), explain(), parseMood(), probe() (+2 more)

### Community 153 - "ML Training Skills"
Cohesion: 0.20
Nodes (10): finetune SKILL, QLoRA fine-tuning Qwen3 8GB 3050, pytorch SKILL, PyTorch VRAM budget training skeleton, Docker ML environment sandbox_run GPU, sandbox SKILL, transformers SKILL, HF Transformers inference dataset pipeline (+2 more)

### Community 154 - "Windows API Shims"
Cohesion: 0.17
Nodes (7): _fake_win32(), _FakeWin32, WindowsDesktop validates `import win32con, win32gui` at construction. These…, The old version searched list_windows() (which drops untitled windows), so a…, test_active_window_falls_back_when_the_api_raises(), test_active_window_is_none_only_when_truly_unknown(), test_active_window_resolves_the_handle_directly()

### Community 155 - "Idea Analysis Tool"
Cohesion: 0.36
Nodes (8): register(), _deterministic(), _facts(), _llm(), /think — stress-test ideas, trade-offs, pros/cons matrices, strategic…, Pull claim-ish fragments (numbers, named risks, constraints) for the…, _save(), think()

### Community 156 - "DSA Benchmark Harness"
Cohesion: 0.31
Nodes (8): check(), compare_sorts(), Path, Benchmark + correctness harness for the DSA library. run_bench(fn, *args,…, Benchmark all sorting implementations on the same random input; verify against…, report(), run_bench(), time_once()

### Community 157 - "Filesystem Security Tools"
Cohesion: 0.19
Nodes (16): _edit_file(), _file_list(), file_tools(), Path, Filesystem tools: file_read, file_write, file_list, file_edit., Windows name-shape attacks the resolve() check cannot see: ADS streams…, _read_file(), _reject_unsafe_name() (+8 more)

### Community 158 - "Time Formatting Utilities"
Cohesion: 0.42
Nodes (7): ago(), clock(), countdown(), day(), pad(), shifted(), stamp()

### Community 159 - "Test Isolation Markers"
Cohesion: 0.28
Nodes (6): _isolate_append_only_streams(), _isolate_post_task_model_calls(), pytest_configure(), Test pyramid markers (audit 2026-10-06; Phase-7 categories 2026-10-08). The…, Reflection (A40b) adds ONE local-model call after every non-trivial task, on…, A test run must not write into the user's real telemetry or training data.…

### Community 160 - "Isolated Eval Environment"
Cohesion: 0.12
Nodes (20): eval_approver(), _isolated_memory(), _isolated_telemetry(), Path, The permission prompt the eval answers on the user's behalf. `file_write` is…, Leave every source file exactly as the run found it — by bytes, not by git.…, Public entry: the run happens against an isolated copy of memory, and the…, only: substring match (str) or explicit id list (list) — for batched runs.… (+12 more)

### Community 161 - "Union Find Reference"
Cohesion: 0.36
Nodes (3): UnionFind, Union-find reference (independent of graphs.has_cycle_undirected)., _ref_has_cycle()

### Community 162 - "Planner Logic Regressions"
Cohesion: 0.09
Nodes (29): _no_fastpath(), _plan_ctx(), no function calls were provided / the available functions are…' is the model…, These two tests aim at the loop's wrap-up logic. Listing the workspace is now…, math_sieve on the live box: 39.9 s, tools=0, and the shipped answer was `I'm…, The fix must not turn a recoverable ramble into a declared failure: one ramble,…, plan_complex, live: '…Use the planner tool.' answered with 'None of the…, P1: the planner used to run only when the user asked for a plan, as a post-hoc… (+21 more)

### Community 163 - "Semantic Memory Retrieval"
Cohesion: 0.13
Nodes (12): auto_context(), needs_context(), RRF fusion of vector (when available) and keyword rankings., Markdown context block for the system/user message, or '' if not needed., retrieve(), Long-term markdown memory. Phase 8: entries carry PROVENANCE inline (source…, _Semantic, test_semantic_add_writes_provenance() (+4 more)

### Community 164 - "Lexicon Word Lists"
Cohesion: 0.25
Nodes (7): INTENSIFIERS, MOOD_WORDS, NEGATED_TARGET, NEGATIONS, REPLIES, SEPARATORS, TOPIC_STOP

### Community 165 - "Core Group Management"
Cohesion: 0.36
Nodes (5): byId(), join(), { match }, matchText(), rank()

### Community 167 - "Dependency Stack Management"
Cohesion: 0.25
Nodes (8): Core deps litellm lancedb fastapi apscheduler, requirements.txt BEE Core, requirements-ml.txt Pinned ML Stack, Pinned scikit-learn numpy scipy joblib versions, Router Model Artifact Meta, Docker sandbox GPU isolation note, Training code versus train data separation, training NOTE code vs data

### Community 168 - "Voice Command Loop"
Cohesion: 0.21
Nodes (11): BEE voice: mic capture -> faster-whisper (local) -> text; text -> TTS. Optional…, _ensure_gate(), print_status(), Voice command loop: listen -> (wake word) -> task -> speak. Usage in REPL:…, If text starts with/contains the wake word, return the remainder (or None)., Terminal approval for capability asks in voice mode. Voice has no kernel…, Attach a capability gate to kernel-less voice contexts. The REPL/web/LiveKit…, run_voice_loop() (+3 more)

### Community 169 - "App Transition Monitoring"
Cohesion: 0.22
Nodes (4): AppEventSource, Foreground-window and running-app transitions. Reads through the SAME desktop…, A foreground poll must not become an event storm: baseline first, then only…, test_app_event_source_emits_transitions_only()

### Community 170 - "Web and Voice Endpoints"
Cohesion: 0.32
Nodes (8): Web Auth Bearer Token, Chat SSE Endpoint, Web Chat UI, Face State Endpoint, Face Visualizer Page, Live Voice Page, LiveKit Token Endpoint, LiveKit Room Config

### Community 171 - "Technical Debt Audit"
Cohesion: 0.32
Nodes (8): JARVIS Baseline Audit, guard_blocked Eval Anomaly, Coherence Pass Fixes F0-F5, BEE to JARVIS Roadmap, Jarvis Milestones J1-J6, H1 AST Risk Layer for Code Run, Technical Debt Report, H8 Eval Safe Computation Budget

### Community 172 - "Execution Receipt Logging"
Cohesion: 0.18
Nodes (9): Human (or test) consult for a capability that needs confirmation. Mirrors the…, ExecutionReceipt, Append-only proof row for one meaningful action. Secrets are redacted before…, Path, Execution receipts (Phase 2) — append-only, redacted JSONL proof rows. Every…, ReceiptLog, _redact_value(), test_receipt_fields_and_redaction() (+1 more)

### Community 173 - "QLoRA Fine-tuning Script"
Cohesion: 0.53
Nodes (5): load_samples(), main(), Path, QLoRA fine-tuning of Qwen2.5-3B-Instruct for BEE — single 4 GB GPU friendly.…, summarize()

### Community 174 - "Security Model Overview"
Cohesion: 0.40
Nodes (6): N1 Guard Off Disables Capability Gate, Web Bearer Token Authentication, BEE Security Model, Docker Sandbox Boundary, Netguard SSRF Protection, ToolBus as Execution Dispatcher

### Community 175 - "Ollama Text Embeddings"
Cohesion: 0.40
Nodes (3): embed_texts(), Embeddings: Ollama (nomic-embed-text) via LLMClient. Lazy access. Usage: from…, Returns embeddings for `texts`. Raises RuntimeError if Ollama/embedder…

### Community 176 - "Service Health Checks"
Cohesion: 0.24
Nodes (11): offline_hint(), For `/health` and the web status panel: what the autostart actually did. There…, What to tell a user whose server is not answering. BEE can start it now, so the…, status(), cli_report(), _disk_free_gb(), docker_has_image(), Path (+3 more)

### Community 177 - "Safety and Guardrail Policies"
Cohesion: 0.40
Nodes (5): Capability Policies, Guard Mode, Coordinate Provenance Check, Emergency Stop Mechanisms, Safe Computer Action Set

### Community 178 - "Grok Web UI Components"
Cohesion: 0.50
Nodes (5): User chat bubble with text Hi agent, Essential and optional cookies consent banner with Reject All and Accept All Cookies, Grok full power features: AI images and videos, Skills and Connectors, Generate files, Chat history, Grok web UI screenshot showing gated conversation, Continue your conversation signup gate with Sign up for free CTA

### Community 179 - "Process Lifecycle Management"
Cohesion: 0.40
Nodes (5): grace(), For the router: a launch is in flight, so give the server the moment it needs…, The availability branch runs on every task; an idle-timeout here would be a…, test_grace_never_blocks_when_bee_never_launched_anything(), test_grace_picks_up_a_launch_that_completes_a_moment_later()

### Community 180 - "Architecture Documentation Authority"
Cohesion: 0.22
Nodes (8): AGENTS.md — BEE personal assistant (Windows-first, local-first), Architecture (don't re-derive; verified), Docs authority, Editing, Live services (creds in `.env` — check presence, never print values), Shell (PowerShell — plain `cmd` idioms break), Tests (source of truth: `tests/conftest.py`, CI: `.github/workflows/ci.yml`), Use Graphify before grep

### Community 181 - "State Reset and Fixtures"
Cohesion: 0.40
Nodes (5): Forget the one-attempt state (tests, or a user who starts Ollama by hand and…, reset(), _fresh_state(), fixture, One launch attempt per process is real behaviour — tests must not inherit it…

### Community 182 - "Memory and System Principles"
Cohesion: 0.50
Nodes (4): Memory Consolidation Design, Memory Layers and Nightly Consolidation, BEE System Prompt, Operating Principles Act Verify

### Community 183 - "Data Science Skills"
Cohesion: 0.50
Nodes (4): polars SKILL, Polars lazy scan filter group_by pipeline, sklearn SKILL, Tabular baseline LightGBM validation SHAP

### Community 187 - "Routing Threshold Configuration"
Cohesion: 0.09
Nodes (27): apply_threshold(), Write router.ml_confidence into config.yaml (explicit operator action). Regex…, Human-readable one-screen summary., render(), _cfg_p7(), p7(), fixture, Phase 7 — ROUTING + TEST/CI REPRODUCIBILITY (2026-10-08). Covers, with evidence… (+19 more)

### Community 206 - "Planner Integration Tests"
Cohesion: 0.25
Nodes (4): PlanFirstClient, A REAL LLMClient (so the loop's real-client gates fire, exactly as they do…, plan_complex: 'Use the planner tool.' The plan is produced BEFORE the model's…, test_plan_first_runs_for_a_plan_request_through_the_kernel()

### Community 220 - "Agent Query Execution"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Why does load_config() connect Voice, Agent Loop, LLM Client, ToolBus and 40+ other communities?, Source Nodes

### Community 221 - "Engine Routing Tests"
Cohesion: 0.13
Nodes (10): ctx(), fixture, Tests: engine choice (ctx.model_override) flows through run_agent in every…, RecordingClient, test_cloud_first_toggle_selects_local(), test_ctx_model_override_local(), test_ctx_model_override_ollama_cloud(), test_engine_endpoints_persist_and_apply() (+2 more)

### Community 223 - "Planner Logic Utilities"
Cohesion: 0.24
Nodes (8): explain(), gapsFrom(), label(), mmhh(), overlaps(), solve(), p, W

### Community 224 - "Hybrid RAG Memory"
Cohesion: 0.11
Nodes (15): Hybrid RAG over BEE memory — vector + keyword fused with Reciprocal Rank…, BEE — a local-first, self-improving, general-purpose personal agent. Stack (see…, BEE memory: Markdown (transparent) + optional LanceDB vectors (semantic search)., Structured memory store (Phase 3, Parts C/D). Five conceptual stores are…, load_episodes(), Episodes + cloud goldens → SFT dataset (Qwen chat format, loss-masked, PII-…, BEE data pipeline: episodes → validate → sanitize → SFT / router training data., build_report() (+7 more)

### Community 225 - "Module Layering Contract"
Cohesion: 0.29
Nodes (7): Path, Layering contract: bee.tools must not statically depend on bee.agent. History:…, Module-level imports reaching bee.agent (deferred function-level imports are…, `import bee.tools` in a fresh interpreter must not load bee.agent., test_tools_have_no_static_agent_import(), test_tools_import_without_agent(), _top_level_agent_imports()

### Community 226 - "DPO Model Training"
Cohesion: 0.60
Nodes (4): load_pairs(), main(), Path, Preference tune of Qwen2.5-3B-Instruct on train/prefs.jsonl — single GPU. Stage…

### Community 227 - "Schema Fitting Optimization"
Cohesion: 0.22
Nodes (4): Records the tool-schema count each route call received (P0-1)., P0-1: all 30 schemas are ~5.2k est tokens of the 7168 local budget — a live…, _SchemaRecClient, test_local_route_gets_the_fitted_schema_subset()

### Community 228 - "Module API Discovery"
Cohesion: 0.33
Nodes (8): module_api_card(), _module_source(), A50: a request that names one of BEE's own modules gets that module's REAL…, test_an_attribute_path_resolves_to_its_module(), test_card_lists_the_real_public_signatures(), test_names_that_are_not_project_modules_add_nothing(), test_the_card_is_bounded(), test_the_model_sees_the_card_in_the_request()

### Community 229 - "Global Emergency Hotkey"
Cohesion: 0.14
Nodes (14): hotkey_state(), HotkeyStopper, Arm the global stop combo once per process (idempotent). Called when the first…, Introspection for /health and /cu status: is the stop combo live?, Test/shutdown hook — retire the poller., Polls a key-combo (injectable for tests) and fires the emergency stop. On…, One poll cycle. Returns True if the stop fired on this poll., start_emergency_hotkey() (+6 more)

### Community 230 - "Docker GPU Sandbox"
Cohesion: 0.22
Nodes (8): _ensure_env_mask_file(), _nvidia_runtime(), Path, sandbox_run — Docker sandbox (bee-sandbox image, GPU passthrough optional). The…, Does this Docker setup have the nvidia runtime (GPU passthrough)? Docker…, An empty host file to bind over <workspace>/.env inside the container. Lives…, Host path as the docker CLI should receive it. Docker Desktop (Windows) accepts…, _to_container_path()

### Community 231 - "Event Bus Implementation"
Cohesion: 0.20
Nodes (5): BusEvent, match supports three key shapes: {"name": "device.memory_low"} the event name…, Publish; returns the number of handlers that ran. The proactive policy gate is…, kernel and automation buses must be thin facades over bee.events., test_one_implementation_two_facades()

### Community 232 - "Content Drafting Tool"
Cohesion: 0.39
Nodes (7): _deterministic(), draft(), _extract_fallback(), _llm(), /draft — emails, memos, outreach, proposals, reports + note extraction. Usage:…, -> (kind, body, tone). Kind = first word if it is a known kind., _split()

### Community 233 - "Local Speech Transcription"
Cohesion: 0.11
Nodes (13): available(), _once(), Local speech-to-text via faster-whisper (runs fully on-device; GPU optional).…, _trans(), ctx(), _Kernel, fixture, Web /voice route — regression pins (2026-10-17). Two real defects, both visible… (+5 more)

### Community 234 - "Isolated Test Environment"
Cohesion: 0.33
Nodes (4): env(), FakeClient, fixture, Isolated gate environment: baselines + models.yaml + diary in tmp.

### Community 235 - "Sub-Agent Spawning"
Cohesion: 0.33
Nodes (5): Sub-agents: spawn_task runs a bounded fresh loop with the same tools., Run a focused sub-task in a fresh context; returns its final answer. Acceptance…, spawn(), Acceptance audit P0-1: spawn_task's sub-context MUST inherit the parent's…, test_f1_spawn_subagent_inherits_capability_gate()

### Community 236 - "Device Event Bus"
Cohesion: 0.12
Nodes (11): DeviceSource, EventBus, _PollSource, Shared poll loop: run `scan()` on an interval, never crash the loop., Memory / disk pressure transitions — this machine's documented failure mode (a…, Synchronous in-process bus — a thin facade over the project's ONE shared…, A poller that outlives the worker is an orphan thread that keeps publishing…, A value oscillating on the threshold must not become a ping storm, and a… (+3 more)

### Community 237 - "MCP Server Config"
Cohesion: 0.29
Nodes (6): type, url, mcp, servers, $schema, graphify

### Community 240 - "Deterministic Memory Requests"
Cohesion: 0.43
Nodes (6): _as_recall(), MemoryRequest, parse(), Deterministic memory requests (Phase 3, Part C). 'Remember that my project is…, Remember my GPU from last time?' is a RECALL request. `_REMEMBER_RE` used to…, test_recall_phrasings_the_eval_uses_reach_the_deterministic_path()

### Community 241 - "Preference Data Export"
Cohesion: 0.60
Nodes (4): export(), main(), Path, Preference pairs -> train/prefs.jsonl (RLAIF stage 2: SFT imitates, preferences…

### Community 242 - "Grounded Fallback Logic"
Cohesion: 0.50
Nodes (4): _grounded_fallback(), What to ship when even the no-tools pass only talked about plumbing. The live…, plan_complex, live: the 'honest' fallback quoted the guard's own budget notice…, test_grounded_fallback_does_not_quote_a_refusal_as_evidence()

### Community 243 - "Startup Protocol Tests"
Cohesion: 0.33
Nodes (5): A53 — the Welcome Home protocol must only ever touch the windows it owns.…, A toast or another app's window appearing during the six-second wait must not…, test_a_failed_focus_does_not_launch_a_second_window(), test_a_foreign_new_window_is_never_dragged_onto_a_monitor(), test_the_browser_window_is_found_by_executable_not_by_what_appeared()

### Community 244 - "Scripted Client Verification"
Cohesion: 0.13
Nodes (9): ScriptedClient, _AnswersWhenToolsClosed, The real wrap pass calls chat(tools=None): the model can only answer., P0-4 (2026-10-17): a draft the verifier FAILED and the loop then fixed is a…, test_a_verify_fix_becomes_a_preference_pair(), chat() pops scripted items: str -> final answer; dict -> raw LLM out; Exception…, The call-order contract this suite depends on: a scripted stand-in that is not…, ScriptedClient (+1 more)

### Community 245 - "rollback_model"
Cohesion: 0.67
Nodes (3): Undo a promotion: remove local_model from models.yaml -> config.yaml wins again., rollback_model(), test_rollback_removes_override()

## Knowledge Gaps
- **330 isolated node(s):** `CloudCfg`, `GuardCfg`, `MonitorCfg`, `OllamaCfg`, `PrivacyCfg` (+325 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **28 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `load_config()` connect `Model Benchmarking Tools` to `Logging and Notifications`, `Command System Tests`, `Voice Engine Mocks`, `Self-Critique Gate`, `Desktop Risk Audit`, `ML Router Reporting`, `Hybrid Routing Logic`, `Memory Recall Tests`, `Hybrid Task Routing`, `Web Application Endpoints`, `Kernel Integration Tests`, `System Configuration`, `Engine Selection Context`, `Modular Slash Commands`, `Telemetry Data Integrity`, `Filesystem Security Tools`, `Self-Reflection Loop`, `Desktop Abstraction Layer`, `Skill Gate Index`, `Planner Logic Regressions`, `Deterministic Verification Suite`, `Workspace Startup Protocol`, `SFT Data Augmentation`, `Hardware Event Sources`, `Schedule Trigger Math`, `Proactive Action Policy`, `Automation Test Utilities`, `Routing Threshold Configuration`, `Tool Effect Verification`, `Voice Agent Adapters`, `Tool Execution Regressions`, `Docker Sandbox Security`, `Post-Answer Verification`, `Context Assembly Logic`, `Planner Integration Tests`, `Prompt Injection Guard`, `Hardware Recall Tests`, `Capability Authorization Tests`, `Evaluation Logic Regressions`, `Evaluation Suite Runner`, `Engine Routing Tests`, `Hybrid RAG Memory`, `Evaluation Hermeticity Tests`, `Typed Execution Planner`, `Global Emergency Hotkey`, `SFT Eligibility Filter`, `Sub-Agent Spawning`, `Device Event Bus`, `Router Training Metadata`, `Tiered Routing Logic`, `Agent Core Loop`, `Scripted Client Verification`, `Action Claim Correction`, `Agent Execution Results`?**
  _High betweenness centrality (0.139) - this node is a cross-community bridge._
- **Why does `Context` connect `Context Assembly Logic` to `Command System Tests`, `Voice Engine Mocks`, `Desktop Risk Audit`, `Hybrid Routing Logic`, `Memory Recall Tests`, `Model Benchmarking Tools`, `Web Application Endpoints`, `Kernel Integration Tests`, `Engine Selection Context`, `Telemetry Data Integrity`, `Self-Reflection Loop`, `Planner Logic Regressions`, `Prompt History Budgeting`, `Automation Test Utilities`, `Tool Effect Verification`, `Voice Agent Adapters`, `Tool Execution Regressions`, `Post-Answer Verification`, `Planner Integration Tests`, `Prompt Injection Guard`, `Hardware Recall Tests`, `Capability Authorization Tests`, `Evaluation Suite Runner`, `Engine Routing Tests`, `Typed Execution Planner`, `SFT Eligibility Filter`, `Sub-Agent Spawning`, `Agent Core Loop`, `Scripted Client Verification`, `Action Claim Correction`, `Agent Execution Results`?**
  _High betweenness centrality (0.031) - this node is a cross-community bridge._
- **Why does `AgentKernel` connect `Agent Kernel Implementation` to `Voice Engine Mocks`, `Desktop Risk Audit`, `Memory Recall Tests`, `Tool Dispatch Bus`, `Web Application Endpoints`, `Kernel Integration Tests`, `Kernel Event Bus`, `Engine Selection Context`, `Telemetry Data Integrity`, `Job Scheduling Adapter`, `Training Pipeline Scheduler`, `Self-Reflection Loop`, `Isolated Eval Environment`, `Execution Receipt Logging`, `Automation Test Utilities`, `Permission Risk Layer`, `Tool Effect Verification`, `Voice Agent Adapters`, `Tool Execution Regressions`, `Post-Answer Verification`, `Planner Integration Tests`, `Hardware Recall Tests`, `Evaluation Suite Runner`, `Evaluation Hermeticity Tests`, `Typed Execution Planner`, `Agent Session State`, `Action Claim Correction`, `Structured Retry Policy`, `Agent Kernel Runtime`?**
  _High betweenness centrality (0.030) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `run_agent()` (e.g. with `LLMError` and `Context`) actually correct?**
  _`run_agent()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 16 inferred relationships involving `AgentKernel` (e.g. with `EventBus` and `MemoryStack`) actually correct?**
  _`AgentKernel` has 16 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `Context` (e.g. with `run_agent()` and `ctx()`) actually correct?**
  _`Context` has 4 INFERRED edges - model-reasoned connections that need verification._
- **What connects `CloudCfg`, `GuardCfg`, `MonitorCfg` to the rest of the system?**
  _330 weakly-connected nodes found - possible documentation gaps or missing edges._