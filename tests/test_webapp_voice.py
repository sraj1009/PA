"""Web /voice route — regression pins (2026-10-17).

Two real defects, both visible only on a live upload:

  1. The route called a `get_kernel(ctx)` helper that was never defined ->
     NameError -> plain-text 500 on EVERY voice upload, so the kernel never
     ran. (The /chat route built its kernel inline; /voice assumed a helper.)
  2. `mic.read_wav` resampled via np.interp — which ALWAYS returns float64 —
     so any uploaded WAV whose rate != 16 kHz (pyttsx3, phone recordings,
     most real audio) crashed faster-whisper's ONNX VAD with
     "[ONNXRuntimeError] Unexpected input data type: tensor(double)".

The route test drives the REAL route and REAL get_kernel (model + kernel
construction stubbed); the dtype tests pin the float32 contract directly.

Run:  python -m pytest tests/test_webapp_voice.py -q
"""
from __future__ import annotations

import types
import wave

import numpy as np
import pytest
from fastapi.testclient import TestClient

from bee import webapp

TOKEN = "voicetokenvoicetokenvoicetoken"  # low-entropy by design: the repo
# secret-scan gate (test_secretscan) rejects plausible tokens even in tests/
H = {"Authorization": f"Bearer {TOKEN}"}


class _Kernel:
    """Stands in for AgentKernel; records calls, returns the result shape."""

    def __init__(self, *a, **kw):
        self.calls = []

    def run(self, text, session_id="web", **kw):
        self.calls.append({"text": text, "session": session_id})
        res = types.SimpleNamespace(model="stub-model", escalated=False)
        return types.SimpleNamespace(agent_result=res,
                                     output=f"handled: {text}", ok=True)


@pytest.fixture
def ctx(monkeypatch, tmp_path):
    monkeypatch.setattr(webapp, "_TOKEN", TOKEN)
    cfg = types.SimpleNamespace(
        voice=types.SimpleNamespace(model="base.en", device="cpu",
                                    compute_type="int8"))
    c = types.SimpleNamespace(cfg=cfg, kernel=None)
    monkeypatch.setattr(webapp, "CTX", c)
    monkeypatch.setattr(webapp, "_voice_available", lambda: True)
    # get_kernel does `from .kernel import AgentKernel` at call time, so the
    # stub goes on the package attribute it resolves.
    import bee.kernel as kernel_pkg
    monkeypatch.setattr(kernel_pkg, "AgentKernel", _Kernel)
    return c


def test_voice_route_completes_and_hits_kernel(ctx, monkeypatch):
    from bee.voice import mic

    monkeypatch.setattr(mic, "read_wav",
                        lambda p, target_rate=16000: (np.zeros(16000, np.float32),
                                                      target_rate))
    from bee.voice import transcribe
    monkeypatch.setattr(transcribe, "transcribe_audio",
                        lambda audio, **kw: "what time is it")

    c = TestClient(webapp.app)
    r = c.post("/voice", headers=H, files={"file": ("q.wav", b"RIFF0000",
                                                    "audio/wav")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["transcript"] == "what time is it"
    assert body["output"] == "handled: what time is it"
    assert body["ok"] is True
    assert ctx.kernel is not None, "route must build a kernel via get_kernel"
    assert ctx.kernel.calls == [{"text": "what time is it", "session": "voice"}]


def test_get_kernel_is_idempotent(ctx):
    k1 = webapp.get_kernel(ctx)
    k2 = webapp.get_kernel(ctx)
    assert k1 is k2


def test_read_wav_resample_returns_float32(tmp_path):
    """np.interp leaks float64; the ONNX VAD accepts only float32."""
    from bee.voice import mic
    p = tmp_path / "eightk.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(np.zeros(8000, np.int16).tobytes())
    arr, rate = mic.read_wav(p, target_rate=16000)
    assert rate == 16000
    assert len(arr) == 16000
    assert arr.dtype == np.float32, f"resample leaked {arr.dtype} to faster-whisper"


def test_private_read_wav_resample_returns_float32(tmp_path):
    from bee.voice import mic
    p = tmp_path / "eightk2.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(np.zeros(22050 * 2, np.int16).tobytes())
    arr = mic._read_wav(p, target_rate=16000)
    assert arr.dtype == np.float32


def test_transcribe_coerces_float64_to_float32(monkeypatch):
    """Chokepoint coercion: a float64 caller must not reach the model as-is."""
    from bee.voice import transcribe as tr

    class _Fake:
        def __init__(self):
            self.dtypes = []

        def transcribe(self, audio, language="en", beam_size=1, vad_filter=True):
            self.dtypes.append(np.asarray(audio).dtype)
            return [], None

    fake = _Fake()
    monkeypatch.setattr(tr, "_load", lambda *a, **k: fake)
    out = tr.transcribe_audio(np.zeros(1600, np.float64))
    assert out == ""
    assert fake.dtypes and all(d == np.float32 for d in fake.dtypes), fake.dtypes
