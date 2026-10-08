"""Streaming TTS (Phase 4) — sentence-pipelined, chunk-streamed audio.

Genuine streaming where the backend supports it:
  - edge-tts: `Communicate.stream()` yields MP3 deltas as they are
    synthesized; each delta goes straight to the sink (speaker). Sentence N
    is synthesizing while sentence N-1 is still playing (pipeline).
  - pyttsx3: batch per sentence (no chunked API) — the fallback; documented.

The engine feeds complete sentences as tokens stream in; `stop()` tears the
pipeline down immediately (barge-in). `on_chunk`/`on_first` callbacks let the
engine flip to SPEAKING at the first real audio byte, not at the first word.
"""
from __future__ import annotations

import logging
import queue
import re
import threading
import time

log = logging.getLogger("bee.voice.tts")


class SentenceSplitter:
    """Accumulate streamed tokens into speakable sentences (min 15, max 200
    chars; break on . ! ? ; or newlines)."""

    def __init__(self, min_chars: int = 15, max_chars: int = 200):
        self.min_chars = min_chars
        self.max_chars = max_chars
        self._buf = ""

    def add(self, token: str) -> list[str]:
        self._buf += token or ""
        out: list[str] = []
        while True:
            m = re.search(r"[.!?;]\s|\n", self._buf)
            cut = None
            if m and (m.start() + 1) >= self.min_chars:
                cut = m.end()
            elif len(self._buf) >= self.max_chars:
                cut = self._buf.rfind(" ", 0, self.max_chars) or self.max_chars
            if cut is None:
                break
            out.append(self._buf[:cut].strip())
            self._buf = self._buf[cut:]
        return [s for s in out if s]

    def flush(self) -> str | None:
        s = self._buf.strip()
        self._buf = ""
        return s or None


class TtsError(RuntimeError):
    pass


class StreamingTTS:
    def __init__(self, sink, voice: str = "en-US-AndrewMultilingualNeural",
                 rate: int = 190, edge_key: str = "", timeout: float = 20.0,
                 on_first=None, on_done=None):
        """sink(audio_bytes) plays one chunk; on_first() fires at the first
        chunk of an utterance; on_done() fires when the whole utterance
        finished (or was stopped)."""
        self.sink = sink
        self.voice = voice
        self.rate = rate
        self.edge_key = edge_key
        self.timeout = timeout
        self.on_first = on_first
        self.on_done = on_done
        self._q: queue.Queue[str | None] = queue.Queue()
        self._stop = threading.Event()
        self._busy = threading.Event()
        self._worker: threading.Thread | None = None
        self._first_sent = False
        self._sent_any = False

    # ------------------------------------------------------------- control
    def begin(self) -> None:
        """Start a fresh utterance (resets first-chunk tracking)."""
        self._first_sent = False
        self._sent_any = False
        self._stop.clear()
        if self._worker is None or not self._worker.is_alive():
            self._worker = threading.Thread(target=self._run, daemon=True,
                                            name="BeeTtsStream")
            self._worker.start()
            self._busy.set()

    def feed(self, sentence: str) -> None:
        s = (sentence or "").strip()
        if s and not self._stop.is_set():
            self._q.put(s)

    def stop(self) -> None:
        """Immediate teardown (barge-in): drop queued sentences + flag the
        in-flight synthesis loop."""
        self._stop.set()
        try:
            while True:
                self._q.get_nowait()
        except queue.Empty:
            pass

    @property
    def busy(self) -> bool:
        return self._busy.is_set()

    def wait_done(self, timeout: float = 30.0) -> bool:
        t0 = time.time()
        while self._busy.is_set() and (time.time() - t0) < timeout:
            time.sleep(0.02)
        return not self._busy.is_set()

    # ------------------------------------------------------------- pipeline
    def _emit(self, chunk: bytes) -> None:
        if self._stop.is_set() or not chunk:
            return
        try:
            self.sink(chunk)
        except Exception as e:
            log.debug("sink failed: %s", e)
            return
        if not self._first_sent:
            self._first_sent = True
            self._sent_any = True
            if self.on_first:
                try:
                    self.on_first()
                except Exception:
                    pass

    def _run(self) -> None:
        while True:
            if self._stop.is_set():
                break
            try:
                item = self._q.get(timeout=0.15)
            except queue.Empty:
                if self._first_sent:  # utterance complete (sentences drained)
                    break
                continue
            if item is None:
                break
            if self._stop.is_set():
                break
            try:
                self._speak_sentence(item)
            except Exception as e:
                log.debug("sentence synth failed: %s", e)
        # utterance finished
        self._busy.clear()
        if self.on_done and not self._stop.is_set():
            try:
                self.on_done()
            except Exception:
                pass

    def _speak_sentence(self, sentence: str) -> None:
        if self.edge_key or self.voice.startswith("en-"):
            try:
                self._edge_stream(sentence)
                return
            except ImportError:
                pass
            except Exception as e:
                log.debug("edge-tts failed (%s) — falling back", str(e)[:80])
        self._pyttsx3_sentence(sentence)

    def _edge_stream(self, sentence: str) -> None:
        """GENUINE streaming: consume edge-tts's chunk iterator live."""
        import asyncio
        import edge_tts
        from ..speak import _edge_rate_pct

        async def gen():
            comm = edge_tts.Communicate(sentence, self.voice, rate=_edge_rate_pct(self.rate))
            async for chunk in comm.stream():
                if self._stop.is_set():
                    return
                if chunk.get("type") == "audio":
                    yield chunk.get("data", b"")

        loop = asyncio.new_event_loop()
        try:
            t0 = time.time()
            for data in loop.run_until_complete(_collect(gen(), self.timeout)):
                if self._stop.is_set() or time.time() - t0 > self.timeout:
                    break
                self._emit(data)
        finally:
            loop.close()

    def _pyttsx3_sentence(self, sentence: str) -> None:
        from .. import speak as _speak
        _speak._pyttsx3_speak(sentence, rate=self.rate,
                              voice="" if self.voice.startswith("en-") else self.voice)


