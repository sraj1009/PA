"""BEE web UI — FastAPI: chat (SSE), voice (upload -> STT -> answer -> JSON), skills list.

Security (Phase 1): every stateful endpoint (chat, voice, engine set, livekit
token mint, face state) requires a bearer token. The token is env-fixed
(BEE_WEB_TOKEN) or auto-generated once per server start (printed in the
console + saved to temp/web_token.txt, which is git-ignored). Static pages
and read-only status endpoints stay open.

Run:  python -m bee.cli web          (or: uvicorn bee.webapp:app --port 8787)
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import queue
import secrets
import tempfile
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from . import paths
from .agent.context import Context
from .agent.loop import run_agent

log = logging.getLogger("bee.web")

app = FastAPI(title="BEE", version="1.0")

CTX: Context | None = None

# ------------------------------------------------------------------- auth
_TOKEN: str | None = None
_TOKEN_FILE = paths.PROJECT_ROOT / "temp" / "web_token.txt"


def _resolve_token() -> str:
    """Bearer token for the web UI. Precedence:
    1. BEE_WEB_TOKEN env (operator-fixed, e.g. in .env)
    2. previous start's token file (temp/web_token.txt)
    3. freshly generated (saved to that file, printed once by the CLI)
    This is a LOCAL session credential for a loopback server — not a cloud
    secret — but it still gates the full agent, so it is never logged."""
    global _TOKEN
    if _TOKEN:
        return _TOKEN
    env = (os.environ.get("BEE_WEB_TOKEN") or "").strip()
    if env:
        _TOKEN = env
        return _TOKEN
    if _TOKEN_FILE.exists():
        t = _TOKEN_FILE.read_text(encoding="utf-8").strip()
        if t:
            _TOKEN = t
            return _TOKEN
    _TOKEN = secrets.token_hex(16)
    try:
        _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        _TOKEN_FILE.write_text(_TOKEN + "\n", encoding="utf-8")
    except Exception:
        pass
    return _TOKEN


def reset_token_for_tests() -> None:
    global _TOKEN
    _TOKEN = None


def require_auth(request: Request) -> None:
    """401 unless Authorization: Bearer <token> (or ?token=) matches."""
    tok = _resolve_token()
    auth = request.headers.get("authorization", "")
    provided = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    if not provided:
        provided = request.query_params.get("token", "")
    if not provided or not hmac.compare_digest(provided, tok):
        raise HTTPException(
            status_code=401,
            detail="unauthorized — send Authorization: Bearer <token> "
                   "(token: server console / temp/web_token.txt / BEE_WEB_TOKEN)")


def get_ctx() -> Context:
    global CTX
    if CTX is None:
        from .config import load_config
        from .agent.context import create_context
        cfg = load_config()
        CTX = create_context(cfg)
        try:
            from . import scheduler
            scheduler.start_scheduler(CTX, cfg)
        except Exception as e:
            log.warning("scheduler not started: %s", e)
    return CTX


@app.get("/", response_class=HTMLResponse)
def index():
    return (Path(__file__).parent / "web" / "index.html").read_text(encoding="utf-8")


@app.get("/health")
def health():
    ctx = get_ctx()
    models = ctx.client.models_list()
    return {"ok": True, "ollama_models": models,
            "voice_stt": _voice_available()}


def _voice_available() -> bool:
    try:
        from .voice import transcribe
        return transcribe.available()
    except Exception:
        return False


def _default_engine_override() -> str | None:
    from .agent import engines
    return engines.override_for(engines.load_engine())


@app.post("/chat")
async def chat(body: dict, request: Request):
    require_auth(request)
    task = str(body.get("task", "")).strip()
    if not task:
        return JSONResponse({"error": "empty task"}, status_code=400)
    model = body.get("model") or _default_engine_override()

    def sse(ev) -> str:
        return "data: " + json.dumps(ev, ensure_ascii=False) + "\n\n"

    def gen():
        # Phase 4: GENUINE streaming. The kernel runs in a worker thread and
        # every event (tool_start, token, verify, ...) is pushed through a
        # queue the moment it happens — the first LLM token reaches the
        # browser before the task is finished (no buffering of the reply).
        ctx = get_ctx()
        # Phase 2: web tasks run through the kernel too (state, verification,
        # receipts, session continuity). The web UI is unattended: 'ask'
        # decisions AUTO-DENY (fail closed) instead of blocking on input().
        if ctx.kernel is None:
            from .kernel import AgentKernel
            ctx.kernel = AgentKernel(ctx, approver=lambda tool, args, reason: False)
        q: "queue.Queue" = queue.Queue()

        def on_event(ev):
            q.put(ev)

        def worker():
            try:
                result = ctx.kernel.run(task, session_id=str(body.get("session") or "web"),
                                        on_event=on_event, model=model,
                                        # truthy on_token switches the loop to
                                        # genuine chat_stream; token events
                                        # also arrive live through on_event
                                        on_token=lambda _t: None)
                q.put({"type": "result", "ok": result.ok,
                       "model": result.model, "escalated": result.escalated,
                       "iterations": result.iterations,
                       "tool_calls": result.tool_calls,
                       "verified": result.verification.verdict,
                       "output": result.output, "error": result.error})
            except Exception as e:
                q.put({"type": "error", "error": f"{type(e).__name__}: {e}"})
            finally:
                q.put(None)

        th = threading.Thread(target=worker, daemon=True, name="BeeWebChat")
        yield sse({"type": "start"})
        th.start()
        while True:
            try:
                ev = q.get(timeout=120)
            except queue.Empty:
                yield sse({"type": "timeout", "error": "task stalled — no events for 120s"})
                break
            if ev is None:
                break
            yield sse(ev)
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/voice")
async def voice(request: Request, file: UploadFile = File(...)):
    """Upload audio (webm/wav/mp3) -> transcribe -> run agent -> return JSON (transcript + answer text)."""
    require_auth(request)
    if not _voice_available():
        return JSONResponse({"error": "voice STT not installed (pip install -r requirements-voice.txt)"},
                            status_code=501)
    from .voice import mic, transcribe
    ctx = get_ctx()
    suffix = Path(file.filename or "audio.webm").suffix or ".webm"
    tmp = Path(tempfile.gettempdir()) / f"bee_upload_{uuid.uuid4().hex}{suffix}"
    tmp.write_bytes(await file.read())
    try:
        if suffix in (".wav",):
            audio, _ = mic.read_wav(tmp, target_rate=16000)
        else:
            # let ffmpeg convert anything ffmpeg understands
            wav = tmp.with_suffix(".wav")
            import subprocess, shutil
            if not shutil.which("ffmpeg"):
                return JSONResponse({"error": "ffmpeg required to decode non-wav uploads"}, status_code=501)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(tmp),
                            "-ar", "16000", "-ac", "1", "-f", "wav", str(wav)], timeout=60)
            audio, _ = mic.read_wav(wav, target_rate=16000)
        text = transcribe.transcribe_audio(audio, model=ctx.cfg.voice.model,
                                           device=ctx.cfg.voice.device,
                                           compute_type=ctx.cfg.voice.compute_type)
    except Exception as e:
        log.exception("voice endpoint failed")
        return JSONResponse({"error": f"voice pipeline failed: {str(e)[:200]}"}, status_code=500)
    finally:
        try:
            tmp.unlink()
        except Exception:
            pass
    if not text:
        return {"transcript": "", "output": "(no speech detected)"}
    result = run_agent(ctx, text)
    return {"transcript": text, "output": result.output, "ok": result.ok,
            "model": result.model, "escalated": result.escalated}


@app.get("/engine")
def engine_get():
    from .agent import engines
    saved = engines.load_engine() or "hybrid"
    return {"current": saved,
            "engines": [{"name": k, "label": v["label"], "override": v["override"]}
                        for k, v in engines.ENGINES.items()]}


@app.post("/engine")
async def engine_set(body: dict, request: Request):
    require_auth(request)
    from .agent import engines
    name = str(body.get("engine", "")).strip()
    if name not in engines.ENGINES:
        return JSONResponse({"error": f"unknown engine: {name}"}, status_code=400)
    engines.save_engine(name)
    if CTX is not None:
        CTX.model_override = engines.override_for(name)
    return {"ok": True, "current": name, "override": engines.override_for(name)}


@app.get("/skills")
def skills():
    out = []
    for md in sorted(paths.SKILLS_DIR.glob("*/SKILL.md")):
        body = md.read_text(encoding="utf-8", errors="ignore")
        desc = next((ln.split(":", 1)[1].strip() for ln in body.splitlines()
                     if ln.lower().startswith("description:")), "")
        out.append({"name": md.parent.name, "description": desc})
    return {"skills": out}


# ---------------------------------------------------------------- Live voice
def _web_dir() -> Path:
    return Path(__file__).parent / "web"


@app.get("/livekit", response_class=HTMLResponse)
def livekit_page():
    return (_web_dir() / "livekit.html").read_text(encoding="utf-8")


@app.get("/livekit/status")
def livekit_status():
    cfg = get_ctx().cfg
    lk = cfg.livekit
    return {"configured": bool(lk.url and lk.api_key and lk.api_secret),
            "room": lk.room, "url": lk.url or "", "enabled": lk.enabled}


@app.post("/livekit/token")
def livekit_token(body: dict, request: Request):
    """Mint a 2h participant JWT for the given room (Web UI join)."""
    require_auth(request)
    ctx = get_ctx()
    room = str(body.get("room", "")).strip()
    if not room:
        return JSONResponse({"error": "room is required"}, status_code=400)
    try:
        from .livekit.agent import make_token, validate_room
        room = validate_room(room)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    if not (ctx.cfg.livekit.url and ctx.cfg.livekit.api_key and ctx.cfg.livekit.api_secret):
        return JSONResponse({"error": "livekit not configured (.env: LIVEKIT_URL / "
                                      "LIVEKIT_API_KEY / LIVEKIT_API_SECRET)"}, status_code=503)
    try:
        return {"token": make_token(ctx.cfg, room), "url": ctx.cfg.livekit.url,
                "room": room}
    except Exception as e:
        log.exception("livekit token mint failed")
        return JSONResponse({"error": f"token mint failed: {str(e)[:200]}"}, status_code=500)


# ---------------------------------------------------------------- the face
@app.get("/face", response_class=HTMLResponse)
def face_page():
    return (_web_dir() / "face.html").read_text(encoding="utf-8")


@app.get("/face/state")
def face_state(request: Request):
    require_auth(request)
    from .livekit.state import get_state
    return get_state()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8787)
