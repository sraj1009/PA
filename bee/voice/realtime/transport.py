"""Audio transport abstraction (Phase 4).

The VoiceEngine talks ONLY to this protocol. It has no knowledge of
microphones, LiveKit rooms, or sockets. Concrete transports:

  - MicTransport      local sounddevice capture + local playback (this box)
  - LiveKitTransport  (bee/livekit/transport.py) a LiveKit room as the
                      transport: remote mic in, TTS out, with LiveKit's own
                      STT/TTS optional. The agent kernel never imports
                      LiveKit directly — it sees a Transport + an engine.

Audio is 16 kHz mono 16-bit signed PCM for capture; playback is whatever the
TTS backend produced (mp3/pcm) — the transport knows how to render it.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Protocol, runtime_checkable

log = logging.getLogger("bee.voice.transport")


class TransportError(RuntimeError):
    pass


@runtime_checkable
class VoiceTransport(Protocol):
    name: str

    def connect(self) -> None:
        """Establish capture/playback. Raises TransportError on failure."""
    ...

    def close(self) -> None:
        ...

    def is_connected(self) -> bool:
        ...

    def read_frame(self, timeout: float = 0.2) -> bytes | None:
        """Blocking read of one ~100 ms 16 kHz mono s16le frame. Returns None
        on timeout (no audio yet), raises TransportError on hard failure."""
        ...

    def play(self, audio: bytes) -> None:
        """Render a TTS audio chunk (format is transport-specific)."""
        ...


class MicTransport:
    """Local microphone transport via sounddevice (16 kHz mono)."""

    name = "mic"

    def __init__(self, sample_rate: int = 16000, frame_ms: int = 100,
                 play_speaker: bool = True):
        self.sample_rate = sample_rate
        self.frame_ms = frame_ms
        self._frame_samples = max(int(sample_rate * frame_ms / 1000), 1)
        self._q: queue.Queue = queue.Queue(maxsize=2000)
        self._stream = None
        self._playing = play_speaker
        self._connected = False
        self._err: str = ""

    def connect(self) -> None:
        try:
            import sounddevice as sd
            import numpy as np
        except ImportError as e:
            raise TransportError(f"sounddevice/numpy not installed: {e}")
        try:
            self._err = ""

            def _cb(indata, frames, t_info, status):
                data = indata[:, 0].copy() if indata.ndim > 1 else indata.ravel()
                # split into fixed frames
                start = 0
                while start + self._frame_samples <= len(data):
                    chunk = data[start:start + self._frame_samples].astype("int16")
                    try:
                        self._q.put_nowait(chunk.tobytes())
                    except queue.Full:
                        pass  # consumer is slow/backed up — drop oldest by design
                    start += self._frame_samples
                # leftover (rare) carried by the next callback's own chunk

            self._stream = sd.InputStream(
                samplerate=self.sample_rate, channels=1, dtype="int16",
                blocksize=self._frame_samples, callback=_cb)
            self._stream.start()
            self._connected = True
        except Exception as e:
            self._connected = False
            self._err = str(e)
            raise TransportError(f"mic capture failed: {e}")

    def close(self) -> None:
        self._connected = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def is_connected(self) -> bool:
        return self._connected

    def read_frame(self, timeout: float = 0.2) -> bytes | None:
        if not self._connected:
            raise TransportError(f"not connected: {self._err or 'closed'}")
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            return None
        except Exception as e:
            raise TransportError(f"read failed: {e}")

    def play(self, audio: bytes) -> None:
        """Local playback: write a wav to a temp file and play via the
        platform player (mirrors speak.py). Non-blocking best-effort."""
        if not self._playing or not audio:
            return
        try:
            import subprocess
            import sys
            import tempfile
            import wave
            from pathlib import Path
            # assume mp3 from edge-tts; if it looks like raw pcm, wrap as wav
            is_wav = audio[:4] == b"RIFF"
            with tempfile.NamedTemporaryFile(suffix=".mp3" if not is_wav else ".wav",
                                             delete=False) as f:
                f.write(audio)
                tmp = f.name
            if sys.platform == "win32":
                if is_wav:
                    subprocess.Popen(["powershell", "-NoProfile", "-Command",
                                      f"Add-Type -AssemblyName PresentationCore; (New-Object Media.SoundPlayer '{tmp}').PlaySync()"],
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                else:
                    subprocess.Popen(["powershell", "-NoProfile", "-Command",
                                      f"Add-Type -AssemblyName PresentationCore; $p=New-Object Media.SoundPlayer; (New-Object IO.FileStream '{tmp}'); "
                                      f"[void](Add-Type -Path (Resolve-Path -LiteralPath '{tmp}')) "],
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            else:
                for player in ("mpg123", "ffplay", "aplay"):
                    if __import__("shutil").which(player):
                        subprocess.Popen([player, tmp] if player != "ffplay" else ["ffplay", "-nodisp", "-autoexit", tmp],
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        break
            try:
                Path(tmp).unlink()
            except Exception:
                pass
        except Exception as e:
            log.debug("local playback failed: %s", e)


class NullTransport:
    """No-op transport for tests and headless runs (no real audio)."""

    name = "null"

    def __init__(self, frames: list[bytes] | None = None, play_log: list | None = None,
                 fail_connect: int = 0, read_error: bool = False):
        self._frames = list(frames or [])
        self._i = 0
        self.play_log = play_log if play_log is not None else []
        self._fail_connect = fail_connect   # number of connect() calls that raise
        self._connected = False
        self.read_error = read_error
        self.closed = False
        self.connects = 0

    def connect(self) -> None:
        self.connects += 1
        if self.connects <= self._fail_connect:
            raise TransportError("synthetic connect failure")
        self._connected = True

    def close(self) -> None:
        self._connected = False
        self.closed = True

    def is_connected(self) -> bool:
        return self._connected

    def read_frame(self, timeout: float = 0.2) -> bytes | None:
        if not self._connected:
            raise TransportError("not connected")
        if self.read_error:
            raise TransportError("synthetic read failure (mic died)")
        if self._i < len(self._frames):
            f = self._frames[self._i]
            self._i += 1
            return f
        time.sleep(min(timeout, 0.1))   # no audio yet — don't spin the pump loop
        return None

    def play(self, audio: bytes) -> None:
        self.play_log.append(audio)