async def _collect(gen, timeout: float):
    """Async generator wrapper with a wall-clock deadline."""
    import asyncio
    t0 = time.time()
    async for item in gen:
        if time.time() - t0 > timeout:
            raise TtsError(f"TTS timed out after {timeout:.0f}s")
        yield item
        await asyncio.sleep(0)


class FakeTTS:
    """Test double with the StreamingTTS lifecycle.

    Mirrors the real pipeline: begin() starts a worker that 'synthesizes'
    queued sentences (sleeping sentence_delay per sentence), busy stays set
    until the queue drains or stop() is called. stop() is immediate (the
    barge-in contract the engine relies on).
    """

    def __init__(self, sentence_delay: float = 0.0, fail: bool = False):
        self.sentences: list[str] = []
        self.played: list[bytes] = []
        self.stops = 0
        self.first_called = 0
        self.done_called = 0
        self._delay = sentence_delay
        self._fail = fail
        self._q: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None
        self._fed = False
        self.busy = threading.Event()

    def begin(self):
        self._stop.clear()
        self._fed = False
        self.busy.set()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def feed(self, sentence):
        if self._fail:
            # mirrors the real contract: the engine's tts.feed() can raise
            # (synthesis backend blew up) -> the engine routes to ERROR
            raise TtsError("fake TTS failure")
        s = (sentence or "").strip()
        if s and not self._stop.is_set() and self.busy.is_set():
            self._fed = True
            self._q.put(s)

    def stop(self):
        self.stops += 1
        self._stop.set()
        try:
            while True:
                self._q.get_nowait()
        except queue.Empty:
            pass
        self.busy.clear()

    def wait_done(self, timeout=30.0) -> bool:
        # wait for busy to CLEAR (Event.wait() returns on SET — wrong sense)
        t0 = time.perf_counter()
        while self.busy.is_set():
            if time.perf_counter() - t0 > timeout:
                return False
            self.busy.wait(0.01)
        return True

    @property
    def is_done(self):
        return not self.busy.is_set()

    def _run(self):
        try:
            while not self._stop.is_set():
                try:
                    s = self._q.get(timeout=0.05)
                except queue.Empty:
                    # re-check the queue directly: a feed() may have landed
                    # between the timeout and this check (begin/feed race)
                    if self._fed and self._q.empty():
                        break      # queue drained -> utterance complete
                    continue
                if s is None or self._stop.is_set():
                    break
                if self._delay:
                    time.sleep(self._delay)
                if self._stop.is_set():
                    break
                self.sentences.append(s)
                self.played.append(f"<audio:{s[:20]}>".encode())
                if len(self.sentences) == 1:
                    self.first_called += 1
        finally:
            self.busy.clear()
            self.done_called += 1
