"""Voice engine tests (Phase 4) — true realtime conversation behavior.

Required scenarios: interruption, cancellation, partial transcript,
empty utterance, provider timeout, reconnect, repeated wake word,
overlapping speech, microphone failure. Plus: state-machine legality,
echo gating (BEE must not hear its own voice), and one end-to-end test
through the REAL agent kernel (scripted LLM stand-in, no network).

All audio is synthetic 440 Hz sine frames:
    SPEECH  rms~0.212  (clearly above any VAD gate)
    ECHO    rms~0.0106 (above the raw VAD floor, below the 2x echo gate)
    SILENCE rms~0.0007

Run:  python -m pytest tests/test_voice_engine.py -q
"""
from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from bee.voice.realtime import (
    FakeTTS, InvalidVoiceTransition, NullTransport, VoiceEngine,
    VoiceEngineCfg, VoiceState, voice_transition,
)
from bee.voice.realtime.stt_stream import SttTimeout


# ------------------------------------------------------------------ helpers
def _pcm(level: float, sr: int = 16000, ms: int = 100, freq: float = 440.0) -> bytes:
    n = sr * ms // 1000
    t = np.arange(n) / sr
    return (np.sin(2 * np.pi * freq * t) * int(level * 32767)).astype(np.int16).tobytes()


SPEECH = _pcm(0.3)
ECHO = _pcm(0.015)
SILENCE = _pcm(0.001)


def rep(frame: bytes, n: int) -> list[bytes]:
    """n copies of a 100 ms frame."""
    return [frame] * n


def wait_for(cond, timeout: float = 3.0, interval: float = 0.005) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if cond():
            return True
        time.sleep(interval)
    return False


