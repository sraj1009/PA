# BEE one-shot setup (Windows). Run:  powershell -ExecutionPolicy Bypass -File setup.ps1
$ErrorActionPreference = "Continue"
Write-Host "=== BEE setup ===" -ForegroundColor Cyan

# 1) Python (try 'python' first; 'py' launcher is optional)
$pyCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pyCmd) { $pyCmd = Get-Command py -ErrorAction SilentlyContinue }
if ($pyCmd) { & $pyCmd.Source --version | Out-Null } else { Write-Host "[!] Python 3.10+ not found on PATH." -ForegroundColor Red }

# 2) Ollama
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollama) {
    Write-Host "[i] Ollama not found. Downloading installer..." -ForegroundColor Yellow
    Invoke-WebRequest "https://ollama.com/download/OllamaSetup.exe" -OutFile "$env:TEMP\OllamaSetup.exe"
    Start-Process "$env:TEMP\OllamaSetup.exe" -ArgumentList "/VERYSILENT"
    Write-Host "[i] Ollama installer started. Restart terminal after install." -ForegroundColor Yellow
} else {
    Write-Host "[ok] Ollama present. Pulling models..." -ForegroundColor Green
    & ollama pull qwen2.5:3b
    & ollama create bee4b -f models\bee4b.Modelfile
    & ollama pull nomic-embed-text
}

# 3) Python deps
Write-Host "[i] Installing core deps (pip install -r requirements.txt)..." -ForegroundColor Yellow
python -m pip install -r requirements.txt
Write-Host "[i] Installing voice deps (pip install -r requirements-voice.txt)..." -ForegroundColor Yellow
python -m pip install -r requirements-voice.txt
Write-Host "[i] Installing live-voice deps (pip install -r requirements-livekit.txt)..." -ForegroundColor Yellow
python -m pip install -r requirements-livekit.txt

# 4) Docker sandbox (optional - the daemon must be running to build)
$docker = Get-Command docker -ErrorAction SilentlyContinue
if ($docker) {
    docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[!] Docker CLI found but the daemon is not running. Start Docker Desktop and re-run setup." -ForegroundColor Yellow
    } else {
        docker image inspect bee-sandbox:latest *> $null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[ok] bee-sandbox:latest already built - skipping." -ForegroundColor Green
        } else {
            Write-Host "[i] Building ML sandbox image (bee-sandbox:latest) - FIRST build takes 10-20 min (torch + ML stack)..." -ForegroundColor Yellow
            # Build from a TEMP copy: Docker Desktop's WSL2 backend can read
            # OneDrive files as truncated cloud placeholders, which fails with
            # "invalid file request Dockerfile". A local temp dir has no reparse
            # points and builds cleanly.
            $buildDir = Join-Path $env:TEMP "bee-sandbox-build"
            if (Test-Path $buildDir) { Remove-Item $buildDir -Recurse -Force }
            Copy-Item .\sandbox $buildDir -Recurse
            docker build -t bee-sandbox:latest $buildDir
            $rc = $LASTEXITCODE
            Remove-Item $buildDir -Recurse -Force -ErrorAction SilentlyContinue
            if ($rc -ne 0) { Write-Host "[!] Sandbox build failed (see log above). Sandbox stays disabled - everything else works without it." -ForegroundColor Yellow }
        }
    }
} else {
    Write-Host "[!] Docker not found - sandbox disabled (set sandbox.enabled=false in config.yaml)." -ForegroundColor Yellow
}

# 4b) Native telemetry daemon (Go, stdlib-only) - fast system stats (~1 ms vs ~500 ms WMI)
Write-Host "[i] Building native telemetry daemon (Go)..." -ForegroundColor Yellow
try {
    & "$PSScriptRoot\bee\native\build.ps1"
    Write-Host "[ok] native telemetry ready." -ForegroundColor Green
} catch {
    Write-Host "[!] Native build skipped (BEE falls back to PowerShell stats). Run: bee\native\build.ps1" -ForegroundColor Yellow
}

# 5) Environment check
Write-Host ""
python -m bee.cli setup

Write-Host "`n=== Done. Start BEE:  python -m bee.cli  (or: python bee.py) ===" -ForegroundColor Cyan
Write-Host "    Voice mode:      python -m bee.cli voice   (or /voice in the REPL)" -ForegroundColor Cyan
Write-Host "    Live voice+face: .\start_talk.ps1   (or: python -m bee.cli livekit)" -ForegroundColor Cyan
Write-Host "    Web UI:          python -m bee.cli web   ->  http://127.0.0.1:8787" -ForegroundColor Cyan
