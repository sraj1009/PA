# BEE Computer Use (Phase 5) — Safe Desktop Control

BEE can observe the user's desktop and act on it — **closed-loop, verified,
budget-bounded, stoppable**. This document states what is supported, what is
deliberately NOT supported, and every limitation honestly.

## Supported platforms

| Platform | Status |
|---|---|
| **Windows 10/11 (x86-64)** | Supported. Window enumeration/focus via win32gui, input via pyautogui, capture via mss, clipboard via win32clipboard. Install: `pip install -r requirements-desktop.txt`. |
| Linux / macOS | **Not implemented.** `make_desktop()` fails with a clean `DesktopError` (the tools report it to the model; nothing crashes). The `Desktop` protocol is platform-neutral — a Linux implementation (X11/Wayland) would be a new concrete class, not a redesign. |
| Headless / CI / tests | `MockDesktop` (in `bee/computeruse/desktop.py`) is the verified path: all 12 Phase-5 tests run against mocked UI states; **no test drives the real desktop**. |

**The real `WindowsDesktop` is thin and untested-in-field by CI** (no display
in the test path), in the same honest sense as `LiveKitTransport` in Phase 4:
it is exercised only by the mock protocol surface + manual runs.

## The safe set (implemented)

12 actions, each a `ComputerAction` with target, coordinates (+provenance),
semantic description, expected result, timeout, risk level, and verification
strategy:

| Verb | Tool | Capability | Default policy | Verification |
|---|---|---|---|---|
| `screenshot`, `inspect_ui` | `computer_observe` | `desktop.observe` (R1) | always_allow | n/a (read-only) |
| `open_application`, `focus_window`, `switch_window` | `computer_window` | `desktop.launch` (R3) | **ask** (task grant) | `window_exists` / `active_window` |
| `click`, `double_click`, `type_text`, `key_press`, `scroll` | `computer_input` | `desktop.control` (R3) | **ask** (task grant) | `screen_changed` (structural) |
| `copy`, `paste` | `computer_clipboard` | `desktop.clipboard` (R2) | always_allow | `clipboard_changed` / `screen_changed` |
| `computer_stop` | (user tool) | `desktop.control` | always_allow | stops all sessions |

## Deliberately NOT implemented (the unsafe set)

- unattended deletion (no file delete, no trash, no disk operations)
- financial transactions
- **credential entry** — `type_text` targeting a password/PIN/token/OTP
  field is refused at the session layer (`is_credential_target`), before any
  input device is touched
- arbitrary downloads / execution (no browser-driven install flows, no
  launching unknown binaries beyond named applications)
- destructive system actions (shutdown/reboot/format/registry)

These are not "hidden" — the verbs do not exist, so no grant, prompt, or
mistake can produce them.

## Closed-loop discipline (no open-loop sequences)

- One tool call = **one action**: pre-snapshot → act → post-observe →
  verify. The observation (active window, window count, screen hash,
  verification detail) goes back to the model, which decides the next step.
- **Action budget per task**: `computeruse.max_actions` (default 15). The
  16th call is refused with "action budget exhausted — report state and
  stop". Budget is task-scoped (a new task gets a fresh session).
- **Verification is never assumed**: if the expected effect did not happen,
  the result is `verified: false` + an explicit error ("do not claim
  success"). There is no automatic retry loop — the model decides (and the
  kernel's circuit breaker still bounds repeated identical calls).
- Verification strategies are **structural** (window title presence, active
  window, screen-hash change, clipboard change) — deterministic and
  model-free.

## "Never trust coordinates blindly"

Clicks carry `coordinate_source`. The session keeps the rects from the last
`computer_observe`:

- `window_rect` / `element_rect` claimed but the point is **outside every
  observed rect (or no observe happened)** → the action is **refused**
  ("call computer_observe first"). The claim is checked, not trusted.
- `model_raw` (the model invents a point) → allowed at the session layer
  **only because the risk layer escalated it to HIGH/ask** — the user must
  explicitly confirm that specific call — and verification still runs.

## Emergency STOP (three independent mechanisms)

1. **Task cancel** — `kernel.cancel()`: REPL `stop`, voice barge-in, or web
   cancel set `ctx.cancel_event`, which the session watches on every call.
2. **Global emergency stop** — `computeruse_emergency_stop()` (and the
   `computer_stop` tool) stops **every** active session and purges
   screenshots.
3. **Global hotkey — Ctrl+Alt+Q** (configurable `computeruse.hotkey`) — a
   daemon poller (GetAsyncKeyState) fires the emergency stop with no focus
   on the agent. Disable with `computeruse.hotkey_enabled: false`.

Stopping never leaves a session half-claiming success: stopped calls return
`blocked: "computer control stopped"`.

## Privacy (enforced in code, `bee/computeruse/privacy.py`)

- **Typed text is never logged** — only `text_len` enters audit/episode/
  receipt records; the payload never reaches the model-visible result either.
- **Clipboard content is never logged** — verification compares and reports
  the boolean only.
- **No pixels in logs** — observations carry an 8-char screen hash +
  geometry. The model sees structured window data (titles are needed for
  the loop); that payload is transient and untrusted-marked, not persisted.
- **Window/tab titles are not in log entries** — log rows carry window
  counts, not observed titles (a tab titled "Bank / Transfer" never lands in
  the audit trail).
- **Screenshot retention**: default is an in-memory hash ring (≤5 frames,
  nothing on disk); optional temp-dir saves are bounded by count AND
  `screenshot_retention_minutes` (default 5) and purged on stop/session end.

## Limitations (honest)

- UI understanding is **structural, not semantic**: window titles, classes,
  and rects — not a vision model reading pixels. Controls *inside* a window
  (buttons, fields) are identified by the model from the window geometry +
  the user's description; that is why unproven coordinates require explicit
  confirmation.
- `screen_changed` verifies that the screen changed, not *how* — a wrong
  click that still changes the screen needs the model to catch it via the
  next observation (or a stronger `expected` like `window_exists`).
- `switch_window`'s alt-tab fallback is best-effort; verification decides.
- Input latency: `typewrite` is 20 ms/char (deliberately conservative for
  on-screen keyboards); long type_text calls are bounded by the action
  timeout (default 10 s).
- Multi-monitor: capture uses monitor 1 by default; coordinates are
  virtual-screen coordinates (win32 convention).
- DPI scaling: pyautogui operates in physical pixels; on scaled displays the
  observed rects (physical) and clicks agree, but model-reasoned points may
  feel "off" — another reason provenance is enforced.

## Usage

```
python -m bee.cli repl          # then ask: "open the Chrome browser window"
python -m bee.cli realtime      # voice: "Bee. Open Chrome." — same kernel
```

Config (`config.yaml`):

```yaml
computeruse:
  enabled: true
  max_actions: 15            # per-task budget
  action_timeout: 10         # seconds per action
  screenshot_retention_minutes: 5
  screenshot_save: false     # true = temp dir (bounded) instead of hash ring
  hotkey: "ctrl+alt+q"       # global emergency stop
  hotkey_enabled: true
```

Tests: `python -m pytest tests/test_computeruse.py -q` (12 tests, all
mocked UI states — no real automation in CI).
