# BEE — a local-first personal assistant

> **Status (re-measured on this machine 2026-10-15):** BEE is a well-tested
> single-user personal agent for human-supervised deployment on this machine —
> **928/928 tests green**, 71,914 deterministic checks passing, all major
> security invariants audit-verified, **20/21** on the 21-task agent eval (one
> invocation, `skipped: 0`, `single_run: true` — the only failure is answer quality
> on the local 3B model). A
> post-audit code sweep has fixed defect classes the suite had been certifying as
> clean (dead config switches, an unarmed emergency-stop hotkey, silent TTS
> playback, a frozen face page, no logging handler at all, a session rule that
> hijacked the deterministic tier, reminders that fired into a log instead of the
> desktop, a dashboard that could not show live data, permission prompts that
> asked the user to approve invisible actions, a semantic-memory call that had
> never returned anything, memory that stayed unfindable for 12 hours after a
> fact was stated — and the assistant's own logs being indexed as memory, so it
> recalled past failures instead of the user's facts, answers claiming actions that never ran,
> hallucinated skills written into the capability library, a test suite writing
> into the user's own telemetry and memory, no way for the assistant to name the
> hardware it runs on, durable memory that duplicated and contradicted itself,
> and 40-second tasks whose final answer was an offer to help, a loop that let one
> task burn 48 tool calls on code that kept failing, and pasted code the assistant
> described instead of running, and a loop whose own `do not repeat this` note was
> returned as a success — so one task asked for the same refused call 21 times in a row
> — plus, in the 2026-10-13→15 pass, a shipped context window that was half the size of
> a real agent turn, a test harness still writing the user's training corpus and score
> ledger, and an eval headline that counted tasks which never ran as passes — see
> `docs/TECHNICAL_DEBT.md` rows A1–A64).
> It is **not** multi-user, **not** "production-ready" in the service sense, and its
> hardware paths (real mic/display/LiveKit room) are test-verified only with mocks.
> Authoritative status: [docs/STATUS.md](docs/STATUS.md) · evidence:
> [docs/JARVIS_ACCEPTANCE_AUDIT.md](docs/JARVIS_ACCEPTANCE_AUDIT.md)

**BEE** is an all-in-one executive and personal assistant that lives on **your**
machine. It plans your day, drafts your writing, summarizes anything, writes and
debugs code, stress-tests your decisions, and executes technical work through a
hybrid local + cloud brain.

Measured on a Windows desktop (RTX 3050 4 GB · 16 GB RAM): local **bee4b** (Qwen2.5-3B + BEE
persona, ~50–90 tok/s, fully on-GPU) orchestrates by default; hard tasks escalate to a
**cloud model** (~1.2 s/call, verified); math — even phrased "what is 17*23?" — is answered by a
**deterministic tier with no LLM at all**; everything degrades gracefully when offline.

```
┌────────────────────────────────────────────────────────────────────┐
 │  Interfaces:  CLI REPL · Web UI (localhost) · Voice (speak directly)│
│  Commands:    /plan /draft /summarize /code /think /remind + /engine, /tts │
├────────────────────────────────────────────────────────────────────┤
│  Agent loop: route → think → act → observe (≤25 iters) → verify    │
│  routing: det > explicit > smalltalk > fast-paths > ML > heuristic  │
│  + escalation · guard rails · PII redaction · offline fallback     │
├─────────────────────────────────┬──────────────────────────────────┤
 │  30 tools (file, shell, sandbox,│  Memory (plain Markdown, yours)  │
│  calc, web, memory, skills,     │  diary/ · lessons/ · profile.md  │
│  planner, scheduler, …)         │  vectors/ (LanceDB) · RAG hybrid │
├─────────────────────────────────┴──────────────────────────────────┤
│  Models: Ollama (bee4b, nomic-embed) · LiteLLM cloud tier          │
│  + offline deterministic engine (math/sort/files/clock)            │
└────────────────────────────────────────────────────────────────────┘
```

---

## 1. Persona & communication

BEE is configured (in `bee/agent/context.py` → `build_system_prompt`) to be **sharp,
organized, proactive, direct, warm, and energetic**:

- begins with useful output — no greetings, pleasantries, filler, or robotic setup
- structured, action-oriented replies: answer/verdict first, then supporting detail
- zero fluff: every sentence must carry information
- proactive: surfaces the next step, the main risk, and one recommended action
- errors: states what failed, why, and the exact next step — never fakes success

All commands (`/plan`, `/draft`, …) follow the same contract: **LLM-driven when a model is
reachable, deterministic floor otherwise, and never an unhandled crash** — failures return a
clear `ERROR: …` line with the reason and the fix.

---

## 2. Prerequisites

| Requirement | Minimum | This build's machine |
|---|---|---|
| OS | Windows 10/11 (tested), Linux/macOS (core runs) | Windows 10, x64 |
| Python | 3.10+ | 3.11 |
| RAM | 8 GB (16 GB recommended — bee4b needs only ~1.9 GB VRAM) | 15.6 GB |
| GPU | any NVIDIA 4 GB+ VRAM for bee4b (CPU works, ~1 tok/s) | RTX 3050 4 GB |
| Ollama | latest Windows build | installed |
| Disk | ~10 GB free (models + deps) | 6+ GB kept free |
| Optional: Docker Desktop | for the ML/DL sandbox | optional |
| Optional: cloud API key | one key enables the escalation tier | Gemini (verified) |

---

## 3. Installation

```powershell
# clone / open the project folder, then:
cd C:\path\to\PA

# one-shot: Ollama models + pip deps + optional sandbox image + env check
powershell -ExecutionPolicy Bypass -File setup.ps1

# or step by step:
ollama pull qwen2.5:3b
ollama create bee4b -f models\bee4b.Modelfile   # BEE persona + speed params
ollama pull nomic-embed-text
python -m pip install -r requirements.txt
python -m pip install -r requirements-voice.txt        # STT/TTS (optional)
docker build -t bee-sandbox:latest .\sandbox           # optional: ML/DL sandbox

# verify everything, then launch
python -m bee.cli doctor     # read-only system report; exit 0 = healthy
python -m bee.cli setup
python -m bee.cli
```

---

## 4. Secure configuration

**Secrets live in user-scope environment variables only — never in `config.yaml`
(synced to OneDrive) and never in code or prompts.**

