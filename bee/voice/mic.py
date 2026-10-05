"""Microphone capture with silence detection.

Primary: sounddevice (numpy frames).
Fallbacks: ffmpeg (stdin) / PowerShell Get-PSSnapIn sndrec (wav file).
Returns 16 kHz mono float32 numpy array, or raises VoiceError with a hint.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path


class VoiceError(RuntimeError):
    pass


def _has(mod: str) -> bool:
    try:
        __import__(mod)
        return True
    except Exception:
        return False


def record_sounddevice(sample_rate: int = 16000, silence: float = 1.2,
                       max_seconds: int = 90, min_seconds: float = 0.6) -> "float32 array":
    import numpy as np
    import sounddevice as sd

    frame = int(sample_rate * 0.3)
    q: list = []
    silence_frames_needed = int(silence / 0.3)
    total_frames = 0
    max_frames = max_seconds * sample_rate
    started = False
    silent_run = 0

    with sd.InputStream(samplerate=sample_rate, channels=1, dtype="float32", blocksize=frame) as stream:
        while total_frames < max_frames:
            data, _overflow = stream.read(frame)
            chunk = data.flatten()
            total_frames += len(chunk)
            loud = float(abs(chunk).max()) if chunk.size else 0.0
            if loud > 0.015:
                started = True
                silent_run = 0
            elif started:
                silent_run += 1
            if started:
                q.append(chunk)
                if silent_run >= silence_frames_needed and total_frames >= min_seconds * sample_rate:
                    break
    if not q:
        raise VoiceError("no speech detected (was the mic muted?)")
    return np.concatenate(q)


def _pcm_to_float(pcm: bytes, rate: int) -> "array":
    import numpy as np
    return (np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0)


def record_ffmpeg(sample_rate: int = 16000, max_seconds: int = 90) -> "float32 array":
    if not shutil.which("ffmpeg"):
        raise VoiceError("ffmpeg not found in PATH (fallback mic)")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "dshow",
           "-i", "audio=default", "-t", str(max_seconds), "-ar", str(sample_rate),
           "-ac", "1", "-f", "s16le", "-"]
    p = subprocess.run(cmd, capture_output=True, timeout=max_seconds + 10)
    if p.returncode != 0 or not p.stdout:
        raise VoiceError(f"ffmpeg mic capture failed: {p.stderr.decode(errors='ignore')[:200]}")
    return _pcm_to_float(p.stdout, sample_rate)


def record_powershell(sample_rate: int = 16000, seconds: int = 5) -> "float32 array":
    if sys.platform != "win32":
        raise VoiceError("powershell recorder is Windows-only")
    wf = Path(tempfile.gettempdir()) / "bee_mic.wav"
    ps = (f"Add-Type -AssemblyName System.Windows.Media; "
          f"$i = New-Object System.Windows.Media.AudioInputDevice; "
          f"# use sndrec if available, else prompt user")
    # use sndrec (bundled with Windows) when present
    sndrec = shutil.which("sndrec")
    if sndrec:
        p = subprocess.run([sndrec, wf.name], capture_output=True, text=True, timeout=seconds + 5,
                           cwd=str(tempfile.gettempdir()))
        if wf.exists():
            return _read_wav(wf, sample_rate)
        raise VoiceError("sndrec produced no file")
    raise VoiceError("no fallback mic: install sounddevice (pip install sounddevice) or ffmpeg")


def _read_wav(wf: Path, target_rate: int = 16000) -> "array":
    import numpy as np
    with wave.open(str(wf), "rb") as w:
        rate = w.getframerate()
        ch = w.getnchannels()
        n = w.getnframes()
        raw = w.readframes(n)
    arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        arr = arr.reshape(-1, ch).mean(axis=1)
    if rate != target_rate:  # naive linear resample
        idx = np.linspace(0, len(arr) - 1, int(len(arr) * target_rate / rate))
        arr = np.interp(idx, np.arange(len(arr)), arr)
    try:
        wf.unlink()
    except Exception:
        pass
    return arr


def record(sample_rate: int = 16000, silence: float = 1.2, max_seconds: int = 90) -> "float32 array":
    """Best-effort mic capture across available backends."""
    errors = []
    if _has("sounddevice"):
        try:
            return record_sounddevice(sample_rate, silence, max_seconds)
        except VoiceError as e:
            errors.append(str(e))
        except Exception as e:
            errors.append(f"sounddevice: {e}")
    try:
        return record_ffmpeg(sample_rate, max_seconds)
    except VoiceError as e:
        errors.append(str(e))
    try:
        return record_powershell(sample_rate, seconds=max(3, int(max_seconds / 10)))
    except VoiceError as e:
        errors.append(str(e))
    raise VoiceError(" | ".join(errors) or "no mic backend available — pip install sounddevice numpy")


def save_wav(audio, sample_rate: int, path: str | Path) -> Path:
    import numpy as np
    path = Path(path)
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return path


def read_wav(path: str | Path, target_rate: int = 16000):
    import numpy as np
    with wave.open(str(path), "rb") as w:
        rate = w.getframerate()
        ch = w.getnchannels()
        raw = w.readframes(w.getnframes())
    arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        arr = arr.reshape(-1, ch).mean(axis=1)
    if rate != target_rate:
        idx = np.linspace(0, len(arr) - 1, int(len(arr) * target_rate / rate))
        arr = np.interp(idx, np.arange(len(arr)), arr)
    return arr, target_rate
