"""BEE web UI — FastAPI: chat (SSE), voice (upload -> STT -> answer -> TTS mp3), skills list.

Run:  python -m bee.cli web          (or: uvicorn bee.webapp:app --port 8787)
"""
from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from . import paths
from .agent.client import LLMClient
from .agent.context import Context
from .agent.loop import run_agent

log = logging.getLogger("bee.web")

app = FastAPI(title="BEE", version="1.0")

CTX: Context | None = None


def get_ctx() -> Context:
    global CTX
    if CTX is None:
        from .config import load_config
        cfg = load_config()
        CTX = Context(cfg, workspace=cfg.workspace, name="BEE")
        CTX.client = LLMClient(cfg)
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
async def chat(body: dict):
    task = str(body.get("task", "")).strip()
    if not task:
        return JSONResponse({"error": "empty task"}, status_code=400)
    model = body.get("model") or _default_engine_override()
    buf: list[str] = []

    def on_event(ev):
        buf.append("data: " + json.dumps(ev, ensure_ascii=False) + "\n\n")

    def gen():
        ctx = get_ctx()
        yield "data: " + json.dumps({"type": "start"}) + "\n\n"
        try:
            result = run_agent(ctx, task, on_event=on_event, model=model)
            for chunk in buf:
                yield chunk
            yield "data: " + json.dumps({"type": "result", "ok": result.ok,
                                         "model": result.model, "escalated": result.escalated,
                                         "iterations": result.iterations,
                                         "tool_calls": result.tool_calls,
                                         "output": result.output, "error": result.error},
                                        ensure_ascii=False) + "\n\n"
        except Exception as e:
            yield "data: " + json.dumps({"type": "error", "error": str(e)}, ensure_ascii=False) + "\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/voice")
async def voice(file: UploadFile = File(...)):
    """Upload audio (webm/wav/mp3) -> transcribe -> run agent -> return text (+tts mp3)."""
    if not _voice_available():
        return JSONResponse({"error": "voice STT not installed (pip install -r requirements-voice.txt)"},
                            status_code=501)
    from .voice import mic, transcribe
    ctx = get_ctx()
    suffix = Path(file.filename or "audio.webm").suffix or ".webm"
    tmp = Path(tempfile.gettempdir()) / f"bee_upload{suffix}"
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
async def engine_set(body: dict):
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
def livekit_token(body: dict):
    """Mint a 2h participant JWT for the given room (Web UI join)."""
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
def face_state():
    from .livekit.state import get_state
    return get_state()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8787)