```powershell
# pick ONE cloud provider (provider prefix must match cloud.llm):
$env:GOOGLE_API_KEY  = "AIza…\"        # → cloud.llm: \"gemini/gemini-3.6-flash\"
$env:XAI_API_KEY     = "xai-…"        # → cloud.llm: "xai/grok-2-latest"
$env:OPENAI_API_KEY  = "sk-…"         # → cloud.llm: "openai/gpt-4o-mini"
$env:OPENROUTER_API_KEY = "sk-or-…"   # → cloud.llm: "openrouter/<vendor>/<model>"

# optional: higher-quality TTS voice (edge-tts)
$env:EDGE_TTS_KEY = "your-azure-key"
```

BEE matches the key to the model's provider automatically (`bee/config.py →
_env_key_for`) — a Gemini model will never receive an OpenAI key.

`config.yaml` (no secrets):

| Key | Default | Meaning |
|---|---|---|
| `ollama.model` | `bee4b` | local orchestrator (Qwen2.5-3B + BEE persona) |
| `ollama.max_tokens` | `1024` | per-turn ceiling (this box: ~50–90 tok/s → snappy turns) |
| `ollama.num_ctx` | `8192` | context window — **pinned by a measured floor**, not a round number: the largest turn the 21-task eval builds is 7339 tokens and 8192 is the biggest window that stays fully resident on this 4 GB card (A59). Below that Ollama silently evaluates `num_ctx / 2` |
| `ollama.keep_alive` | `"60s"` | unload the local model 60 s after last use (`""` = Ollama's own 5 min). Sent in `extra_body` — litellm has no `keep_alive` parameter (A58) |
| `ollama.autostart` | `true` | bring up Ollama itself at boot (A60a) when it is not already reachable; a server you started is never touched, and a failed launch shows up as a reason on the health page instead of a degraded silent turn |
| `cloud.enabled` / `cloud.llm` | `true` / `gemini/gemini-3.6-flash` | escalation tier (`provider/model`) |
| `voice.speak` | `true` | speak answers aloud (REPL: `/tts on\|off`) |
| `voice.tts_rate` | `190` | TTS speed, words/minute (REPL: `/tts rate <n>`) |
| `voice.tts_voice` | `""` | TTS voice: `""` = system default, else name substring, e.g. `aria` (SAPI) or `en-US-AriaNeural` (edge-tts). List with `/tts voices` |
| `voice.edge_key` | `""` | optional Azure key for edge-tts |
| `voice.wake_word` | `bee` | voice-mode trigger |
| `guard.mode` | `cli` | `cli` prompt / `unattended` auto-deny / `always` (unsafe) |
| `privacy.redact_cloud` | `true` | PII redaction on cloud-bound payloads (local is never redacted) |
| `router.ml_enabled` / `ml_min_episodes` | `true` / `150` | learned ML router activation |
| `rag.auto_context` / `k` | `true` / `4` | memory auto-injection for dangling references |
| `monitor.enabled` | `true` | metrics stream + dashboard (false = stream off) |
| `automation.events_enabled` | `true` | proactive **event sources**: heartbeat + battery (Windows power API) + network (TCP probe, no DNS); `file_watch_dir` opts in file-change. Events never act without a user-authorized rule |
| `automation.battery_low_percent` | `20` | `battery.low` fires at/below this while unplugged (edge-triggered, one alert per crossing) |
| `livekit.enabled` / `room` | `true` / `bee-pa` | live realtime voice (see §6.5); the `url`/`api_key`/`api_secret` come from `.env` |
| `user.name` / `timezone` / `region` / `interests` | `Boss` / `Asia/Calcutta` / `IN` / `[]` | the "Who I serve" personalization block injected into every prompt |

`models.yaml` is the model registry (local/cloud/future fine-tunes).
`BEE_WORKSPACE` env var relocates the workspace root.

---

## 5. Using BEE — text

```powershell
python -m bee.cli        # REPL
.\bee-runfull.ps1        # ALL at once: web UI + Live Voice (browser) + text REPL
```

**Full stack in one command.** `\bee-runfull.ps1` (or `python -m bee.cli full`) starts everything: the web server (chat UI, /face, Live Voice join), the LiveKit voice agent, opens the browser on the Live Voice page, and runs the text REPL in your console (`/voice` PTT still works inside it). `/exit` tears the child processes down; their logs land in `temp/bee-full-*.log`.

```text
you> /plan daily                 # today's time-boxed itinerary
you> /plan add "Pay client invoice" due 2026-10-06 P1
you> /draft email launch slips a week [tone: apologetic]
you> /summarize https://…        # article → TL;DR + bullets + table
you> /code bash rotate log files # production-grade script + tests
you> /think alternatives ship the telegram bot
you> cloud: write the Q4 forecast memo     # force cloud model for one task
you> 12 * (3 + 4)                  # deterministic tier — no LLM, instant, exact
you> hi                            # smalltalk tier — instant canned reply, no model
you> what time is it               # fast path — pure Python, no LLM
you> open chrome                   # fast path — one guard-checked shell call
you> 100 celsius to fahrenheit     # fast path — instant conversion
you> weather in delhi              # fast path — wttr.in fetch, no LLM
you> todo: ship the beta by friday # fast path — straight into the /plan store
you> how is the pc                 # fast path — CPU/RAM/disk/battery in one WMI round-trip
you> next track                    # fast path — system media keys (works with any player)
you> lock my pc                    # fast path — guard-checked, one confirmation
you> what is a transformer         # fast path — Wikipedia REST summary, no LLM
```

**Fast paths** (`bee/agent/fastpaths.py`) are a catalog of 46 pure-Python handlers
for the things a PA is asked most: time/date/uptime, open `<app>` (chrome, notepad,
excel, vscode, …), open `<workspace file>`, search/google `<q>`, weather, unit +
temperature conversions, coin/dice/random/pick, note, todo, CPU/RAM/disk/battery stats,
machine specs (GPU/CPU/RAM model, read from the box), workspace folder listings,
run-this-pasted-code (`run python: …` executes it),
spoken `/remind`, public IP, identity, "what's on my plate" (plan list), speak, **and** the JARVIS-port
set (see §7): wikipedia, play/youtube, media keys, volume, brightness, lock, sleep,
show-desktop, take-a-photo, welcome-home. All answer in milliseconds with zero
LLM calls; anything action-y still passes through the **guard** (a fast path can never
bypass permissions); handlers decline (return `None`) when a network call fails, and the
normal model pipeline takes over. Adding one is ~5 lines (registry at the bottom of the
file).

**Choosing the brain at launch.** First start asks once (persisted to `settings.json`):
`hybrid` (default) · `local` (offline, ~50–90 tok/s) · `ollama-cloud`
(`glm-5.2:cloud` — fast, remote, via your Ollama login) · `api-cloud` (Gemini API —
fastest). Switch any time with `/engine`; a per-task `cloud:`/`local:` prefix always
wins for that one task.

**Hybrid is cloud-first by default (speed + memory).** On a RAM-tight box, loading
the local model for every conversational turn adds first-token latency. So in
`hybrid` mode substantive chat/QA is answered by the fast cloud model **first**
(`cloud.cloud_first: true`), with automatic fallback to local when the cloud is down —
and vice-versa escalation (local→cloud) on quality failure. Explicit `local:`/`use
local` and `engine: local` always force the local model. Set `cloud_first: false` for the
classic local-first hybrid. The local model is also released from RAM/VRAM
`ollama.keep_alive` (60 s) after its last use, and `num_ctx` is **8192** — the largest
window that keeps bee4b fully on the 4 GB GPU *and* holds a whole real agent turn
(measured: the biggest turn the 21-task eval builds is 7339 tokens; at 4096 Ollama
evaluated 2050 of 5779 silently — see `docs/TECHNICAL_DEBT.md` A58/A59).

**The local brain: bee4b.** A custom Ollama model built from **Qwen2.5-3B** with the BEE
persona baked in (`models/bee4b.Modelfile`). Sizing rationale for this 4 GB card, all
measured: Qwen2.5 has no 4B (lineup jumps 3B → 7B); `qwen3:4b` is a *thinking* model that
narrates its reasoning in-content and exhausts the token budget before answering (even
"reply OK" → "Hmm, the user wants…") — unusable for a fast PA; `qwen3:8b` (~5 GB)
CPU-offloads on this card → ~4.6 tok/s. Qwen2.5-3B sits at ~1.9 GB of weights, runs 100 %
on-GPU even at `num_ctx: 8192` (A59 measured `size_vram` 2.31 GB — weights *plus* KV
cache — on this 4 GB card), and measured **~50–90 tok/s** with crisp, direct answers (at
the earlier 4096 window; what moving to 8192 bought is whole-turn prompts and 70 → 46
model calls per eval, A59).
Rebuild it any time: `ollama create bee4b -f models\bee4b.Modelfile`.

**Math never touches the model.** The deterministic tier (`bee/agent/router.py: math_expr`)
catches pure expressions, lightly-phrased asks ("what is 17*23?", "calculate 10% of 200",
"5 plus 5", "6 to the power of 2", "17 × 23") **and prose-wrapped ones** — "Use the
calculator tool to compute 12 * 14 + 8 and give the final number." is answered in 0.02 s.
The prose path (`_embedded_expr`) only fires when a compute-intent verb is present and the
leftover words are pure math, verified by AST against `eval_safe`'s allowlist, so text that
carries a second request ("…and explain the steps", "…email it to bob") or injection-shaped
payloads declines and goes to the model. A 3B model given that same sentence told the user
"none of the provided functions are for a calculator". It wins over explicit engine overrides by design: a model should
never be the calculator (one 3B model answered 17×23 = 401; the tier answers 391).

Every command works offline (deterministic floor) and persists its output:
itineraries → `plans/`, drafts → `drafts/`, summaries → `sums/`, code → `codeout/`,
thoughts → `thoughts/`.

---

## 6. Using BEE — voice

```powershell
python -m bee.cli voice      # or /voice inside the REPL
```

**Speak your task directly** — e.g. "what's on my plate today?" (saying "bee" first also
works; it's stripped, not required). Local faster-whisper STT (audio never leaves the
machine) → agent → **TTS reply**. The speech model warms up when voice mode starts (first
run downloads ~150 MB, progress is printed). Very short utterances ("hi", "yes") are
re-transcribed without VAD so they are never silently dropped.

TTS controls (session; `config.yaml voice:` to persist):

```text
you> /tts               # status: on/off · rate · voice · backends
you> /tts off           # mute voice output (text continues)
you> /tts rate 160      # slow down (80–300 wpm)
you> /tts voice aria    # pick a SAPI voice by substring
you> /tts voices        # list installed voices + edge-tts ids
you> /tts test          # spoken self-check
you> /speak hello       # one-off TTS test
```

Backends: **pyttsx3** (offline, SAPI5) first; **edge-tts** (network, neural voices) when
`voice.edge_key` is set.

---

## 6.5 Live voice (real-time) & the face

BEE can talk to you in real time — not "record, then answer", but a live two-way
conversation — with a full-screen **face** that idles / listens / thinks / speaks in
sync. The transport is **LiveKit Cloud's free tier** (~1000 agent-minutes/month,
WebRTC); **all the intelligence and all the audio models stay local and free**:

```
 mic ──▶ silero VAD (local) ──▶ BeeSTT (faster-whisper, local)
      ──▶ BEE brain   (the FULL pipeline: fast paths → engine routing →
                 tools + guard → persona → memory)
      ──▶ BeeTTS (edge-tts neural MP3 / pyttsx3 offline WAV) ──▶ speakers
