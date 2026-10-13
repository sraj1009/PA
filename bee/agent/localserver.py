"""Start the local model server when the user expects it and it is not running.

BEE's identity is the local `bee4b` model, but nothing in the app could bring
that server up: if Ollama was not already running (a reboot, or it simply not
being in the startup group) every local task degraded to the cloud tier or to
deterministic mode, and the fine-tuned model was never consulted. This mirrors
`bee/native`: launch on a background thread at boot, never block startup, and
treat a server BEE did not start as untouchable.

It starts the *server*, not the model — `keep_alive` still governs when the
weights load — and a failed launch is a log line plus `status()`, never an
exception that reaches the user.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
import time
from urllib.parse import urlparse

import httpx

log = logging.getLogger("bee.localserver")

_attempted = threading.Event()   # a launch has been tried (once per process)
_ready = threading.Event()       # the server answered /api/tags after that try
_lock = threading.Lock()
_err = ""                        # why the launch failed, for the health surface


def _base(cfg) -> str:
    return str(getattr(cfg.ollama, "base_url", "") or "").rstrip("/")


def reachable(cfg, timeout: float = 0.8) -> bool:
    """Is the server already answering? Same probe `client.ollama_up()` uses."""
    try:
        return httpx.get(f"{_base(cfg)}/api/tags", timeout=timeout).status_code == 200
    except Exception:
        return False


def _model_present(cfg, timeout: float = 2.0) -> bool:
    """Is the configured model actually pulled? A server with no `bee4b` answers
    /api/tags happily and then 404s on every call, so the two are reported
    separately — 'ollama up' was never the whole question."""
    want = (getattr(cfg.ollama, "model", "") or "").split("/", 1)[-1]
    try:
        names = [m.get("name", "") for m in
                 httpx.get(f"{_base(cfg)}/api/tags", timeout=timeout)
                 .json().get("models", [])]
    except Exception:
        return False
    return any(n == want or n.split(":")[0] == want.split(":")[0] for n in names)


def _is_local(cfg) -> bool:
    """Only ever start a server on this machine — a remote or ollama-cloud base
    URL is somebody else's process, and `ollama serve` would not serve it."""
    host = (urlparse(_base(cfg)).hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "0.0.0.0", "::1", "")


def exe_path() -> str | None:
    """Where the `ollama` binary lives: PATH first, then the two install dirs."""
    found = shutil.which("ollama")
    if found:
        return found
    local = os.environ.get("LOCALAPPDATA") or ""
    for cand in (os.path.join(local, "Programs", "Ollama", "ollama.exe"),
                 r"C:\Program Files\Ollama\ollama.exe"):
        if cand and os.path.exists(cand):
            return cand
    return None


def _child_env(cfg) -> dict:
    """Bind the server to the port BEE is configured to talk to. Without this a
    non-default `ollama.base_url` (or a second Ollama) would make the launch look
    like a failure: the child would sit on 11434 while BEE polled somewhere else."""
    env = dict(os.environ)
    port = urlparse(_base(cfg)).port
    if port:
        env["OLLAMA_HOST"] = f"127.0.0.1:{port}"
    return env


def _launch(cfg) -> None:
    exe = exe_path()
    if not exe:
        raise FileNotFoundError("ollama binary not on PATH or in the known install dirs")
    # Detached and window-less: the server must outlive BEE, and must never flash
    # a console on the user's desktop.
    kwargs = dict(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                  env=_child_env(cfg))
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000      # CREATE_NO_WINDOW
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen([exe, "serve"], **kwargs)


def wait(cfg, timeout: float = 5.0) -> bool:
    """Block until the server answers, at most `timeout` seconds."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if reachable(cfg):
            return True
        time.sleep(0.15)
    return reachable(cfg)


def _boot(cfg, wait_s: float) -> None:
    global _err
    try:
        _launch(cfg)
        if wait(cfg, wait_s):
            _ready.set()
            log.info("local model server is up")
            if not _model_present(cfg):
                log.warning("ollama is up but %r is not pulled — run `ollama pull %s`",
                            cfg.ollama.model, cfg.ollama.model)
        else:
            _err = f"launched but not answering within {wait_s:g}s"
            log.warning("ollama autostart: %s", _err)
    except Exception as e:
        _err = f"{type(e).__name__}: {str(e)[:160]}"
        log.warning("ollama autostart failed: %s", _err)
    finally:
        _attempted.set()


def start_background(cfg, wait_s: float = 20.0) -> bool:
    """Bring Ollama up if it is not already. Returns True when the server is
    reachable now (was already up, or came up fast). Never raises, never blocks."""
    if not getattr(cfg.ollama, "autostart", True) or not _is_local(cfg):
        return False
    with _lock:
        if reachable(cfg):
            _ready.set()
            _attempted.set()
            return True
        if _attempted.is_set():     # one attempt per process; the rest is the user's call
            return False
        threading.Thread(target=_boot, args=(cfg, wait_s), daemon=True,
                         name="bee-ollama").start()
    return False


def grace(cfg, timeout: float = 1.5) -> bool:
    """For the router: a launch is in flight, so give the server the moment it
    needs instead of degrading the task on a lookup that merely raced it."""
    if not _attempted.is_set() or _ready.is_set():
        return False
    ok = wait(cfg, timeout)
    if ok:
        _ready.set()
    return ok


def status() -> dict:
    """For `/health` and the web status panel: what the autostart actually did.
    There is deliberately no `stop()` — `ollama serve` is the user's server: other
    apps may share it, and unloading the weights costs the next startup seconds."""
    return {"attempted": _attempted.is_set(), "ready": _ready.is_set(),
            "error": _err}


def offline_hint(cfg) -> str:
    """What to tell a user whose server is not answering. BEE can start it now, so
    the bare 'start Ollama' was wrong advice half the time."""
    if not getattr(cfg.ollama, "autostart", True):
        return "autostart is off — start Ollama or set ollama.autostart: true"
    st = status()
    if st["error"]:
        return f"autostart failed: {st['error']}"
    if st["attempted"]:
        return "launching — give it a few seconds"
    return "will be started on the next BEE launch (ollama.autostart)"


def reset() -> None:
    """Forget the one-attempt state (tests, or a user who starts Ollama by hand
    and wants BEE to retry)."""
    global _err
    _attempted.clear()
    _ready.clear()
    _err = ""
