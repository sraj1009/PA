"""Streaming-TTS and local-playback regressions (audit 2026-10-08).

Two real defects are pinned here:

  * `StreamingTTS.begin()` set `busy` only inside the branch that started a new
    worker. A `begin()` while the previous utterance's worker was still tearing
    down left `busy` unset, so the engine's echo guard (engine.py:131) believed
    TTS was idle and BEE could capture its own voice mid-reply. The test double
    `FakeTTS` sets busy unconditionally, which is why the engine suite stayed
    green against the bug.
  * `speak.py` played edge-tts output through
    `System.Windows.Media.SoundPlayer`, which only decodes WAV — the neural
    voice "succeeded" while staying silent on Windows. The same function also
    returned False without an Azure key, although edge-tts needs none.

Run:  python -m pytest tests/test_voice_tts.py -q
"""
from __future__ import annotations

import io
import shutil
import subprocess
import sys
import types
import wave
from pathlib import Path

import pytest

from bee.voice import speak
from bee.voice.realtime.tts_stream import StreamingTTS


def _slow_speak(tts, delay: float):
    """Stand-in synthesizer: burns `delay` s, then emits one chunk per sentence."""
    def _speak(sentence: str, stop) -> None:
        import time
        time.sleep(delay)
        tts._emit(f"<{sentence}>".encode(), stop)
    return _speak


# ----------------------------------------------------- begin()/busy contract
def test_begin_marks_busy_while_the_previous_worker_is_still_alive():
    """The bug: busy stayed unset when begin() reused an alive worker."""
    tts = StreamingTTS(sink=lambda b: None, voice="x")
    tts._speak_sentence = _slow_speak(tts, 0.3)
    tts.begin()
    tts.feed("one.")
    assert tts.busy
    tts.stop()                       # barge-in; the worker is mid-sleep
    assert tts._worker.is_alive()    # teardown is asynchronous
    tts.begin()                      # previous worker STILL alive here
    assert tts.busy, "begin() must mark busy regardless of worker reuse"
    assert tts._worker.is_alive()
    tts.stop()
    assert tts.wait_done(timeout=3.0)


def test_superseded_worker_cannot_emit_into_the_new_utterance():
    got: list[bytes] = []
    tts = StreamingTTS(sink=got.append, voice="x")
    tts._speak_sentence = _slow_speak(tts, 0.25)
    tts.begin()
    tts.feed("first.")
    tts.stop()                       # interrupt mid-sentence
    tts.begin()
    tts.feed("second.")
    assert tts.wait_done(timeout=3.0)
    assert got == [b"<second.>"], f"barge-in leaked audio from the old utterance: {got}"


def test_busy_clears_and_on_done_fires_only_for_the_current_utterance():
    done: list[int] = []
    tts = StreamingTTS(sink=lambda b: None, voice="x",
                       on_done=lambda: done.append(1))
    tts._speak_sentence = _slow_speak(tts, 0.02)
    tts.begin()
    tts.feed("alpha.")
    assert tts.wait_done(timeout=3.0)
    assert not tts.busy
    assert done == [1]
    # a barged-in utterance must NOT report completion
    tts.begin()
    tts.feed("beta.")
    tts.stop()
    assert tts.wait_done(timeout=3.0)
    assert done == [1]


def test_feed_after_stop_is_dropped():
    """feed() refuses to enqueue once the utterance is cancelled."""
    q: list[str] = []
    tts = StreamingTTS(sink=lambda b: None, voice="x")
    tts._speak_sentence = lambda s, stop: q.append(s)
    tts.begin()
    tts.stop()
    tts.feed("never spoken.")
    assert tts.wait_done(timeout=3.0)
    assert q == []


# --------------------------------------------------------- local TTS playback
def test_powershell_player_path_is_gone():
    """No shell-out player may come back: it only decoded WAV, so MP3 output
    "succeeded" silently, and it built a command line out of a file path."""
    src = Path(speak.__file__).read_text(encoding="utf-8")
    for needle in ("Add-Type", "New-Object", "powershell"):
        assert needle not in src, f"speak.py still shells out to {needle!r}"


@pytest.mark.skipif(sys.platform != "win32", reason="winsound is Windows-only")
def test_play_media_decodes_to_wav_and_uses_winsound(monkeypatch):
    calls: list[tuple] = []
    fake = types.SimpleNamespace(
        SND_MEMORY=4,
        PlaySound=lambda data, flags: calls.append((data, flags)))
    monkeypatch.setitem(sys.modules, "winsound", fake)
    monkeypatch.setattr(speak, "_decode_to_wav", lambda p: b"RIFFfake-wav")
    assert speak._play_media(Path("anything.mp3")) is True
    assert calls == [(b"RIFFfake-wav", 4)], "must hand winsound a WAV container"


@pytest.mark.skipif(sys.platform != "win32", reason="winsound is Windows-only")
def test_play_media_reports_failure_honestly_without_a_decoder(monkeypatch):
    monkeypatch.setattr(speak, "_decode_to_wav", lambda p: None)
    assert speak._play_media(Path("anything.mp3")) is False


