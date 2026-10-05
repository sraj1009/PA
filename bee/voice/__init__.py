"""BEE voice: mic capture -> faster-whisper (local) -> text; text -> TTS.

Optional deps (install with: pip install -r requirements-voice.txt):
  faster-whisper, sounddevice, numpy, pyttsx3
Fallbacks: ffmpeg/sndrec for mic, edge-tts (network) for speech.
"""
