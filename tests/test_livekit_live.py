"""Live-credential verification for LiveKit Cloud (optional).

Skipped when the livekit SDK is not installed (a bare install) or no
credentials are configured (CI without .env) — creds alone are not enough,
and the skip must never become a failure (A69, 2026-10-18: a bare install
with a .env ran these and died with ModuleNotFoundError). When both are
present it proves end-to-end: config loads keys, token minting works, and the
LiveKit Cloud room-service API answers. No room is joined, no media flows —
zero agent-minutes burned.
"""
from __future__ import annotations

import asyncio

import pytest


def _live_cfg():
    from bee.config import load_config
    cfg = load_config()
    lk = cfg.livekit
    if lk.url and lk.api_key and lk.api_secret:
        return cfg
    return None


requires_livekit = pytest.mark.skipif(
    _live_cfg() is None, reason="no LiveKit credentials configured")


@requires_livekit
def test_live_token_mints():
    pytest.importorskip(
        "livekit", reason="MISSING OPTIONAL DEPENDENCY: livekit SDK — "
        "make_token builds the JWT through livekit.api")
    from bee.livekit.agent import make_token, validate_room
    cfg = _live_cfg()
    room = validate_room(cfg.livekit.room or "bee-pa")
    tok = make_token(cfg, room, identity="verify-probe")
    assert tok.count(".") == 2, "not a JWT"
    assert len(tok) > 100


@requires_livekit
def test_live_room_service_reachable():
    pytest.importorskip(
        "livekit", reason="MISSING OPTIONAL DEPENDENCY: livekit SDK — the "
        "room-service call goes through livekit.api")
    from livekit.api import LiveKitAPI
    from livekit.protocol.room import ListRoomsRequest
    cfg = _live_cfg()
    lk = cfg.livekit

    async def _list():
        async with LiveKitAPI(lk.url, lk.api_key, lk.api_secret) as api:
            return await api.room.list_rooms(ListRoomsRequest())

    rooms = asyncio.run(_list())
    got = getattr(rooms, "rooms", rooms)
    assert got is not None  # reachable + authenticated; content may be empty
