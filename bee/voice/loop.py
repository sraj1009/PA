"""Voice command loop: listen -> (wake word) -> task -> speak.

Usage in REPL:  /voice            (runs until /stop or Ctrl-C)
Standalone:     python -m bee.cli voice
"""
from __future__ import annotations

import logging
import re

from . import mic, speak, transcribe

log = logging.getLogger("bee.voice")


def _wake(text: str, wake_word: str) -> str | None:
    """If text starts with/contains the wake word, return the remainder (or None)."""
    t = text.strip().lower().rstrip(".!?")
    if not t:
        return None
    if t.startswith(wake_word):
        rest = t[len(wake_word):].strip(" ,.!")
        return rest if rest else ""
    if f" {wake_word} " in f" {t} ":
        return t.split(wake_word, 1)[1].strip(" ,.!")
    return None


def print_status(cfg):
    if not transcribe.available():
        print("  [voice] faster-whisper NOT installed — voice input unavailable.")
        print("          install:  pip install -r requirements-voice.txt")
        return False
    print(f"  [voice] STT: faster-whisper '{cfg.voice.model}' (local)   "
          f"TTS: {', '.join(speak.available()) or 'none'}")
    return True


def run_voice_loop(ctx, on_event=None, max_rounds: int = 0) -> None:
    from ..agent.loop import run_agent
    cfg = ctx.cfg
    if not print_status(cfg):
        return
    wake = (cfg.voice.wake_word or "").lower()
    print("\n  VOICE MODE — speak your task directly (saying 'bee' first also works). Ctrl-C to exit.\n")
    print("  [voice] warming up speech model (first run downloads ~150 MB)...")
    try:
        transcribe._load(cfg.voice.model, cfg.voice.device, cfg.voice.compute_type)
        print("  [voice] speech model ready.")
    except Exception as e:
        print(f"  [voice] pre-warm failed ({str(e)[:120]}) — will retry on your first utterance.")
    rounds = 0
    try:
        while True:
            if max_rounds and rounds >= max_rounds:
                break
            rounds += 1
            print(f"  \u25cf listening... (round {rounds})")
            try:
                audio = mic.record(sample_rate=cfg.voice.sample_rate,
                                   silence=cfg.voice.silence, max_seconds=cfg.voice.max_seconds)
            except mic.VoiceError as e:
                print(f"  [mic] {e}")
                continue
            try:
                text = transcribe.transcribe_audio(
                    audio, sample_rate=cfg.voice.sample_rate,
                    model=cfg.voice.model, device=cfg.voice.device,
                    compute_type=cfg.voice.compute_type)
            except Exception as e:
                print(f"  [stt] failed: {e}")
                continue
            print(f"  you: {text}")
            if not text:
                continue
            rest = _wake(text, wake) if wake else None
            if rest is None and len(text.strip()) >= 2:
                rest = text  # explicit voice session: every utterance is for BEE
            if rest is None:
                speak.speak("Yes? I'm listening.", cfg)
                continue
            task = rest
            if not task:
                speak.speak("What would you like me to do?", cfg)
                continue
            print(f"  task: {task}")
            result = run_agent(ctx, task)
            print(f"  BEE: {result.output[:400]}")
            speak.speak(result.output, cfg)
    except KeyboardInterrupt:
        print("\n  voice mode stopped.")