def step_until(eng, cond, timeout: float = 6.0, interval: float = 0.002) -> bool:
    """Step SILENCE frames (paced like a real ~10 f/s mic plus slack) until
    cond() or the wall-clock deadline — the engine is frame-driven, so
    waiting without frames would stall completion handling."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        eng.step_frame(SILENCE)
        if cond():
            return True
        time.sleep(interval)
    return cond()


class FakeSTT:
    """Scripted StreamingSTT stand-in (same surface: begin/feed/partial/
    finalize/cancel/buffered_ms). finals may contain Exception instances."""

    def __init__(self, finals: list | None = None, partials: list | None = None):
        self._finals = list(finals or [])
        self._partials = list(partials or [])
        self._buf = bytearray()
        self.finalizes = 0
        self.partial_calls = 0

    def begin(self):
        self._buf = bytearray()

    def feed(self, pcm: bytes):
        self._buf.extend(pcm or b"")

    def buffered_ms(self) -> int:
        return len(self._buf) * 1000 // (2 * 16000)

    def partial(self) -> str:
        self.partial_calls += 1
        return self._partials.pop(0) if self._partials else ""

    def finalize(self) -> str:
        self.finalizes += 1
        item = self._finals.pop(0) if self._finals else ""
        if isinstance(item, Exception):
            raise item
        return item

    def cancel(self):
        self._buf = bytearray()


class FakeKernel:
    """Kernel stand-in: run() 'works' for delay seconds (polling the cancel
    event like the real loop), streams the reply word-by-word when on_token
    is passed, and returns a TaskResult-shaped object."""

    def __init__(self, reply: str = "Done.", delay: float = 0.0,
                 tokens: bool = True, token_delay: float = 0.0):
        self.calls: list[str] = []
        self.session_ids: list[str] = []
        self.cancel_event = threading.Event()
        self.cancel_count = 0
        self.ctx = SimpleNamespace(cancel_event=self.cancel_event)
        self.reply = reply
        self.delay = delay
        self.tokens = tokens
        self.token_delay = token_delay

    def cancel(self):
        self.cancel_count += 1
        self.cancel_event.set()

    def run(self, text, session_id=None, on_event=None, on_token=None, **kw):
        self.calls.append(text)
        self.session_ids.append(session_id)
        self.cancel_event.clear()
        t0 = time.time()
        while time.time() - t0 < self.delay:
            if self.cancel_event.is_set():
                break
            time.sleep(0.005)
        cancelled = self.cancel_event.is_set()
        out = "" if cancelled else self.reply
        if not cancelled and self.tokens and on_token is not None and out:
            for w in out.split(" "):
                if self.cancel_event.is_set():
                    cancelled = True
                    break
                on_token(w + " ")
                if self.token_delay:
                    time.sleep(self.token_delay)
        if on_event:
            on_event({"type": "task_done", "cancelled": cancelled})
        return SimpleNamespace(
            ok=not cancelled, output=out,
            error="cancelled" if cancelled else None, model="fake",
            iterations=1, tool_calls=0, escalated=False, cancelled=cancelled,
            verification=SimpleNamespace(verdict="unverified"))


def make_engine(cfg_over: dict | None = None, stt=None, tts=None, kernel=None,
                transport=None, events=None, sleep_fn=None):
    cfg = VoiceEngineCfg()
    for k, v in (cfg_over or {}).items():
        setattr(cfg, k, v)
    ev = events if events is not None else []
    eng = VoiceEngine(transport or NullTransport(),
                      stt or FakeSTT(),
                      tts or FakeTTS(),
                      kernel or FakeKernel(),
                      cfg=cfg, on_event=ev.append,
                      sleep_fn=sleep_fn or (lambda s: None))
    return eng, ev


# ------------------------------------------------------------ state machine
def test_state_machine_legality():
    with pytest.raises(InvalidVoiceTransition):
        voice_transition(VoiceState.IDLE, VoiceState.SPEAKING)
    with pytest.raises(InvalidVoiceTransition):
        voice_transition(VoiceState.ERROR, VoiceState.SPEAKING)
    # the full conversational chain is legal
    chain = [VoiceState.IDLE, VoiceState.LISTENING, VoiceState.PROCESSING,
             VoiceState.THINKING, VoiceState.SPEAKING, VoiceState.INTERRUPTED,
             VoiceState.LISTENING, VoiceState.ERROR, VoiceState.IDLE]
    cur = chain[0]
    for nxt in chain[1:]:
        voice_transition(cur, nxt)
        cur = nxt


# ---------------------------------------------------------------- scenarios
def test_1_interruption_barge_in():
    """User barges in while BEE is thinking/speaking: TTS stops immediately,
    the task is cancelled, and the interrupting utterance becomes the new turn."""
    events: list = []
    kernel = FakeKernel(reply="Done. Chrome is open now. Anything else you need?",
                        delay=0.6)
    tts = FakeTTS(sentence_delay=0.03)
    eng, ev = make_engine(cfg_over=dict(always_on=True),
                          stt=FakeSTT(finals=["open chrome", "stop"]),
                          kernel=kernel, tts=tts, events=events)
    eng.transport.connect()
    for f in rep(SPEECH, 5) + rep(SILENCE, 8):
        eng.step_frame(f)
    assert kernel.calls == ["open chrome"]
    assert wait_for(lambda: eng.state in (VoiceState.THINKING, VoiceState.SPEAKING))
    # sustained user speech -> barge-in
    for _ in range(3):
        eng.step_frame(SPEECH)
    assert tts.stops >= 1                       # (6) TTS stopped immediately
    assert kernel.cancel_count >= 1             # (7) task cancelled
    assert [t for _, t in eng.history] and "INTERRUPTED" in [t for _, t in eng.history]
    assert any(e["type"] == "barge_in" for e in ev)
    # the interrupting utterance ("stop") is captured and processed
    for _ in range(3):
        eng.step_frame(SPEECH)
    for _ in range(8):
        eng.step_frame(SILENCE)
    assert kernel.cancel_count >= 2
    assert "Stopped." in tts.sentences
    assert kernel.calls == ["open chrome"]      # "stop" never became a task


def test_2_cancellation_stop_word():
    """'stop' as a complete utterance cancels (even when nothing is running)."""
    events: list = []
    kernel = FakeKernel(reply="Sure, working on it.")
    tts = FakeTTS()
    eng, ev = make_engine(cfg_over=dict(always_on=True),
                          stt=FakeSTT(finals=["stop"]),
                          kernel=kernel, tts=tts, events=events)
    eng.transport.connect()
    for f in rep(SPEECH, 5) + rep(SILENCE, 8):
        eng.step_frame(f)
    assert kernel.cancel_count >= 1
    assert kernel.calls == []
    assert "Stopped." in tts.sentences
    assert any(e["type"] == "stopped" for e in ev)
    assert eng.state == VoiceState.LISTENING


def test_3_partial_transcript():
    """Interim transcripts flow while speaking; the task starts only at endpoint."""
    events: list = []
    kernel = FakeKernel(reply="Done.")
    eng, ev = make_engine(cfg_over=dict(always_on=True),
                          stt=FakeSTT(finals=["open chrome"],
                                       partials=["open", "open chrome"]),
                          kernel=kernel, events=events)
    eng.transport.connect()
    for f in rep(SPEECH, 40) + rep(SILENCE, 8):   # 4 s of speech -> 2 partials
        eng.step_frame(f)
    parts = [e["text"] for e in ev if e["type"] == "partial"]
    assert parts == ["open", "open chrome"]
    assert "open chrome" in kernel.calls
    assert [e for e in ev if e["type"] == "transcript"][0]["text"] == "open chrome"


def test_4_empty_utterance():
    """Noise blip detected as speech but transcribing to nothing: no task,
    back to listening."""
    events: list = []
    eng, ev = make_engine(cfg_over=dict(always_on=True),
                          stt=FakeSTT(finals=["   "]),
                          kernel=FakeKernel())
    eng.transport.connect()
    for f in rep(SPEECH, 5) + rep(SILENCE, 8):
        eng.step_frame(f)
    assert eng.state == VoiceState.LISTENING
    assert eng.kernel.calls == []
    assert any(e["type"] == "empty_utterance" for e in ev)


def test_5_provider_timeout():
    """STT final pass times out -> ERROR (fail closed) -> recover on next frame
    once the transport is still healthy."""
    events: list = []
    eng, ev = make_engine(cfg_over=dict(always_on=True),
                          stt=FakeSTT(finals=[SttTimeout("STT timed out after 30s")]))
    eng.transport.connect()
    for f in rep(SPEECH, 5) + rep(SILENCE, 8):
        eng.step_frame(f)
    # ERROR was hit (and the trailing frames already self-recovered — that is
    # the point: transport healthy -> next frame back in the conversation)
    assert "ERROR" in [t for _, t in eng.history]
    assert any(e["type"] == "error" and "timed out" in e["error"] for e in ev)
    eng.step_frame(SILENCE)
    assert eng.state == VoiceState.LISTENING
    assert any(e["type"] == "recovered" for e in ev)


def test_6_reconnect_after_connect_failures():
    """Transport connect fails twice, succeeds on the third: capped
    exponential backoff, then a normal conversation."""
    sleeps: list = []
    transport = NullTransport(frames=rep(SPEECH, 5) + rep(SILENCE, 8),
                              fail_connect=2)
    eng, ev = make_engine(cfg_over=dict(always_on=True),
                          stt=FakeSTT(finals=["open chrome"]),
                          kernel=FakeKernel(reply="Done."),
                          transport=transport,
                          sleep_fn=lambda s: sleeps.append(s))
    timer = threading.Timer(1.2, eng.stop)
    timer.daemon = True
    timer.start()
    eng.run()
    assert transport.connects == 3
    assert sleeps == [0.5, 1.0]           # capped backoff: 0.5 -> 1.0 -> ok
    assert eng.reconnects == 1
    assert "open chrome" in eng.kernel.calls
    assert "Done." in eng.tts.sentences
    assert transport.closed


def test_7_repeated_wake_word():
    """'bee' in IDLE wakes + acks; 'bee' again (as a whole utterance) re-acks
    and keeps listening — never a task."""
    events: list = []
    tts = FakeTTS()
    eng, ev = make_engine(cfg_over=dict(always_on=False, wake_word="bee",
                                        conversation=True),
                          stt=FakeSTT(finals=["bee", "bee"]),
                          tts=tts, events=events)
    eng.transport.connect()
    for f in rep(SPEECH, 4) + rep(SILENCE, 8):
        eng.step_frame(f)
    assert eng.state == VoiceState.LISTENING
    assert "Yes?" in tts.sentences
    for f in rep(SPEECH, 4) + rep(SILENCE, 8):
        eng.step_frame(f)
    assert eng.kernel.calls == []
    assert tts.sentences.count("Yes?") == 2
    assert [e for e in ev if e["type"] == "wake" and e.get("repeat")]


def test_8_overlapping_speech_new_turn_same_session():
    """Barge-in with a NEW command: old task cancelled, new turn processed on
    the same session (context continuity — the kernel owns that)."""
    kernel = FakeKernel(reply="Done. Window opened.", delay=0.5)
    tts = FakeTTS(sentence_delay=0.03)
    eng, ev = make_engine(cfg_over=dict(always_on=True),
                          stt=FakeSTT(finals=["open notepad", "close it"]),
                          kernel=kernel, tts=tts)
    eng.transport.connect()
    for f in rep(SPEECH, 5) + rep(SILENCE, 8):
        eng.step_frame(f)
    assert wait_for(lambda: kernel.calls == ["open notepad"])
    assert wait_for(lambda: eng.state in (VoiceState.THINKING, VoiceState.SPEAKING))
    for _ in range(3):
        eng.step_frame(SPEECH)            # user talks over BEE
    assert tts.stops >= 1
    assert kernel.cancel_count >= 1
    for _ in range(3):
        eng.step_frame(SPEECH)
    for _ in range(8):
        eng.step_frame(SILENCE)
    assert wait_for(lambda: len(kernel.calls) == 2)
    assert kernel.calls[1] == "close it"
    assert kernel.session_ids == ["voice", "voice"]


def test_9_microphone_failure_graceful():
    """Mic dies mid-run (read errors): close + reconnect with backoff; when
    attempts are exhausted the engine parks in ERROR and stops cleanly —
    no exception escapes run()."""
    sleeps: list = []
    transport = NullTransport(read_error=True)
    eng, ev = make_engine(cfg_over=dict(always_on=True, max_reconnect_attempts=2),
                          transport=transport,
                          sleep_fn=lambda s: sleeps.append(s))
    eng.run()
    assert eng.state == VoiceState.ERROR
    assert transport.closed
    assert transport.connects == 2                 # initial + 1 reconnect, then give up
    assert sleeps == [0.5, 1.0]
    errs = [e for e in ev if e["type"] == "error"]
    assert any("read failed" in e["error"] for e in errs)
    assert errs[-1]["error"] == "reconnect attempts exhausted"


def test_echo_gating_no_barge_on_own_voice():
    """BEE's own speech (echo level) while TTS is playing must NOT trigger a
    barge-in — the VAD gate is raised x echo_gate while audio is out."""
    kernel = FakeKernel(reply="One. Two. Three. Four. Five. Six.",
                        token_delay=0.05)
    tts = FakeTTS(sentence_delay=0.05)
    eng, ev = make_engine(cfg_over=dict(always_on=True),
                          stt=FakeSTT(finals=["hello there"]),
                          kernel=kernel, tts=tts)
    eng.transport.connect()
    for f in rep(SPEECH, 5) + rep(SILENCE, 8):
        eng.step_frame(f)
    assert step_until(eng, lambda: eng.state == VoiceState.SPEAKING)
    assert step_until(eng, lambda: tts.busy.is_set())
    for _ in range(6):
        eng.step_frame(ECHO)                # loud-ish echo of BEE's own voice
    assert tts.stops == 0
    assert kernel.cancel_count == 0
    assert eng.state in (VoiceState.SPEAKING, VoiceState.THINKING)


# ------------------------------------------------------- end-to-end (real kernel)
class ScriptedClient:
    """Same shape as tests/test_kernel_integration.py, plus chat_stream so
    the engine's streaming path (on_token) is genuinely exercised."""

    def __init__(self, script: list):
        self.script = list(script)
        self.calls = 0

    def chat(self, name, messages, tools=None, **kw):
        self.calls += 1
        item = self.script.pop(0) if self.script else "Done."
        return {"content": item, "usage": {}}

    def chat_stream(self, name, messages, on_token, tools=None, **kw):
        out = self.chat(name, messages, tools=tools, **kw)
        for w in (out.get("content") or "").split(" "):
            on_token(w + " ")
        return out

    def _has_ollama(self):
        return True

    def models_list(self):
        return ["bee4b"]


