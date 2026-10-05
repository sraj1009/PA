"""BEE native subsystem — a Go-built system-telemetry daemon.

Python is excellent for orchestration/LLM/agents, but BEE's old system-stats
path spawned PowerShell + CIM/WMI on EVERY read — slow under low free RAM. This
module manages a tiny resident Go daemon that reads Windows metrics straight
from the OS API and serves them on localhost HTTP (~1 ms).

Graceful by design: if the daemon can't be built or started, callers simply
fall back to the original PowerShell path, so this is a pure speed-up with no
regression. The daemon is stdlib-only Go (no external deps); the Go toolchain is
auto-installed to %LOCALAPPDATA%\\bee on first build (kept off OneDrive).
"""
from __future__ import annotations

import atexit
import logging
import os
import subprocess
import tempfile
import threading
import time
import zipfile
from pathlib import Path

import httpx

log = logging.getLogger("bee.native")

ADDR = "127.0.0.1:8790"
BASE = f"http://{ADDR}"
_BEE_LOCAL = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "bee"
EXE = _BEE_LOCAL / "bin" / "bee-telemetry.exe"
_GO = _BEE_LOCAL / "go" / "bin" / "go.exe"
_SRC = Path(__file__).parent / "telemetry"

_proc: subprocess.Popen | None = None  # the daemon we launched (None if we reused one)
_boot_lock = threading.Lock()
_tls = threading.local()


def _client() -> httpx.Client:
    """Per-thread persistent httpx client.

    Connection reuse is the whole point: a one-shot httpx.get() pays a fresh
    TCP setup on every call (measured 270-675 ms under load on this box), while
    a pooled client is ~1-5 ms. Thread-local keeps it safe without a lock.
    """
    c = getattr(_tls, "client", None)
    if c is None:
        c = httpx.Client(timeout=1.0)
        _tls.client = c
    return c


def _create_flags() -> int:
    return 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW


def healthy(timeout: float = 0.4) -> bool:
    try:
        return _client().get(f"{BASE}/health", timeout=timeout).status_code == 200
    except Exception:
        return False


def _install_go() -> None:
    """Download + extract the Go toolchain (one-time, best-effort)."""
    import urllib.request
    v = (urllib.request.urlopen("https://go.dev/VERSION?m=text", timeout=30)
         .read().decode().splitlines()[0].strip())
    _BEE_LOCAL.mkdir(parents=True, exist_ok=True)
    zip_ = _BEE_LOCAL / "go.zip"
    url = f"https://go.dev/dl/{v}.windows-amd64.zip"
    log.info("installing Go from %s", url)
    urllib.request.urlretrieve(url, str(zip_))
    with zipfile.ZipFile(zip_) as z:
        z.extractall(_BEE_LOCAL)
    zip_.unlink(missing_ok=True)


def build(force: bool = False) -> bool:
    """Compile the Go daemon (installing Go first if needed). Best-effort."""
    if EXE.exists() and not force:
        return True
    if not _GO.exists():
        try:
            _install_go()
        except Exception as e:
            log.warning("Go install failed: %s", str(e)[:200])
    if not _GO.exists():
        return False
    EXE.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, GOROOT=str(_GO.parent.parent),
               GOCACHE=str(_BEE_LOCAL / "gocache"), CGO_ENABLED="0")
    try:
        r = subprocess.run([str(_GO), "build", "-o", str(EXE), "."],
                           cwd=str(_SRC), env=env, capture_output=True, timeout=300)
        if r.returncode != 0:
            log.warning("go build failed: %s", r.stderr.decode(errors="ignore")[:300])
            return False
        return True
    except Exception as e:
        log.warning("go build error: %s", str(e)[:200])
        return False


def _launch() -> None:
    global _proc
    _proc = subprocess.Popen([str(EXE), "-addr", ADDR],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=_create_flags())


def ensure(wait_s: float = 3.0) -> bool:
    """Ensure the daemon is up: reuse if healthy, else build + launch."""
    with _boot_lock:
        if healthy():
            return True
        if not build():
            return False
        try:
            _launch()
        except Exception as e:
            log.warning("daemon launch failed: %s", str(e)[:200])
            return False
        deadline = time.time() + wait_s
        while time.time() < deadline:
            if healthy():
                return True
            time.sleep(0.1)
        return healthy()


def start_background() -> None:
    """Build + launch the daemon on a daemon thread so it never blocks startup."""
    if healthy():
        return

    def _boot() -> None:
        try:
            ensure()
        except Exception as e:
            log.debug("native boot: %s", str(e)[:200])

    threading.Thread(target=_boot, daemon=True, name="bee-native").start()
    atexit.register(stop)


def stats(timeout: float = 0.6) -> dict | None:
    """Fast native stats, or None if the daemon is unavailable."""
    try:
        r = _client().get(f"{BASE}/stats", timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def stop() -> None:
    """Stop the daemon *if this process started it* (never kill a borrowed one)."""
    global _proc
    try:
        if _proc is not None and _proc.poll() is None:
            _proc.terminate()
    except Exception:
        pass
    finally:
        _proc = None
    c = getattr(_tls, "client", None)  # best-effort: close this thread's client
    if c is not None:
        try:
            c.close()
        except Exception:
            pass
        _tls.client = None
