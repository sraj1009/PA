# BEE full-stack launcher — runs the agent fully: text CLI + voice + all.
#
#   powershell -ExecutionPolicy Bypass -File bee-runfull.ps1
#   .\bee-runfull.ps1 my-room          # optional: custom LiveKit room
#
# Starts in one go:
#   1. Go telemetry daemon (system stats, ~1 ms)
#   2. Web UI            http://127.0.0.1:8787   (chat, /face, Live Voice join)
#   3. LiveKit voice agent (realtime two-way voice; needs keys in .env)
#   4. Browser           -> Live Voice page (join + talk)
#   5. Text REPL         in THIS console (/voice PTT works inside it too)
#
# /exit (or Ctrl-C in the console) tears the child processes down.
# Child logs: temp\bee-full-web.log, temp\bee-full-livekit.log

Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONIOENCODING = "utf-8"
python -m bee.cli full @args