def test_10_end_to_end_real_kernel(tmp_path):
    """Full pipeline with the REAL AgentKernel + run_agent (scripted LLM):
    utterance -> kernel task -> streamed tokens -> spoken sentence -> back to
    LISTENING. The session id is 'voice' (same AgentSession system as text)."""
    from bee.agent.context import Context
    from bee.config import load_config
    from bee.kernel import AgentKernel, TaskState

    cfg = load_config()
    cfg.cloud.enabled = False
    cfg.workspace = tmp_path
    client = ScriptedClient(["Done. I opened the browser for you."])
    ctx = Context(cfg, workspace=tmp_path, client=client,
                  guard_on=True, guard_mode="unattended",
                  episodes_on=False, rag_on=False,
                  cancel_event=threading.Event())
    kernel = AgentKernel(ctx, sessions_dir=tmp_path / "sessions",
                         receipts_path=tmp_path / "receipts.jsonl")
    ctx.kernel = kernel
    tts = FakeTTS()
    eng, ev = make_engine(cfg_over=dict(always_on=True),
                          stt=FakeSTT(finals=["open the browser"]),
                          kernel=kernel, tts=tts)
    eng.transport.connect()
    for f in rep(SPEECH, 5) + rep(SILENCE, 8):
        eng.step_frame(f)
    assert step_until(eng, lambda: kernel.last_task is not None
                      and kernel.last_task.state == TaskState.COMPLETED, timeout=10.0)
    assert kernel.last_task.session_id == "voice"
    assert step_until(eng, lambda: eng.state == VoiceState.LISTENING)
    assert "Done. I opened the browser for you." in tts.sentences
    # genuine streaming: the first sentence was spoken before the task ended
    assert any(e["type"] == "state" and e["to"] == "SPEAKING" for e in ev)
    eng.close()
