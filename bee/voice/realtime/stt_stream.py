"""Streaming STT (Phase 4) — interim + final transcripts.

faster-whisper is fundamentally a batch model, so genuine *interim*
transcripts here come from re-transcribing the growing utterance window at a
rate-limited cadence (the standard local-ASR approach for partials). The
FINAL transcript is one pass over the complete utterance at endpoint.

The engine drives this: begin() -> feed(frame)* -> partial()/finalize().
A FakeSTT with the same shape is used in tests.
"""
from __future__ import annotations

import logging
import re
import struct
import threading
import time

log = logging.getLogger("bee.voice.stt")


class SttError(RuntimeError):
    pass


class SttTimeout(SttError):
    pass


def pcm_to_float(pcm: bytes) -> "float32 array":
    import numpy as np
    if not pcm:
        return np.zeros(0, dtype="float32")
    n = len(pcm) // 2
    raw = pcm[: n * 2]
    return (np.frombuffer(raw, dtype="<i2").astype("float32")) / 32768.0


class StreamingSTT:
    """Windowed partials + one final pass, over faster-whisper."""

    def __init__(self, sample_rate: int = 16000, model: str = "base.en",
                 device: str = "auto", compute_type: str = "int8",
                 language: str = "en", timeout: float = 30.0):
        self.sample_rate = sample_rate
        self.model = model
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.timeout = timeout
        self._buf: bytearray = bytearray()
        self._lock = threading.Lock()
        self._model = None

    # ------------------------------------------------------------- model
    def _ensure_model(self):
        if self._model is None:
            from .. import transcribe
            self._model = transcribe._load(self.model, self.device, self.compute_type)
        return self._model

    @staticmethod
    def _run(m, audio, language) -> str:
        from .. import transcribe
        try:
            return transcribe._once(m, audio, language)
        except Exception as e:
            raise SttError(f"transcribe failed: {e}")

    # ---------------------------------------------------------- lifecycle
    def begin(self) -> None:
        with self._lock:
            self._buf = bytearray()

    def feed(self, pcm: bytes) -> None:
        if pcm:
            with self._lock:
                self._buf.extend(pcm)

    def buffered_ms(self) -> int:
        with self._lock:
            return len(self._buf) * 1000 // (2 * self.sample_rate)

    def _audio(self) -> "array":
        with self._lock:
            data = bytes(self._buf)
        return pcm_to_float(data)

    def partial(self) -> str:
        """Interim transcript of the utterance so far ('' if nothing yet)."""
        try:
            if self.buffered_ms() < 180:
                return ""
            m = self._ensure_model()
            return self._run(m, self._audio(), self.language)
        except SttError:
            raise
        except Exception as e:
            log.debug("partial failed (non-fatal): %s", e)
            return ""

    def finalize(self) -> str:
        """Final transcript over the whole utterance; honors self.timeout."""
        buf = self._audio()
        if len(buf) < self.sample_rate * 0.12:  # <120 ms of audio
            self.begin()
            return ""
        m = self._ensure_model()
        box: dict = {"text": "", "err": None}

        def work():
            try:
                box["text"] = self._run(m, buf, self.language)
            except Exception as e:
                box["err"] = e
        t = threading.Thread(target=work)
        t.start()
        t.join(timeout=self.timeout)
        self.begin()
        if t.is_alive():
            raise SttTimeout(f"STT timed out after {self.timeout:.0f}s")
        if box["err"]:
            raise box["err"] if isinstance(box["err"], SttError) else SttError(str(box["err"]))
        return box["text"]

    def cancel(self) -> None:
        self.begin()

    @staticmethod
    def available() -> bool:
        try:
            import faster_whisper  # noqa: F401
            return True
        except ImportError:
            return False
