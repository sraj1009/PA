"""Text-to-speech.

Primary: pyttsx3 (offline; SAPI5 on Windows, espeak on Linux, NSSpeech on macOS).
Fallback: edge-tts (network; needs config voice.edge_key or internet).

Configuration (config.yaml voice: / REPL /tts):
  tts_rate   words per minute (pyttsx3 directly; edge-tts % derived, baseline 150 wpm)
  tts_voice  "" = system default; else case-insensitive substring match
             (SAPI name like "aria" | edge voice id like "en-US-AriaNeural")
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

log = logging.getLogger("bee.tts")


def _edge_rate_pct(tts_rate: int) -> str:
    """Map words/minute to an edge-tts rate percentage (baseline ~150 wpm)."""
    pct = int(round((max(60, min(300, tts_rate)) / 150.0 - 1.0) * 100))
    pct = max(-50, min(50, pct))
    return f"{pct:+d}%"


def _pick_py_voice(eng, wanted: str):
    """Return (voice_id, name) — substring match on name/id when wanted, else first."""
    voices = eng.getProperty("voices") or []
    if not voices:
        return None, ""
    if wanted:
        w = wanted.lower()
        for v in voices:
            if w in (v.name or "").lower() or w in (v.id or "").lower():
                return v.id, v.name
        log.info("tts_voice '%s' not found in SAPI voices — using first", wanted)
    return voices[0].id, voices[0].name


def _pyttsx3_speak(text: str, rate: int = 190, voice: str = "") -> bool:
    """Runs the blocking SAPI loop in a worker thread. Returns True on success."""
    box: dict = {"ok": False, "err": ""}

    def worker():
        try:
            import pyttsx3
            eng = pyttsx3.init()
            try:
                eng.setProperty("rate", rate)
                vid, vname = _pick_py_voice(eng, voice)
                if vid:
                    eng.setProperty("voice", vid)
                    log.info("TTS voice: %s", vname)
                eng.say(text)
                eng.runAndWait()
                box["ok"] = True
            finally:
                try:
                    eng.stop()
                except Exception:
                    pass
        except Exception as e:
            box["err"] = str(e)

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(timeout=max(5, len(text) // 4 + 10))
    if t.is_alive():
        log.warning("pyttsx3 timed out")
        return False
    if not box["ok"]:
        log.info("pyttsx3 failed: %s", box["err"])
        return False
    return True


def _wav_bytes(pcm: bytes, rate: int, channels: int = 1, width: int = 2) -> bytes:
    """Wrap raw PCM in a WAV container (winsound only understands WAV)."""
    import io
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def _decode_to_wav(path: Path) -> bytes | None:
    """Decode any container (mp3 included) to self-contained WAV bytes.

    The size fields must be EXACT: winsound's SND_MEMORY buffer cannot be
    sized from a streamed (0xFFFFFFFF) header, so the ffmpeg fallback writes a
    seekable file rather than piping to stdout.
    """
    try:
        import av
    except ImportError:
        av = None
    if av is not None:
        try:
            with av.open(str(path)) as cont:
                streams = cont.streams.audio
                if not streams:
                    return None
                stream = streams[0]
                rate = stream.rate or 22050
                res = av.AudioResampler(format="s16", layout="mono", rate=rate)
                chunks: list[bytes] = []
                for frame in cont.decode(stream):      # AudioStream is not iterable
                    for out in res.resample(frame):
                        chunks.append(out.tobytes())
                for out in res.resample(None):         # flush the resampler tail
                    chunks.append(out.tobytes())
                if chunks:
                    return _wav_bytes(b"".join(chunks), rate)
        except Exception as e:
            log.info("pyav decode failed (%s) — trying ffmpeg", str(e)[:120])
    import shutil
    ff = shutil.which("ffmpeg")
    if not ff:
        return None
    fd, tmp = tempfile.mkstemp(prefix="bee_tts_", suffix=".wav")
    os.close(fd)
    wav = Path(tmp)
    try:
        r = subprocess.run([ff, "-v", "error", "-i", str(path), "-y",
                            "-f", "wav", "-acodec", "pcm_s16le", "-ac", "1",
                            str(wav)], capture_output=True, timeout=120)
        if r.returncode != 0 or not wav.exists() or wav.stat().st_size < 44:
            log.info("ffmpeg decode failed: %s",
                     (r.stderr or b"").decode("utf-8", "replace")[:120])
            return None
        return wav.read_bytes()
    except Exception as e:
        log.info("ffmpeg decode failed: %s", e)
        return None
    finally:
        wav.unlink(missing_ok=True)


def _play_media(path: Path) -> bool:
    """Play an audio file on the default output device.

    The previous Windows path used System.Windows.Media.SoundPlayer, which only
    decodes WAV — an edge-tts MP3 "played" successfully while staying silent.
    """
    if sys.platform != "win32":
        import shutil
        for player in ("mpg123", "ffplay", "aplay"):
            if shutil.which(player):
                args = ([player, str(path)] if player != "ffplay"
                        else ["ffplay", "-nodisp", "-autoexit", str(path)])
                try:
                    p = subprocess.run(args, capture_output=True, timeout=120)
                    if p.returncode == 0:
                        return True
                except Exception as e:
                    log.info("%s failed: %s", player, e)
        return False
    try:
        import winsound
        wav = _decode_to_wav(path)
        if not wav:
            log.info("no MP3 decoder available (install PyAV or put ffmpeg on PATH)")
            return False
        winsound.PlaySound(wav, winsound.SND_MEMORY)
        return True
    except Exception as e:
        log.info("winsound playback failed: %s", e)
        return False


def _edge_tts_speak(text: str, key: str = "", voice: str = "en-US-AndrewMultilingualNeural",
                    rate: int = 190) -> bool:
    """Synthesize with edge-tts and play it. `key` is accepted for config
    compatibility — edge-tts itself is a free network service and needs none,
    so gating this on an Azure key only cost the neural voice for no reason."""
    try:
        import edge_tts
    except ImportError:
        return False
    fd, tmp = tempfile.mkstemp(prefix="bee_tts_", suffix=".mp3")
    os.close(fd)
    out = Path(tmp)

    async def gen():
        import asyncio
        communicate = edge_tts.Communicate(text, voice, rate=_edge_rate_pct(rate))
        await communicate.save(str(out))

    try:
        import asyncio
        asyncio.run(gen())
    except Exception as e:
        log.info("edge-tts failed: %s", e)
        out.unlink(missing_ok=True)
        return False
    try:
        return _play_media(out)
    finally:
        out.unlink(missing_ok=True)


def speak(text: str, cfg) -> bool:
    if not cfg.voice.enabled or not cfg.voice.speak:
        return False
    text = (text or "").strip()
    if not text:
        return False
    if len(text) > cfg.voice.speak_limit:
        text = text[: cfg.voice.speak_limit].rsplit(" ", 1)[0] + "..."
    voice = getattr(cfg.voice, "tts_voice", "") or ""
    if voice.startswith("en-") and voice.endswith("Neural"):  # edge-tts id -> use edge backend first
        if _edge_tts_speak(text, key=cfg.voice.edge_key, voice=voice, rate=cfg.voice.tts_rate):
            return True
    if _pyttsx3_speak(text, rate=cfg.voice.tts_rate, voice=voice):
        return True
    if _edge_tts_speak(text, key=cfg.voice.edge_key, voice=voice or "en-US-AndrewMultilingualNeural",
                       rate=cfg.voice.tts_rate):
        return True
    log.info("no TTS backend available — install pyttsx3 (offline) or set voice.edge_key (edge-tts)")
    return False


def py_voices() -> list[str]:
    """Names of installed SAPI/espeak voices (for /tts voices)."""
    box: dict = {"out": []}

    def worker():
        try:
            import pyttsx3
            eng = pyttsx3.init()
            try:
                box["out"] = [v.name for v in (eng.getProperty("voices") or [])]
            finally:
                try:
                    eng.stop()
                except Exception:
                    pass
        except Exception:
            pass

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(timeout=10)
    return box["out"]


def available() -> list[str]:
    out = []
    try:
        import pyttsx3  # noqa: F401
        out.append("pyttsx3")
    except Exception:
        pass
    try:
        import edge_tts  # noqa: F401
        out.append("edge-tts")
    except Exception:
        pass
    return out