```

**Start it (two ways):**

```powershell
# the "Talk" one-shot: web server + voice agent + browser (face + join) in one go
.\start_talk.ps1

# …or by hand, two terminals:
python -m bee.cli livekit --room bee-pa   # terminal 1: the voice agent
python -m bee.cli web                     # terminal 2: serves /livekit + /face
```

Then in the browser: **Live Voice** (`/livekit`) → *Join* → enable the mic → talk;
**the face** (`/face`) shows the sync visualizer (press **F** to full-screen).
Stop with **Ctrl-C** in the agent terminal.

**Secrets** live in `.env` (never `config.yaml`): `LIVEKIT_URL`, `LIVEKIT_API_KEY`,
`LIVEKIT_API_SECRET`. The web server mints a 2-hour participant JWT per join
(`POST /livekit/token`); room names are validated to `^[A-Za-z0-9][A-Za-z0-9-]{0,63}$`.
Destructive actions run under the guard in `unattended` mode during a live call
(auto-deny, never a blocking prompt). Dependencies: `requirements-livekit.txt`
(livekit-agents pinned to 1.4.6 for a stable STT/TTS plugin surface).

### Where fullstack-agent fits

This mirrors Jared Rhodenizer's [fullstack-agent](https://github.com/jaredrhod/fullstack-agent)
— "an agent that HAS a full stack: memory, voice, and face" — with each piece mapped to BEE:

| fullstack-agent piece | BEE equivalent | Notes |
|---|---|---|
| **The mind** — ai-memory-vault | `memory/` (diary · lessons · profile · longterm) + `vectors/` (LanceDB) + RAG | BEE's vault is larger: hybrid vector+keyword search, nightly consolidation, SFT flywheel |
| **The mouth** — backtalk (hold-to-talk) | **Live voice (LiveKit)** + `/voice` (PTT) | LiveKit is real-time duplex — a step beyond backtalk's hold-to-talk |
| **The face** — ai-visualizer | `/face` (idle/listen/think/speak visualizer) | synced to live-voice state via a cross-process bridge (temp-file JSON) |
| **The hands** — barehands (webcam hand tracking) | *not ported* | an optional extra needing webcam + ~1 GB MediaPipe — deliberately left off this RAM-tight box |

**Personalization is first-class.** The system prompt carries a "Who I serve" block
(name, timezone, interests) from `config.yaml → user:`, so BEE addresses you by name and
reasons in your local time everywhere — REPL, web, voice, and live.

---

## 7. System & workspace control (Super JARVIS integration)

BEE integrates the Super JARVIS feature set: hands-free PC control, the "Welcome Home"
startup protocol, and an acoustic **double-clap** trigger — implemented with pure Windows
APIs (`ctypes` keybd_event / powrprof / WMI) instead of pyautogui/psutil, so there is
zero extra dependency cost on this RAM-tight box.

**App & URL accessibility — deterministic, instant.** "Open something" never waits for
the model: a fastpath layer (`bee/agent/fastpaths.py` — part of the 46-handler catalog)
resolves these with no model call —
`chrome`/`edge` **including browser profiles** ("open chrome and select user 1" →
`chrome --profile-directory="Profile 1"`), installed apps (terminal, vscode, spotify,
zoom, slack, task manager, settings, Microsoft Store), the Windows **Camera** and Photos
apps, and web apps (whatsapp → web.whatsapp.com, telegram, gmail, maps, grok, youtube) —
plus bare domains and full URLs ("open grok.com", "open https://example.com/x?y=1") and
inverted phrasing ("camera launch"). Every launch still runs through the guard, so a
fastpath can never bypass permissions. Web research is keyless and resilient too:
`web_search` chains **DuckDuckGo HTML → Bing → Wikipedia opensearch** (probed live from
this network in Oct 2026 — the old DDG API/lite endpoints are blocked here, which is why
search used to return "endpoints unreachable"), then `web_fetch` cleans the chosen page
into text.

### Native performance layer (polyglot by design)

BEE uses the best language for each job. The heavy lifting already runs on **native**
code under the Python orchestration: **LanceDB** (Rust/C++) for vector memory,
**Ollama** (Go + C++ llama.cpp) for the local LLM, **CTranslate2** (C++) for
faster-whisper STT, **silero** (C++) VAD, **PyAV** (C) for media. On top of that, a
new **Go telemetry daemon** (`bee/native/`) — standard-library only, compiled to a
~9 MB self-contained `.exe` — replaces the old per-call PowerShell/WMI system-stats
round-trip (~500 ms under load) with a resident localhost HTTP endpoint read in
**~1 ms** (connection-pooled). BEE starts it in the background at launch and silently
falls back to the WMI path if it's unavailable — a pure speed-up with no regression.

```powershell
# (re)build the native daemon:
powershell -ExecutionPolicy Bypass -File bee\native\build.ps1
```

**Instant PC control** — type in the REPL or say in voice mode (fast paths: no LLM):

| Say / type | What happens |
|---|---|
| `how is the pc` · `system status` | CPU % + free RAM + C: free + battery — one WMI round-trip |
| `how much is the battery` | battery % + AC/on-battery state |
| `volume up` / `down` / `max` · `mute` / `unmute` | system volume keys |
| `next track` · `previous track` · `pause the music` · `resume the music` | system media keys — works with Spotify or any player |
| `play <song>` · `youtube <q>` | YouTube search in the browser (Spotify API is a possible upgrade) |
| `set brightness to 80` | screen brightness via WMI (internal displays) |
| `show desktop` · `minimize all windows` | Win+D |
| `lock my pc` | lock the workstation — **guard asks first** |
| `put my pc to sleep` | sleep via the power API — **guard asks first** |
| `take a photo` | webcam snapshot + face count → `snapshots/` (optional: `pip install -r requirements-vision.txt`) |
| `what is <topic>` · `wikipedia <topic>` | one-paragraph Wikipedia summary via REST API; offline → declines to the model |

**Welcome Home protocol** — `/welcome`, say "welcome home", or double-clap (this box's
defaults: **aistudio.google.com** + **grok.com**, focus **Accio Work**):
welcome song (optional `welcome.song_uri`) → each `welcome.urls` entry opens in a **fresh
Chrome window** snapped to its monitor (fullscreen optional, F11) → spoken greeting →
the configured app **focused or launched — never cloned** (matched by real process
executable `welcome.ide_exes`, largest main window; launch target `welcome.ide_path`,
falls back to Cursor/VS Code). `/welcome dry` previews the plan; `/welcome reset`
clears the retrigger guard (default 60 s anti-spam window).

**Double-clap trigger** — `python -m bee.cli clap`:
mic stream at 44.1 kHz with adaptive noise floor (alpha 0.992), hysteresis retrigger
(sustained loud audio never counts as repeated claps), 1.5 s calibration warmup,
double = two claps 60–400 ms apart, 1.5 s cooldown after a trigger.
`clap.action` (config.yaml): `welcome` (default) or `voice` (records one utterance and
runs it as a normal task).

**Guard treatment:** `systemctl` is an execution tool — `lock`/`sleep` always ask for
confirmation (`guard.mode: cli` prompts; `unattended` auto-denies), the rest classify as
allow. Fast paths that act return `FastExec` and run through the **same guard** as LLM
tool calls — a fast path can never bypass permissions.

---

## 8. Command reference

**Assistant commands** (modular — each is one file in `bee/commands/`):

| Command | What it does |
|---|---|
| `/plan` | Daily/weekly/monthly itineraries with **time-boxing** (P1 45′, P2 30′, P3 20′, P4 15′; breaks 12:30–14:00, 16:00–16:15) and the **Eisenhower matrix** (P1 urgent+important … P4 neither). Task store with deadlines, priorities, dependencies, status: `/plan add <title> [due YYYY-MM-DD] [P1..P4] [needs a,b]` · `/plan list` · `/plan done t1 t2` · `/plan weekly` · `/plan monthly` · `/plan clear-done` |
| `/draft <kind>` | `email` · `memo` · `outreach` · `proposal` · `report` in the requested `[tone: …]`; `extract` pulls **key decisions, action items, owners, follow-ups** from messy notes/transcripts |
| `/summarize` | URL, local file, or pasted text → **TL;DR + high-density bullets + comparative Markdown table** of figures |
| `/code` | `[python\|bash\|js\|ts] <task>` → production-grade code (typed, validated, error-handled, commented) **with tests**; `debug <code + error>` → root cause, evidence, fix, regression test |
| `/think` | Stress-test an idea: verdict, kill criteria, pre-mortem, trade-off table, pros/cons matrix, recommendation; `alternatives` adds 3+ strategic paths |
| `/remind` | **Durable reminders** on the one job store: `/remind call the bank tomorrow 9am` · `/remind list` · `/remind cancel <id\|last\|all>`. Time words are parsed deterministically (`in 20 min`, `tonight`, `friday 4pm`, `12 Oct 07:30`, `day after tomorrow at 11:30`), so **no model call is needed to set one and none is needed to fire it** — it survives restarts, is repaired by `worker.restore()`, and arrives as a desktop toast. Say it instead of typing it: *"remind me to stretch in 20 min"*, *"what are my reminders?"*, *"cancel all my reminders"* all take the instant fast path (§6) |
| `/welcome [dry\|reset]` | **Welcome Home** workspace protocol: song → configured Chrome windows on their monitors → spoken greeting → IDE focus (see §7) |

**System commands** (REPL):

| Command | What it does |
|---|---|
| `/help` | this reference (generated from the registry) |
| `/voice` | voice command mode (wake word: `bee`) |
| `/tts …` | TTS controls (see §6) |
| `/model [local\|cloud\|name]` | view/override the session model |
| `/tools` · `/skills` | list agent tools / skill cards |
| `/mem <query>` | hybrid vector+keyword memory search |
| `/reflect` · `/consolidate` | run self-review / nightly consolidation now |
| `/eval` | run the 21-task agent eval suite |
| `/health` · `/dashboard` | environment report / metrics dashboard **snapshot** (the web app serves the same page **live** at `GET /dashboard?token=…`, refreshing every 30 s) |
| `/doctor` | deep read-only report — config precedence, guard + capability-gate status, Ollama reachability + `bee4b`/`nomic-embed-text` presence, memory index age + dirty queue, disk, last eval summary. CLI: `python -m bee.cli doctor` (exit 0 healthy · 1 no local core · 2 broken config; never prints keys) |
| `/router` | learned-ML-router training status |
| `/guard on\|off` · `/privacy on\|off` · `/rag on\|off` | session safety toggles |
| `/clear` · `/exit` | screen / quit |
| `cloud: <task>` | force the cloud model for one task |

---

## 9. Hybrid intelligence (how it routes and verifies)

One facade owns the decision — `bee/agent/router.py:decide()` is the single routing
entry the loop calls. First hit wins:

| Stage | Trigger | Result |
|---|---|---|
| 0 deterministic | math incl. phrased ("what is 17*23?", "10% of 200", "5 plus 5") | `eval_safe` — **no LLM** (0 ms, offline) |
| 1 explicit | `cloud:` / `local:` prefix, `/model`, "use local/cloud", image → vision | as requested |
| 2 smalltalk | greetings / thanks / bye | canned reply — no model call |
| 3 fast-path | time, open app/URL/profile, search, weather, conversions, todo, creator identity, … | pure-Python handlers — **no LLM** (0 ms, offline where possible) |
| 4 learned ML | TF-IDF + logistic regression over BEE's own episodes | votes only above 0.70 confidence after 150 labeled episodes; shadow-logged |
| 5 heuristic | length + task cues (prove / multi-phase / long-form …) | local default → cloud when complex |
| 6 escalate | hybrid cloud-first (session engine) + local runtime failure (overload, bad tool call, retries out) | cloud auto-escalation with re-prompt |
| offline | both models unreachable | deterministic rules: math, sort, file listing, clock, identity |

Escalation runs in the loop right after `decide()` because it needs live service
probes; the order is pinned end to end by `tests/test_routing_order.py`.

**Verification, not vibes:** after every answer, `bee/brain/verifier.py` recomputes
calculator claims, re-reads written files, and cross-checks cited URLs — one bounded fix
round on failure. URLs a tool actually **opened** in the browser satisfy the citation
check (an action is not a fabrication). `bee/privacy.py` redacts PII from **cloud-bound**
payloads only (local = privacy floor; every redaction counted in metrics).
`bee/guard.py` classifies every shell/code/sandbox call as allow | ask | deny and is
**enforced in the loop** — the model cannot bypass it. Three circuit breakers keep a
small model from thrashing: identical-failure, identical-call caching, and **per-tool**
refusal/failure counting (a tool denied 2x or failed 3x is short-circuited without even
consulting the gate, and 3 refusals lock the toolset so the budget goes to an honest answer).

**Loop discipline (anti-runaway, small-model safe):** the agent loop enforces
three circuit breakers — a call that *fails twice with identical arguments* is not executed a
third time, a call *re-issued identically* gets the cached result back with a nudge
to finish, and **refusals are counted per tool**: a capability already denied twice
is no longer even consulted, and three refusals in a row lock the toolset so the
remaining budget goes to an honest answer. A 3B model once re-ran the same `web_search` 20×,
and asked for one denied capability 6× with slightly varied arguments (which slipped past
the exact-arguments breakers) — neither can happen now. The `/eval` suite is cancel-poisoning-proof too: a Ctrl-C from a previous
task can no longer silently cancel every remaining eval task (the event is cleared per
task and a user cancel stops the suite cleanly).

**BEE knows itself:** creator ("who made you?" → the human from `user.name`), origin,
and what it can do are deterministic fastpaths — the model never has to guess its own
biography, and the system prompt carries the "act, don't refuse" rule for action tasks.

**Self-improvement loops:** diary (every task) → reflection/lessons (**only for
non-trivial tasks** — tool use, failures, escalations; greetings and one-shot answers
skip it to save a model call) → **teach-back** (every successful *cloud* answer is
stored to `train/golden/cloud_golden.jsonl`; nightly, the best ones are distilled into
`skills/cloud-<topic>/SKILL.md`, and all successful episodes feed the SFT pipeline, so
the local model learns from what the cloud did well) → skills (novel successes distilled
to `skills/<name>/SKILL.md`) → nightly consolidation (03:00, diary → `longterm.md`) →
**episodes** (full trajectories as SFT-ready JSONL) → **ML router auto-retrains itself**
on startup and nightly once ≥ 150 labeled episodes exist (`maybe_train_router`) →
eval gate (`evals/`) → optional QLoRA fine-tune into a dedicated `bee-8b`
(`training/qlora/`, `docs/llm-component.md`, `docs/training-plan.md`).
Every layer is plain Markdown or JSONL you can read, edit, or delete.

---

## 10. Development workflow

Layout:

```
bee/
  cli.py · __main__.py     REPL/voice/web/plan/speak/eval/setup entry points
  config.py · paths.py     config + canonical paths
  privacy.py · guard.py    PII redaction · execution gates
  commands/                ★ modular slash-commands (registry + 7 commands)
  agent/                   loop · client · router · offline · context · reflection · spawn
  brain/                   verifier · rag (RRF hybrid) · mlrouter (learned)
  tools/                   30 tools (registry: tools/__init__.py)
  memory/ · episodes/      markdown memory + hybrid search · SFT trajectory capture
  pipeline/                validate → sanitize → build SFT → train ML router
  monitor/                 metrics.jsonl stream · health · dashboard
  voice/                   mic · transcribe (whisper) · speak (TTS) · loop
  dsa/                     algorithm library + bench harness
  evals/                   21-task runner + model benchmark
 tests/                     68 pytest files / 928 tests (markers: core/security/windows/ml/voice/livekit)
