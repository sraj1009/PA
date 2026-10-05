"""LiveKit realtime voice — BEE's live body ('backtalk').

Free-tier LiveKit Cloud: the agent joins a room over WebRTC, hears you
(silero STT, local), thinks with the full BEE pipeline (fast paths, engine
routing, tools, guard, persona, memory) and speaks back (silero TTS, local).

Run the agent:   python -m bee.cli livekit [--room bee-pa]
Join as a user:  Web UI -> "Live Voice" tab -> Join (or any LiveKit client).
"""
