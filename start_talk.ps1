# ============================================================
#  BEE "Talk" - live realtime voice + face
#  (mirrors fullstack-agent's "Talk" shortcut: voice + face together)
#
#  What it does:
#    1. starts the web server (serves /face + /livekit + /face/state)
#    2. opens your browser on the Live-Voice join page and the face
#    3. runs the LiveKit voice agent in THIS window (foreground)
#
#  Stop: press Ctrl-C here - the web server is stopped with it.
#
#  Requires:
#    python -m pip install -r requirements-livekit.txt
#    LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET  in  .env
# ============================================================
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$port = 8787
$room = "bee-pa"

Write-Host ""
Write-Host "  BEE TALK - live voice + face" -ForegroundColor Cyan
Write-Host "  room: $room   (change with: python -m bee.cli livekit --room <roomname>)" -ForegroundColor DarkGray
Write-Host "  stop:  Ctrl-C in this window." -ForegroundColor DarkGray
Write-Host ""

# 1) web server in a hidden background window (engine is the persisted default)
$web = Start-Process -FilePath "python" `
        -ArgumentList @("-m", "bee.cli", "web", "--port", $port) `
        -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru

# 2) let the server come up, then open the browser (two tabs)
Start-Sleep -Seconds 3
Start-Process "http://127.0.0.1:$port/livekit"   # join room + mic + talk
Start-Process "http://127.0.0.1:$port/face"      # full-screen visualizer (F = fullscreen)

# 3) LiveKit voice agent in the foreground (Ctrl-C stops it + the web server)
try {
    python -m bee.cli livekit --room $room
}
finally {
    Write-Host ""
    Write-Host "  stopping web server..." -ForegroundColor DarkGray
    Stop-Process -Id $web.Id -Force -ErrorAction SilentlyContinue
}
Write-Host "  Talk session ended." -ForegroundColor Cyan