training/qlora/            SFT/merge/export for the dedicated model
skills/ · evals/ · memory/ · train/ · metrics/ · docs/
config.yaml · models.yaml · requirements*.txt · setup.ps1
```

**Add a command (5 lines):**

```python
# bee/commands/myservice.py
from . import register

@register("myservice", "/myservice <arg>", "one-line description")
def myservice(ctx, arg: str) -> str:
    return "markdown output"
```

then add the module to the self-registration import at the bottom of
`bee/commands/__init__.py`. Contract: handler `(ctx, arg) -> str`, errors returned as
`ERROR: …` (never raised), one focused LLM call max, deterministic fallback required.
The REPL, `/help`, and any new surface (web/voice) pick it up automatically.

**Add a tool** → register in `bee/tools/`. **Add a skill** → `skills/<name>/SKILL.md`.
**Change the persona** → the `Persona — BEE` block in `bee/agent/context.py`.

---

## 11. Testing & verification

```powershell
python -m pytest tests -q                 # full suite — 928 passed, 0 failed (2026-10-15, 105.8 s)
python -m pytest tests -q -m core         # portable core (unit+integration) — 849 (79 deselected, see A64)
python -m pytest tests -q -m security     # permission/privacy surface — 135
python evals/verify_suite.py              # 71,914 deterministic checks vs references
python -m bee.cli eval                    # 21-task agent eval — 20/21 (2026-10-15, one run, 0 skipped)
python -m bee.evals.bench_model           # tok/s + latency benchmark
```

**Neither gate touches your real data** (A44 → A57 → A61): a scored run and a plain
`pytest` run both redirect memory, receipts/sessions/checkpoints, `audit.jsonl`,
telemetry, `train/` (episodes + the cloud-golden corpus), `evals/results.jsonl`,
`skills/` and the workspace into a temp copy — copied rather than emptied, so readers
still see your real content — and `tests/test_eval_hermeticity.py` hashes those trees
before/after a live run so the claim cannot rot silently. It could; it used to.

**Deterministic verification (no LLM, ~10 s).** Every deterministic subsystem is checked
against independent references with Wilson 95 % confidence intervals. A perfect run with
n ≥ ~3,900 has a CI lower bound ≥ 99.9 % — the honest, measurable form of the 99.9 %+
target. Latest measured run (this machine, seed 20261004):

| Suite | n | accuracy | 95 % CI lower |
|---|---:|---:|---:|
| math (`eval_safe` vs independent values) | 10,000 | 100.000 % | **99.962 %** |
| dsa (sorts/DP/graphs/structures vs references) | 38,456 | 100.000 % | **99.990 %** |
| pii (detection + redaction, Luhn-aware) | 13,200 | 100.000 % | **99.971 %** |
| guard (allow/ask/deny commands) | 4,204 | 100.000 % | **99.909 %** |
| router (4-tier logic) | 6,000 | 100.000 % | **99.936 %** |
| rag (keyword recall@5 + triggers) | 54 | 100.000 % | 93.359 % (small-n) |

**What it does NOT cover:** open-ended LLM behaviour — stochastic by nature, measured
(never guaranteed) by the 21-task agent suite (`evals/results.jsonl`, event assertions
for route/guard/verify/redact) and the DSA benchmark:

| algorithm | best (ms), n=2000 | algorithm | best (ms) |
|---|---|---|---|
| timsort (ref) | 0.66 | bubble | 128.6 |
| heap | 1.71 | insertion | 20.6 |
| quick | 2.32 | merge | 3.33 |

Cloud tier verified end-to-end on `gemini-3.6-flash` (Gemini 3+ uses Google's default
temperature 1.0 — BEE omits the deprecated `temperature`/`top_p`/`top_k` for it) with
PII redaction confirmed on wire.

---

## 12. Troubleshooting

| Symptom | Fix |
|---|---|
| `Ollama not reachable` | BEE starts it (A60a: `ollama.autostart: true` launches the server on a background thread at boot, and the health page says which of the two states you are in) — if it is still down, start it yourself and check `status()`; `ollama pull qwen2.5:3b` + `ollama create bee4b -f models\bee4b.Modelfile` if the models are missing |
| Slow local answers | `ollama ps` → PROCESSOR shows the CPU/GPU split. bee4b (Qwen2.5-3B) is **2.31 GB including its KV cache** at `num_ctx: 8192` and measured fully resident on this 4 GB card (A59's `size_vram` table: 12288 spills 0.46 GB and adds ~1.5 s per call) — if you see a partial CPU split, close other GPU apps or lower `num_ctx`. Bigger local models (7B+) CPU-offload on this card by hardware limit — that's why bee4b is 3B-based |
| Whole system stalls, evals hang | check free RAM (`Get-CimInstance Win32_OperatingSystem`). Zombie `llama-server` processes from killed sessions hoard ~4 GB: kill them (`Stop-Process -Name llama-server`, or via Task Manager), wait for pagefile to settle, rerun in batches of 2–3 LLM tasks |
| Cloud 401 / "no credits" | key must match `cloud.llm` provider (`gemini/…` → `GOOGLE_API_KEY`); an OpenAI key with no credits fails — switch providers in `config.yaml` |
| Cloud model 404 | model deprecated/renamed — query the provider's models API and update `cloud.llm` |
| Voice: no STT | `pip install -r requirements-voice.txt`; voice mode prints a pre-warm message (first run downloads the whisper model, ~150 MB, into `workspace/models/` as plain files — no Developer Mode needed); check Windows mic privacy settings |
| Voice (web): `WinError 1314` during model download | fixed — the model now downloads to a local dir (no symlinks); if it ever recurs, delete `~/.cache/huggingface` and retry |
| Voice: `cublas64_12.dll is not found` on the first round | fixed — on Windows, STT `device: auto` now resolves to CPU (the CUDA ctranslate2 wheel needs NVIDIA cublas DLLs a plain driver doesn't provide); if a GPU error still occurs mid-inference, it rebuilds on CPU and retries once. Force GPU with `voice.device: cuda` only if you've installed the CUDA runtime |
| Voice: says "I'm listening" but nothing happens | short utterances are retried without VAD; if still silent, the mic may be muted/captured by another app — check `Get-Process` for mic holders |
| Voice: no TTS | `pip install pyttsx3` (offline) or set `voice.edge_key` (neural); verify with `/tts voices` + `/tts test` |
| Trivial messages ("hi") feel slow | they shouldn't — smalltalk + math are answered by the deterministic tier in 0 ms with no model call; if you still see model meta under a greeting, check the task text (anything beyond a bare greeting routes to a model by design) |
| Real tasks slow AND the whole PC lags | free RAM is the bottleneck: with the local model resident, keep ≥ 4 GB free — close browsers/apps or run `ollama stop bee4b` between sessions |
| `docker not reachable` / setup.ps1 skips the sandbox build | the Docker **daemon** must be running (setup.ps1 checks `docker info`); start Docker Desktop and rerun. setup.ps1 skips the build when `bee-sandbox:latest` exists, and builds from a temp copy (OneDrive files can be read truncated by Docker's WSL2 backend → "invalid file request Dockerfile") |
| sandbox says "GPU not available — ran on CPU" | expected on Docker Desktop without the NVIDIA Container Toolkit; the sandbox auto-detects the missing nvidia runtime and falls back to CPU (no action needed) |
| Stale behaviour after edits | clear `__pycache__` before running — OneDrive keeps stale .pyc copies: `Get-ChildItem -Recurse -Directory -Filter __pycache__ bee \| Remove-Item -Recurse -Force` |
| `results.jsonl` / small files missing | OneDrive file eviction of rarely-read files — BEE re-writes results per task, so rerunning the eval regenerates them |
| Model answers with JSON tool calls as text | already handled — `agent/loop.py` recovery parser (7/7 tests) |

---

## 13. Deployment

**Personal daily driver (this setup):**

1. `python -m bee.cli` — REPL for desk work; `python -m bee.cli web` for the localhost chat
   UI (binds 127.0.0.1 only).
2. **Nightly job** (memory consolidation + ML-router retrain at 03:00) via Task Scheduler:
   `schtasks /Create /SC DAILY /ST 03:00 /TN "BEE consolidate" /TR "python -m bee.cli consolidate"`
   (the in-process scheduler runs it too while BEE is open — pick one, not both).
3. Ollama runs as a background service from the installer; keep the two models pulled
   (`bee4b`/`qwen2.5:3b`, `nomic-embed-text`).

**Headless / unattended:** set `guard.mode: unattended` (auto-deny destructive),
`privacy.redact_cloud: true`, run with `python -m bee.cli plan <sub>` or the web API;
every run is metric-logged (`metrics/metrics.jsonl`) and eval-gated.

**Scaling the brain (Phase 5):** accumulate ≥ 200 verified episodes →
`python -m bee.pipeline.train_router` (learned router) → `training/qlora/train.py --dry-run`
then a real QLoRA run on a GPU box → `merge_export.py` → `ollama create bee-8b` →
flip `models.yaml`. Full plan: `docs/llm-component.md`, `docs/training-plan.md`.

**Safety invariants (tested):** file tools jailed to the workspace · AST-whitelisted
calculator · guard rails + capability gate enforced in the loop (every kernel surface,
sub-agents and clap mode included) · cloud PII-redacted · web UI localhost-only
· local voice audio never leaves the machine (LiveKit room audio transits LiveKit
Cloud — see §6.5) · secrets env-only · external web content treated as untrusted
(state-changing actions after ingestion are escalated to explicit approval).

---

## Roadmap

- [x] **Phase 1** — MVP agent (loop, tools, markdown memory, CLI)
- [x] **Phase 2** — hybrid routing, web UI, voice in/out, sandbox, vector memory
- [x] **Phase 3** — reflection + skills + nightly consolidation + evals
- [x] **Phase 4** — production hardening: 4-tier hybrid routing (learned ML router +
  deterministic tier), guard rails, privacy redaction, verifier, offline mode, RAG,
   episode data flywheel + QLoRA pipeline, monitoring, 71,914-check verification suite
   (5 suites with Wilson 95 % CI lower ≥ 99.9 %), **assistant command layer
   (`/plan /draft /summarize /code /think /remind /welcome` — 7 in the registry),
   BEE persona, configurable TTS**,
    **fast-path command catalog (46 pure-Python handlers) + engine selection
   (hybrid/local/ollama-cloud/api-cloud) + cloud teach-back**
- [x] **Phase 4.5** — **Super JARVIS integration**: Welcome Home protocol,
   double-clap acoustic trigger, hands-free PC control (systemctl: stats/hardware/battery/
   volume/brightness/lock/sleep/media/show-desktop), wikipedia + play fast paths,
   optional vision (webcam photo + face count) — all pure Windows APIs, no
    pyautogui/psutil, all action-y paths guard-checked
 - [x] **Phase 4.6** — **Live realtime voice + face (LiveKit Cloud free tier) +
    fullstack-agent integration**: LiveKit agent (silero VAD → local faster-whisper
    STT → full BEE pipeline → edge-tts/pyttsx3 TTS), `/face` sync visualizer with a
    cross-process state bridge, `start_talk.ps1` "Talk" one-shot, and the
    temperature-aware `gemini-3.6-flash` cloud tier. First-class personalization
    (`user:` → "Who I serve" prompt block). Maps fullstack-agent: mind→memory vault,
    mouth→LiveKit,     face→`/face`, hands→(not ported — RAM-bound)
 - [x] **Phase 4.7** — **Native Go telemetry daemon** (`bee/native/`): stdlib-only Go,
    reads CPU/RAM/disk/battery straight from the Windows API over localhost HTTP (~1 ms
    vs ~500 ms WMI), auto-built to `%LOCALAPPDATA%\bee`, background-launched, graceful
    WMI fallback. Polyglot stack: Python orchestration over Go/Rust/C++ native layers.
 - [x] **Phase 4.8** — **ML/DL + DSA + automation hardening**: ML route router upgraded
    to cross-validated **ML-vs-DL model selection** (LogReg vs MLPClassifier) + sublinear
    TF-IDF + an mtime-keyed model cache (predict ~0.6 ms, no per-call disk re-unpickle);
    **provably-correct DSA** via `bee/dsa/verify.py` (~3,400 assertions vs independent
    references; found & fixed a `merge_sort` reverse-stability bug); new `automate` tool
    (inventory / batch-rename dry-run / CSV↔JSONL↔TSV / dedupe / head-tail-grep /
     template-fill, workspace-confined); restored the router's missing `scikit-learn`
     dependency (it had been silently disabled).
 - [x] **Phase 4.9** — **Super-power pass**: DL route model is now feature-**scaled**
    (`StandardScaler`) — kills the MLP `ConvergenceWarning` and lifts accuracy; added
    `mlp_deep` to the cross-validated ML-vs-DL selection + 3 discriminative features
    (`has_path`/`has_number`/`log_len`). DSA extended to **9 modules** (+`binary_tree`
    traversals/BST/LCA, +`heap`/quickselect — ~6,000 assertions; fixed a `pushpop`
    return-logic bug and a missing-`heapify` reference bug). `automate` gained 4 recipes
    (`jsonq` jq-lite / `count` / `find` / `zip` — 10 total). SFT pipeline: data-**quality
    scoring** + `--min-quality` filter + opt-in cloud-teacher **paraphrase augmentation**
    (`--paraphrase N`) to train more from the same verified examples.
  - [ ] **Phase 5** — first `bee-8b` fine-tune from verified episodes (pipeline + J3
    quality gate ready; no trained model promoted yet) · GPU sandbox variant ·
   unattended-automation hardening · more commands (`/inbox`) via the registry
   (`/remind` shipped — 7 commands register today) · **A64: cloud goldens still store
   the kernel-augmented prompt as the user's task, and the verified corpus is empty
   until that is fixed, so there is currently nothing honest to fine-tune on**
- [x] **Proactive event intelligence (A22–A23)** — six event sources now run in
 production (timer, file-change, battery, network, app foreground/launch, memory+disk
 pressure), all edge-triggered with hysteresis; rules stay default-deny and
 user-authorized, and threshold rules finally work (`{"ram_free_mb<=": 1500}`,
 `{"name": "device.memory_low"}`). Verified live on this machine: a real 4.1 GB-free
 reading produced `device.memory_low` and fired an authorized rule, while an
 unauthorized policy returned nothing.
- [x] **Phases 6–12 (JARVIS program, 2026-10-08)** — provider abstraction · unified
   durable scheduler (JobWorker through the kernel) · ML-router reproducibility + CI ·
   typed planner + persistent sessions + provenance memory · realtime voice engine
   (barge-in, 6-state machine, LiveKit behind a transport) · safe computer use
   (observe→act→verify loop, coordinate provenance, emergency stops, vision
   abstraction) · proactive policy (default-deny, quiet hours, external
   authorization) · final production hardening + **independent acceptance audit**
   (`docs/JARVIS_ACCEPTANCE_AUDIT.md`, 535/535 tests, P0/P1 fixes F0–F5).
   Authoritative feature status: `docs/STATUS.md` · full phase history:
   `docs/JARVIS_ROADMAP.md`.
- [x] **Context + measurement pass (A57–A64, 2026-10-13→15)** — the local context
   window now reaches the model and is sized to a **measured** real turn (A58/A59),
   BEE **starts Ollama itself** at boot (A60a), old tool history is compacted before
   Ollama truncates it and says so when it cannot fit (A60c), the eval headline
   counts only tasks that actually ran (A62), and the harness stopped writing the
   user's **training corpus and score ledger** (A57/A61) — which is how the cloud
   golden corpus turned out to be 208 rows of test fixtures (A63, quarantined).
   Measured on this machine: `pytest tests -q` **928 passed, 0 failed**, verify_suite
   **ALL PASS** (71,914 checks), agent eval **20/21** in one invocation, 0 skipped.

---

*BEE is opinionated but readable — every module starts with a docstring of what it does and
why. Read it, edit it, make it yours.*
