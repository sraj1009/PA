"""Voice Activity Detection (Phase 4) — adaptive energy gate.

Same adaptive-noise-floor design as the double-clap detector (bee/voice/clap.py):
the noise floor tracks quiet frames only, so speech never inflates the
baseline. Pure PCM s16le mono input; no model download, works offline.

`feed(frame) -> (speech: bool, rms: float)` — one 100 ms frame in, a speech
decision out. The engine layers endpointing + barge-in timing on top.
"""
from __future__ import annotations

import struct


def frame_rms(pcm: bytes) -> float:
    """RMS of a 16-bit mono PCM frame (0..1 scale)."""
    n = len(pcm) // 2
    if n == 0:
        return 0.0
    # sample the leading 8000 samples for very long frames (fast path)
    if n > 8000:
        n = 8000
    vals = struct.unpack_from("<%dh" % n, pcm, 0)
    s = sum(v * v for v in vals)
    return (s / n) ** 0.5 / 32768.0  # RMS on a 0..1 scale


class EnergyVAD:
    def __init__(self, sample_rate: int = 16000, frame_ms: int = 100,
                 spike_ratio: float = 4.0, min_rms: float = 0.008,
                 alpha: float = 0.95, floor_min: float = 0.0015,
                 hangover_ms: int = 200):
        self.sample_rate = sample_rate
        self.frame_ms = frame_ms
        self.spike_ratio = spike_ratio
        self.min_rms = min_rms
        self.alpha = alpha
        self.floor_min = floor_min
        self.hangover_frames = max(1, hangover_ms // frame_ms)
        self.noise_floor = 0.006
        self._hang = 0
        self.frames_seen = 0

    def threshold(self) -> float:
        return max(self.noise_floor * self.spike_ratio, self.min_rms)

    def feed(self, pcm: bytes) -> tuple[bool, float]:
        """Returns (speech, rms). Speech frames keep a short hangover so brief
        dips inside a word don't chop the utterance."""
        rms = frame_rms(pcm)
        self.frames_seen += 1
        # adapt the floor on quiet frames only (speech never inflates it)
        if rms < self.threshold() * 0.6:
            self.noise_floor = self.alpha * self.noise_floor + (1 - self.alpha) * rms
            self.noise_floor = max(self.floor_min, self.noise_floor)
        speech = rms >= self.threshold()
        if speech:
            self._hang = self.hangover_frames
        elif self._hang > 0:
            self._hang -= 1
            speech = True
        return speech, rms
