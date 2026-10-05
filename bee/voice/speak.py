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


def _edge_tts_speak(text: str, key: str = "", voice: str = "en-US-AndrewMultilingualNeural",
                    rate: int = 190) -> bool:
    if not key:
        return False
    try:
        import edge_tts
    except ImportError:
        return False
    out = Path(tempfile.gettempdir()) / "bee_tts.mp3"

    async def gen():
        import asyncio
        communicate = edge_tts.Communicate(text, voice, rate=_edge_rate_pct(rate))
        await communicate.save(str(out))

    try:
        import asyncio
        asyncio.run(gen())
    except Exception as e:
        log.info("edge-tts failed: %s", e)
        return False
    # play mp3
    if sys.platform == "win32":
        p = subprocess.run(["powershell", "-NoProfile", "-Command",
                            f"Add-Type -AssemblyName PresentationCore; "
                            f"(New-Object Media.SoundPlayer '{out}').PlaySync()"],
                           capture_output=True, timeout=60)
        return p.returncode == 0
    else:
        for player in ("mpg123", "ffplay", "aplay"):
            if __import__("shutil").which(player):
                args = [player, str(out)] if player != "ffplay" else ["ffplay", "-nodisp", "-autoexit", str(out)]
                p = subprocess.run(args, capture_output=True, timeout=120)
                return p.returncode == 0
    return False


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