def test_decode_to_wav_roundtrips_through_a_real_decoder(tmp_path):
    av = pytest.importorskip("av", reason="PyAV is an optional voice-tier dep")
    src = tmp_path / "tone.wav"
    with wave.open(str(src), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00\x40\x01" * 800)
    data = speak._decode_to_wav(src)
    assert data and data[:4] == b"RIFF" and data[8:12] == b"WAVE"
    with wave.open(io.BytesIO(data)) as r:
        assert r.getnframes() >= 800
        assert r.getnchannels() == 1


def test_edge_tts_runs_without_an_azure_key(monkeypatch, tmp_path):
    """`key` is config-compatible but unnecessary — gating on it only cost the
    neural voice, so an empty key must still synthesize and play."""
    import edge_tts

    class FakeCommunicate:
        def __init__(self, text, voice, rate="0%"):
            self.text, self.voice = text, voice

        async def save(self, path: str) -> None:
            Path(path).write_bytes(b"fake-mp3-bytes")

    monkeypatch.setattr(edge_tts, "Communicate", FakeCommunicate)
    played: list[Path] = []

    def fake_play(p: Path) -> bool:
        played.append(Path(p))
        return True

    monkeypatch.setattr(speak, "_play_media", fake_play)
    assert speak._edge_tts_speak("hello", key="", voice="en-US-AriaNeural") is True
    assert len(played) == 1
    assert played[0].suffix == ".mp3"
    assert not played[0].exists(), "the temp synthesis file must be cleaned up"


def test_edge_tts_returns_false_when_synthesis_fails(monkeypatch):
    import edge_tts

    class Boom:
        def __init__(self, *a, **k):
            pass

        async def save(self, path: str) -> None:
            raise RuntimeError("network down")

    monkeypatch.setattr(edge_tts, "Communicate", Boom)
    played: list[Path] = []
    monkeypatch.setattr(speak, "_play_media",
                        lambda p: played.append(p) or True)
    assert speak._edge_tts_speak("hello", key="", voice="en-US-AriaNeural") is False
    assert played == []


def test_speak_falls_back_to_pyttsx3_when_edge_playback_fails(monkeypatch):
    """Backend order must degrade, never claim a silent success."""
    monkeypatch.setattr(speak, "_edge_tts_speak",
                        lambda *a, **k: False)
    seen: list[str] = []
    monkeypatch.setattr(speak, "_pyttsx3_speak",
                        lambda text, rate=190, voice="": seen.append(text) or True)

    class V:
        enabled = True
        speak = True
        speak_limit = 500
        tts_voice = "en-US-AriaNeural"
        tts_rate = 190
        edge_key = ""

    class Cfg:
        voice = V()

    assert speak.speak("fallback please", Cfg()) is True
    assert seen == ["fallback please"]


def _wav_size_fields(wav: bytes) -> tuple[int, int]:
    """(data chunk size field, actual payload bytes)."""
    import struct
    d = wav.find(b"data")
    return struct.unpack("<I", wav[d + 4:d + 8])[0], len(wav) - (d + 8)


def test_decoded_wav_carries_exact_sizes_winsound_can_use(tmp_path):
    """A streamed (0xFFFFFFFF) header decodes fine in Python but winsound
    cannot size its buffer from it — that is a silent failure again."""
    pytest.importorskip("av", reason="PyAV is an optional voice-tier dep")
    src = tmp_path / "tone.wav"
    with wave.open(str(src), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
        w.writeframes(b"\x00\x00\x40\x01" * 4000)
    wav = speak._decode_to_wav(src)
    declared, payload = _wav_size_fields(wav)
    assert declared == payload, \
        f"WAV header is streamed ({declared}) but payload is {payload} — winsound cannot use it"
    with wave.open(io.BytesIO(wav)) as r:
        assert r.getnframes() == payload // 2


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg on PATH")
def test_ffmpeg_fallback_writes_a_seekable_wav(tmp_path, monkeypatch):
    """Piping ffmpeg WAV output to stdout produces unknown-size headers; the
    fallback must land in a file so the container stays playable."""
    monkeypatch.setitem(sys.modules, "av", None)      # force the fallback path
    src = tmp_path / "tone.wav"
    with wave.open(str(src), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
        w.writeframes(b"\x00\x00\x40\x01" * 4000)
    wav = speak._decode_to_wav(src)
    assert wav and wav[:4] == b"RIFF"
    declared, payload = _wav_size_fields(wav)
    assert declared == payload != 0xFFFFFFFF


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg on PATH")
def test_real_mp3_decodes_to_playable_wav(tmp_path):
    """The regression end-to-end: a real MP3 (what edge-tts produces) must
    become a WAV whose frame count the player can read."""
    pytest.importorskip("av", reason="PyAV is an optional voice-tier dep")
    mp3 = tmp_path / "edge.mp3"
    subprocess.run([ "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                     "sine=frequency=440:duration=1", "-codec:a", "libmp3lame",
                     "-y", str(mp3)], check=True, capture_output=True)
    assert mp3.stat().st_size > 1000
    wav = speak._decode_to_wav(mp3)
    declared, payload = _wav_size_fields(wav)
    assert declared == payload
    with wave.open(io.BytesIO(wav)) as r:
        assert r.getnframes() > 40000          # ~1 s of audio survived the decode
        assert r.getnchannels() == 1
