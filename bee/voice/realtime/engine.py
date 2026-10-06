"""VoiceEngine (Phase 4) — the realtime conversation orchestrator.

Pipeline (one ~100 ms frame at a time):

    transport frame
      -> EnergyVAD            (speech/silence, adaptive noise floor)
      -> wake capture         (IDLE: buffer a short utterance and STT-confirm
                               the wake word — energy alone never wakes)
      -> utterance capture    (LISTENING: feed StreamingSTT; interim partials
                               at a rate-limited cadence)
      -> endpointing          (silence_ms of quiet after speech, or
                               max_utterance_ms force-finalize)
      -> classification       (wake / stop / ack / repeated wake / task)
      -> kernel.run()         (worker thread — the SAME AgentSession/Task
                               system text uses; cancellation is
                               kernel.cancel(); the voice layer owns no
                               business logic)
      -> streamed tokens      (genuine LLM streaming -> SentenceSplitter)
      -> StreamingTTS         (genuine chunk streaming; sentence pipeline)
      -> transport.play()

Barge-in: while THINKING or SPEAKING, sustained speech (>= barge_min_speech_ms)
bares in. While TTS is playing the energy gate is raised x echo_gate, so BEE's
own voice looping back into the mic is not heard as the user. A barge-in does:
tts.stop() immediately + kernel.cancel() + INTERRUPTED -> LISTENING, and the
interrupting utterance is captured (backfilled from a short ring of recent
frames) and processed as the next turn with the same session context.

Failure handling: any STT/transport/TTS/step error routes to ERROR (fail
closed, no crash loop). run() reconnects the transport with capped
exponential backoff; step_frame() itself never raises.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from collections import deque

from .state import (VoiceEngineCfg, VoiceState, voice_transition)
from .stt_stream import SttError
from .transport import TransportError
from .tts_stream import SentenceSplitter
from .vad import EnergyVAD

log = logging.getLogger("bee.voice.engine")


class VoiceEngine:
    """Owns the voice state machine and timing; delegates all task logic to
    the kernel (which is injected — the engine works with any object exposing
    run(text, session_id=..., on_event=...) and cancel())."""

    def __init__(self, transport, stt, tts, kernel, cfg: VoiceEngineCfg | None = None,
                 on_event=None, sleep_fn=None, wake_ack_text: str = "Yes?"):
        self.transport = transport
        self.stt = stt
        self.tts = tts
        self.kernel = kernel
        self.cfg = cfg or VoiceEngineCfg()
        self.on_event = on_event
        self._sleep_fn = sleep_fn or time.sleep
        self.wake_ack_text = wake_ack_text

        self.vad = EnergyVAD(sample_rate=self.cfg.sample_rate,
                             frame_ms=self.cfg.frame_ms)

        self._state = VoiceState.IDLE
        self._lock = threading.RLock()

        # utterance capture
        self._capture = False
        self._silence = 0
        self._utterance_frames = 0
        self._partial_growth = 0
        self._last_partial = ""
        self._idle_listen = 0
        # wake-word capture (IDLE)
        self._wake_cap: bytearray | None = None
        self._wake_frames = 0
        self._wake_silence = 0
        # barge-in
        self._barge_frames = 0
        self._recent: deque[bytes] = deque(
            maxlen=max(2, self.cfg.barge_min_speech_ms // self.cfg.frame_ms + 2))
        # kernel worker
        self._worker: threading.Thread | None = None
        self._task_done = threading.Event()
        self._fully_fed = True
        self._task_result: dict | None = None
        self._splitter = SentenceSplitter()
        self._tts_started = False
        # lifecycle
        self._stop_event = threading.Event()
        self._backoff = 0.5
        self.reconnects = 0

    # ------------------------------------------------------------ inspection
    @property
    def state(self) -> VoiceState:
        with self._lock:
            return self._state

    @property
    def history(self) -> list:
        return self.cfg.history

    def _set_state(self, target: VoiceState) -> None:
        with self._lock:
            voice_transition(self._state, target)
            if target == self._state:
                return
            frm = self._state
            self._state = target
            self.cfg.history.append((frm.value, target.value))
        self._emit({"type": "state", "from": frm.value, "to": target.value})

    def _emit(self, ev: dict) -> None:
        if self.on_event:
            try:
                self.on_event(ev)
            except Exception:
                pass

    @property
    def _partial_every_frames(self) -> int:
        return max(1, self.cfg.partial_every_ms // self.cfg.frame_ms)

    def _tts_busy(self) -> bool:
        b = self.tts.busy
        if hasattr(b, "is_set"):      # FakeTTS (Event) vs StreamingTTS (property)
            return b.is_set()
        return bool(b)

    def stop(self) -> None:
        self._stop_event.set()

    def close(self) -> None:
        self._stop_event.set()
        try:
            self.tts.stop()
        except Exception:
            pass
        try:
            self.transport.close()
        except Exception:
            pass
        if self._worker is not None and self._worker.is_alive():
            self._worker.join(timeout=2.0)

    # ------------------------------------------------------------ frame step
    def step_frame(self, pcm: bytes) -> None:
        """Process one ~100 ms frame. NEVER raises — failures route to ERROR."""
        try:
            st = self.state
            if st == VoiceState.ERROR:
                self.recover()
                return
            if st == VoiceState.IDLE:
                self._step_idle(pcm)
            elif st in (VoiceState.THINKING, VoiceState.SPEAKING):
                self._step_speaking(pcm)
            else:   # LISTENING (PROCESSING/INTERRUPTED are transient)
                self._step_listening(pcm)
        except Exception as e:
            self._fail(f"frame step failure: {type(e).__name__}: {e}")

    # ----------------------------------------------------------------- IDLE
    def _step_idle(self, pcm: bytes) -> None:
        if self.cfg.always_on:
            self._set_state(VoiceState.LISTENING)
            self._idle_listen = 0
            self._step_listening(pcm)
            return
        speech, rms = self.vad.feed(pcm)
        if self._tts_busy():          # BEE's own ack still on the speaker
            return
        if self._wake_cap is None and speech:
            self._wake_cap = bytearray()
            self._wake_frames = 0
            self._wake_silence = 0
        if self._wake_cap is not None:
            self._wake_cap += pcm
            self._wake_frames += 1
            # endpointing measures REAL quiet (the hangover flag would eat
            # the first ~200 ms of genuine silence and delay endpointing)
            if rms < self.vad.threshold():
                self._wake_silence += 1
            else:
                self._wake_silence = 0
            if (self._wake_silence * self.cfg.frame_ms >= self.cfg.silence_ms
                    or self._wake_frames * self.cfg.frame_ms >= self.cfg.wake_max_ms):
                self._check_wake()

    def _check_wake(self) -> None:
        cap = bytes(self._wake_cap or b"")
        self._wake_cap = None
        self._wake_frames = 0
        self._wake_silence = 0
        if not cap:
            return
        self.stt.begin()
        self.stt.feed(cap)
        try:
            text = self.stt.finalize()
        except SttError as e:
            self._fail(f"STT wake failure: {e}")
            return
        norm = (text or "").lower().strip(" .!?,")
        if not self._has_wake(norm):
            if norm:
                self._emit({"type": "wake_reject", "text": norm})
            return
        self._emit({"type": "wake", "text": norm})
        remainder = self._wake_remainder(norm)
        self._set_state(VoiceState.LISTENING)
        self._idle_listen = 0
        if self.cfg.wake_ack:
            self._speak_fixed(self.wake_ack_text)
        if remainder:            # "bee, open chrome" said in one breath
            self._start_task(remainder)
        # else: LISTENING — wait for the command utterance

    def _has_wake(self, norm: str) -> bool:
        if not norm:
            return False
        w = re.escape(self.cfg.wake_word.lower().strip())
        return re.search(rf"\b{w}\b", norm) is not None

    def _wake_remainder(self, norm: str) -> str:
        w = self.cfg.wake_word.lower().strip()
        toks = norm.replace(",", " ").split()
        out, dropped = [], False
        for t in toks:
            if not dropped and t == w:
                dropped = True
                continue
            out.append(t)
        return " ".join(out).strip()

    # ---------------------------------------------------------- LISTENING
    def _step_listening(self, pcm: bytes) -> None:
        self._recent.append(pcm)
        speech, rms = self.vad.feed(pcm)
        if self._capture:
            self.stt.feed(pcm)
            self._utterance_frames += 1
            # endpointing measures REAL quiet, not the hangover-adjusted
            # speech flag (hangover keeps intra-word dips alive; it would
            # otherwise eat ~200 ms of the endpointing silence window)
            if rms < self.vad.threshold():
                self._silence += 1
            else:
                self._silence = 0
            self._partial_growth += len(pcm)
            if (self.cfg.partial_stt and self._utterance_frames
                    and self._utterance_frames % self._partial_every_frames == 0
                    and self._partial_growth >= self.cfg.partial_min_growth):
                self._partial_growth = 0
                try:
                    p = self.stt.partial()
                except SttError as e:
                    self._fail(f"STT partial failure: {e}")
                    return
                if p and p.strip() != self._last_partial:
                    self._last_partial = p.strip()
                    self._emit({"type": "partial", "text": self._last_partial})
            if (self._silence * self.cfg.frame_ms >= self.cfg.silence_ms
                    or self.stt.buffered_ms() >= self.cfg.max_utterance_ms):
                self._end_utterance()
                return
        elif speech:
            # echo guard: while BEE's own voice is on the speaker, don't
            # start capturing (its echo would be transcribed as the user)
            if self._tts_busy():
                return
            self.stt.begin()
            self._capture = True
            self._silence = 0
            self._utterance_frames = 0
            self._partial_growth = 0
            self._last_partial = ""
            self._idle_listen = 0
        else:
            if not self.cfg.always_on:
                self._idle_listen += 1
                if self._idle_listen * self.cfg.frame_ms >= self.cfg.listen_timeout_ms:
                    self._set_state(VoiceState.IDLE)

    def _end_utterance(self) -> None:
        self._capture = False
        self._set_state(VoiceState.PROCESSING)
        try:
            text = self.stt.finalize()
        except SttError as e:
            self._fail(f"STT final failure: {e}")
            return
        norm = (text or "").lower().strip(" .!?,")
        self._emit({"type": "transcript", "text": norm})
        if not norm:
            self._emit({"type": "empty_utterance"})
            self._set_state(self._post_state())
            return
        if self._is_stop(norm):
            # first-class cancellation: stop the active task (if any)
            try:
                self.kernel.cancel()
            except Exception:
                pass
            self._set_state(self._post_state())
            self._emit({"type": "stopped"})
            self._speak_fixed("Stopped.")
            return
        if self._is_ack(norm):
            self._set_state(self._post_state())
            self._emit({"type": "ack"})
            self._speak_fixed("Anything else?")
            return
        if self._has_wake(norm):
            # repeated wake word — re-ack and keep listening, never a task
            self._emit({"type": "wake", "text": norm, "repeat": True})
            self._set_state(self._post_state())
            if self.cfg.wake_ack:
                self._speak_fixed(self.wake_ack_text)
            return
        self._start_task(norm)

    def _is_stop(self, norm: str) -> bool:
        toks = norm.replace(",", " ").split()
        for w in self.cfg.stop_words:
            if norm == w or norm.endswith(" " + w):
                return True
            if len(w.split()) == 1 and w in toks:
                return True
        return False

    def _is_ack(self, norm: str) -> bool:
        return norm in self.cfg.ack_words

    def _post_state(self) -> VoiceState:
        if self.cfg.always_on or self.cfg.conversation:
            return VoiceState.LISTENING
        return VoiceState.IDLE

    # ------------------------------------------------- kernel task (worker)
    def _start_task(self, text: str) -> None:
        # clear any stale cancel flag (the REPL does the same before each run)
        ev = getattr(getattr(self.kernel, "ctx", None), "cancel_event", None)
        if isinstance(ev, threading.Event):
            ev.clear()
        self._task_done.clear()
        self._fully_fed = False
        self._task_result = None
        self._splitter = SentenceSplitter()
        self._tts_started = False
        self._set_state(VoiceState.THINKING)
        self._emit({"type": "task_start", "text": text})
        self._worker = threading.Thread(target=self._task_worker, args=(text,),
                                        daemon=True, name="BeeVoiceTask")
        self._worker.start()

    def _task_worker(self, text: str) -> None:
        try:
            result = self.kernel.run(
                text, session_id=self.cfg.session_id,
                on_event=self._on_kernel_event,
                # a truthy on_token switches the loop to genuine streaming
                # (chat_stream); the token dicts then also arrive through
                # on_event via the kernel's bridge.
                on_token=lambda _t: None)
        except Exception as e:
            self._task_result = {"ok": False, "output": "",
                                 "error": f"{type(e).__name__}: {e}",
                                 "cancelled": False}
        else:
            self._task_result = {
                "ok": getattr(result, "ok", True),
                "output": getattr(result, "output", "") or "",
                "error": getattr(result, "error", None),
                "cancelled": bool(getattr(result, "cancelled", False)),
            }
        finally:
            self._flush_splitter()
            self._fully_fed = True
            self._task_done.set()

    def _on_kernel_event(self, ev: dict) -> None:
        t = ev.get("type")
        if t == "token":
            self._on_token(ev.get("text", ""))
            return
        self._emit(ev)     # tool_start / tool_result / verify / route / ...

    def _on_token(self, text: str) -> None:
        if not text:
            return
        if self.state not in (VoiceState.THINKING, VoiceState.SPEAKING):
            return                     # interrupted / cancelled — stop audio
        sentences = self._splitter.add(text)
        for s in sentences:
            if self.state not in (VoiceState.THINKING, VoiceState.SPEAKING):
                return
            try:
                if self.state == VoiceState.THINKING:
                    self.tts.begin()
                    self._tts_started = True
                    try:
                        self._set_state(VoiceState.SPEAKING)
                    except Exception:
                        pass     # barge-in flipped the state first — tts.stop()
                                 # already dropped the queue, feeds below no-op
                self.tts.feed(s)
            except Exception as e:
                self._fail(f"TTS streaming failure: {e}")
                return

    def _flush_splitter(self) -> None:
        tail = self._splitter.flush()
        if not tail:
            return
        if self.state not in (VoiceState.THINKING, VoiceState.SPEAKING):
            return
        try:
            if self.state == VoiceState.THINKING and not self._tts_started:
                self.tts.begin()
                self._tts_started = True
            self.tts.feed(tail)
        except Exception:
            pass

    @staticmethod
    def _split_all(text: str) -> list[str]:
        s = SentenceSplitter()
        out = s.add(text)
        tail = s.flush()
        if tail:
            out.append(tail)
        return out or [text[:200]]

    # --------------------------------------------------- THINKING / SPEAKING
    def _step_speaking(self, pcm: bytes) -> None:
        self._recent.append(pcm)
        st = self.state
        done = self._task_done.is_set()
        if done and st == VoiceState.THINKING:
            self._finish_task()
            return
        if done and st == VoiceState.SPEAKING and self._fully_fed \
                and not self._tts_busy():
            self._finish_task()
            return
        # barge-in (works in THINKING even before any audio: the user may
        # interrupt a long tool call)
        if self.cfg.barge_in:
            _speech, rms = self.vad.feed(pcm)
            gate = self.vad.threshold() * (self.cfg.echo_gate
                                           if self._tts_busy() else 1.0)
            if rms >= gate:
                self._barge_frames += 1
                if self._barge_frames * self.cfg.frame_ms \
                        >= self.cfg.barge_min_speech_ms:
                    self._barge_in()
            else:
                self._barge_frames = 0
        else:
            self.vad.feed(pcm)         # keep the noise floor fresh

    def _barge_in(self) -> None:
        self._barge_frames = 0
        self._emit({"type": "barge_in"})
        try:
            self.tts.stop()            # (6) immediately stop TTS
        except Exception:
            pass
        try:
            self.kernel.cancel()       # (7) cancel the active task
        except Exception:
            pass
        self._set_state(VoiceState.INTERRUPTED)
        # capture the interrupting utterance (backfill the recent ring)
        try:
            self.stt.begin()
            for f in self._recent:
                self.stt.feed(f)
        except Exception:
            pass
        self._capture = True
        self._silence = 0
        self._utterance_frames = 0
        self._partial_growth = 0
        self._last_partial = ""
        self._set_state(VoiceState.LISTENING)

    def _finish_task(self) -> None:
        if self.state not in (VoiceState.THINKING, VoiceState.SPEAKING):
            return                     # barge-in already moved on; stale result
        res = self._task_result or {}
        cancelled = bool(res.get("cancelled"))
        err = res.get("error")
        out = (res.get("output") or "").strip()
        if self.state == VoiceState.THINKING:
            if cancelled:
                self._set_state(self._post_state())
                self._emit({"type": "cancelled"})
                self._speak_fixed("Stopped.")
                return
            if not out:
                self._set_state(self._post_state())
                if err:
                    self._emit({"type": "task_error", "error": str(err)})
                return
            # finished without streamed tokens: feed the complete answer —
            # each sentence is genuinely synthesized (real TTS, per sentence)
            self._set_state(VoiceState.SPEAKING)
            try:
                self.tts.begin()
                self._tts_started = True
                for s in self._split_all(out):
                    self.tts.feed(s)
            except Exception as e:
                self._fail(f"TTS failure: {e}")
                return
            return                     # drain check on the next frame
        # SPEAKING and fully drained
        self._set_state(self._post_state())
        self._emit({"type": "reply", "text": out})
        self._barge_frames = 0

    # ------------------------------------------------------------ utilities
    def _speak_fixed(self, text: str) -> None:
        if not text:
            return
        try:
            self.tts.begin()
            self.tts.feed(text)
            self.tts.wait_done(timeout=self.cfg.tts_timeout)
        except Exception as e:
            self._fail(f"TTS fixed-phrase failure: {e}")

    def _fail(self, reason: str) -> None:
        log.warning("voice engine -> ERROR: %s", reason)
        try:
            self.tts.stop()
        except Exception:
            pass
        try:
            self.stt.cancel()
        except Exception:
            pass
        self._capture = False
        self._wake_cap = None
        self._set_state(VoiceState.ERROR)
        self._emit({"type": "error", "error": reason})

    def recover(self) -> bool:
        """ERROR -> IDLE (or LISTENING when always-on) once the transport is up."""
        if self.state != VoiceState.ERROR:
            return True
        if not self.transport.is_connected():
            return False
        self._capture = False
        self._wake_cap = None
        self._barge_frames = 0
        self._idle_listen = 0
        self._recent.clear()
        self._set_state(VoiceState.LISTENING if self.cfg.always_on
                        else VoiceState.IDLE)
        self._emit({"type": "recovered"})
        return True

    # ------------------------------------------------------------- run loop
    def _recover_or_idle(self) -> None:
        if self.state == VoiceState.ERROR:
            self.recover()
        elif self.cfg.always_on and self.state == VoiceState.IDLE:
            self._set_state(VoiceState.LISTENING)

    def _ensure_connected(self) -> bool:
        if self.transport.is_connected():
            return True
        try:
            self.transport.connect()
        except TransportError as e:
            self._fail(f"transport connect failed: {e}")
            self._sleep_fn(min(self.cfg.reconnect_max, self._backoff))
            self._backoff = min(self.cfg.reconnect_max, self._backoff * 2)
            return False
        self.reconnects += 1
        self._recover_or_idle()
        return True

    def run(self) -> None:
        """Blocking transport pump with reconnect + capped backoff.

        stop() (or Ctrl-C) ends the loop. Mic death (read TransportError)
        forces a transport close + reconnect; if max_reconnect_attempts is
        set and exhausted, the engine fails over to ERROR and stops cleanly.
        """
        fails = 0
        try:
            while not self._stop_event.is_set():
                if self.cfg.max_reconnect_attempts \
                        and fails >= self.cfg.max_reconnect_attempts:
                    self._fail("reconnect attempts exhausted")
                    break
                if not self._ensure_connected():
                    fails += 1
                    continue
                # a reconnect only 'counts as good' once it actually delivers
                # audio — otherwise a mic that dies on every reconnect would
                # loop forever (connect ok -> read dies -> connect ok ...)
                got_audio = False
                while not self._stop_event.is_set() \
                        and self.transport.is_connected():
                    try:
                        frame = self.transport.read_frame(timeout=0.2)
                    except TransportError as e:
                        log.warning("transport read failed: %s", e)
                        self.transport.close()
                        fails += 1
                        self._fail(f"transport read failed: {e}")
                        self._sleep_fn(min(self.cfg.reconnect_max, self._backoff))
                        self._backoff = min(self.cfg.reconnect_max,
                                            self._backoff * 2)
                        break
                    if frame is None:
                        continue
                    got_audio = True
                    self.step_frame(frame)
                if got_audio:
                    fails = 0
                    self._backoff = 0.5     # transport actually delivering —
                                             # back to base backoff for next time
        except KeyboardInterrupt:
            pass
        finally:
            self.close()
