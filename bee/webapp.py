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
import time
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
    # Compare BYTES: hmac.compare_digest raises TypeError on strings that
    # contain non-ASCII, so an odd-shaped (or deliberately malformed) header
    # used to answer 500 instead of 401. A 500 also leaks that the handler
    # blew up rather than that the credential was wrong.
    if not provided:
        raise HTTPException(
            status_code=401,
            detail="unauthorized — send Authorization: Bearer <token> "
                   "(token: server console / temp/web_token.txt / BEE_WEB_TOKEN)")
    ok = hmac.compare_digest(
        provided.encode("utf-8", "replace"), tok.encode("utf-8", "replace"))
    if not ok:
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
        # The web process is UNATTENDED by definition: no human is at the
        # stdin. guard mode "cli" would make a guard 'ask' call input() from
        # a worker thread (hangs the web worker, or worse, steals a keypress
        # typed into the console) — fail closed instead (audit 2026-10-06).
        # /chat is unaffected: its kernel already auto-denies 'ask'.
        CTX = create_context(cfg, guard_mode="unattended")
        try:
            from . import scheduler
            scheduler.start_automation(CTX, cfg)
        except Exception as e:
            log.warning("automation not started: %s", e)
    return CTX


@app.get("/", response_class=HTMLResponse)
def index():
    return _page("index.html")


@app.get("/health")
def health():
    ctx = get_ctx()
    models = ctx.client.models_list()
    return {"ok": True, "ollama_models": models,
            "voice_stt": _voice_available()}


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    """Live monitoring page — rendered per request from the current metrics.

    `python -m bee.cli dashboard` writes a SNAPSHOT file, so opening it later
    showed whatever was true when it was generated (audit item L3/M8: the
    dashboard could not show live data). This route builds the same HTML on every
    request and tells the browser to re-fetch, so the numbers move while you
    watch. Gated like the other data surfaces: the content IS usage data."""
    require_auth(request)
    from .monitor import dashboard as dash
    return HTMLResponse(content=dash.render(refresh_seconds=30),
                        headers={"Cache-Control": "no-store"})


def _voice_available() -> bool:
    try:
        from .voice import transcribe
        return transcribe.available()
    except Exception:
        return False


def _default_engine_override() -> str | None:
    from .agent import engines
    return engines.override_for(engines.load_engine())


@app.post("/cancel")
def cancel_task(request: Request):
    """Stop the ACTIVE task. The REPL has always had this (Ctrl-C / 'stop') and
    the voice engine has it (barge-in / "Stop."); the web UI had no route at all,
    so a browser user could only watch a runaway task finish.

    Safe because cancellation is kernel-owned and task-scoped: the kernel clears
    the cancel event at every new task start, so this can never poison the next
    task (audit item N4).
    """
    require_auth(request)
    ctx = get_ctx()
    kernel = getattr(ctx, "kernel", None)
    if kernel is None:
        return JSONResponse({"cancelled": False, "running": False,
                             "reason": "no agent has run in this process yet"})
    active = getattr(kernel, "_active_task", None)
    kernel.cancel()
    return {"cancelled": True, "running": active is not None,
            "task_id": getattr(active, "id", "") or "",
            "note": "" if active is not None else
                    "no task was running — nothing to stop"}


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
    # Audit item 1: /voice runs through the SAME kernel as /chat (capability
    # gate, receipts, verification, telemetry) instead of raw run_agent.
    k = get_kernel(ctx)
    tr = k.run(text, session_id="voice")
    res = tr.agent_result
    return {"transcript": text, "output": tr.output, "ok": tr.ok,
            "model": res.model if res else None,
            "escalated": res.escalated if res else False}


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
    from .evals.skillgate import read_meta
    out = []
    for md in sorted(paths.SKILLS_DIR.glob("*/SKILL.md")):
        body = md.read_text(encoding="utf-8", errors="ignore")
        desc = next((ln.split(":", 1)[1].strip() for ln in body.splitlines()
                     if ln.lower().startswith("description:")), "")
        m = read_meta(md.parent.name)
        out.append({"name": md.parent.name, "description": desc,
                    "version": m.get("version", 1), "status": m.get("status", "active")})
    return {"skills": out}


# ---------------------------------------------------------------- Live voice
def _web_dir() -> Path:
    return Path(__file__).parent / "web"


def _page(name: str) -> HTMLResponse:
    """Serve a bundled page with no-store.

    The face/kiosk tab and the chat tab stay open for days; without a cache
    directive an upgrade leaves them running the OLD page (which is how a fixed
    UI bug can appear to survive its own fix)."""
    return HTMLResponse(content=(_web_dir() / name).read_text(encoding="utf-8"),
                        headers={"Cache-Control": "no-store"})


@app.get("/livekit", response_class=HTMLResponse)
def livekit_page():
    return _page("livekit.html")


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
# Live-voice state lives IN MEMORY here (the webapp is the single reader);
# the agent process pushes each transition to /livekit/state (bearer auth).
# No temp-JSON file: nothing survives a webapp restart, so a dead agent can
# no longer masquerade as a live one — /face/state reports age_s instead.
_LK_STATE = {"state": "idle", "last_user": "", "last_reply": "", "engine": "",
             "ts": 0.0, "seq": 0}
_LK_LOCK = threading.Lock()


def _livekit_snapshot() -> dict:
    with _LK_LOCK:
        out = dict(_LK_STATE)
    ts = out.get("ts")
    out["age_s"] = round(max(0.0, time.time() - float(ts)), 1) if ts else None
    return out


@app.get("/face", response_class=HTMLResponse)
def face_page():
    return _page("face.html")


@app.get("/face/state")
def face_state(request: Request):
    require_auth(request)
    return _livekit_snapshot()


@app.post("/livekit/state")
def livekit_state_push(body: dict, request: Request):
    """Agent -> web UI state push (single writer = the live voice process)."""
    require_auth(request)
    with _LK_LOCK:
        _LK_STATE["state"] = str(body.get("state") or "idle")[:32]
        if body.get("last_user"):
            _LK_STATE["last_user"] = str(body["last_user"])[:300]
        if body.get("last_reply"):
            _LK_STATE["last_reply"] = str(body["last_reply"])[:600]
        if body.get("engine"):
            _LK_STATE["engine"] = str(body["engine"])[:64]
        _LK_STATE["ts"] = time.time()
        _LK_STATE["seq"] = int(body.get("seq") or _LK_STATE.get("seq", 0) + 1)
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8787)
