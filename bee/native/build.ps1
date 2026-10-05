# ============================================================
#  Build BEE's native telemetry daemon (Go, standard library only).
#  - Installs the Go toolchain to %LOCALAPPDATA%\bee if missing.
#  - Compiles bee\native\telemetry\main.go -> %LOCALAPPDATA%\bee\bin\bee-telemetry.exe
#  (Everything kept OFF OneDrive to avoid sync/lock issues.)
#  Run:  powershell -ExecutionPolicy Bypass -File bee\native\build.ps1
# ============================================================
$ErrorActionPreference = "Stop"
$local = Join-Path $env:LOCALAPPDATA "bee"
$goRoot = Join-Path $local "go"
$goExe  = Join-Path $goRoot "bin\go.exe"
$binDir = Join-Path $local "bin"

# 1) ensure Go
if (-not (Test-Path $goExe)) {
    Write-Host "[i] Installing Go toolchain -> $goRoot" -ForegroundColor Yellow
    New-Item -ItemType Directory -Force -Path $local | Out-Null
    $v = ((Invoke-RestMethod "https://go.dev/VERSION?m=text") -split "`n")[0].Trim()
    $zip = Join-Path $local "go.zip"
    $ProgressPreference = 'SilentlyContinue'
    Invoke-WebRequest "https://go.dev/dl/$v.windows-amd64.zip" -OutFile $zip -UseBasicParsing
    Expand-Archive $zip $local -Force
    Remove-Item $zip
    Write-Host "[v] Go installed: " -NoNewline; & $goExe version
}

# 2) build the daemon (stdlib only, CGO off -> self-contained exe)
New-Item -ItemType Directory -Force -Path $binDir | Out-Null
$out = Join-Path $binDir "bee-telemetry.exe"
$env:GOROOT = $goRoot
$env:GOCACHE = (Join-Path $local "gocache")
$env:CGO_ENABLED = "0"
Push-Location $PSScriptRoot/telemetry
try {
    & $goExe build -o $out .
    if ($LASTEXITCODE -ne 0) { throw "go build failed (rc=$LASTEXITCODE)" }
} finally { Pop-Location }

Write-Host "[v] Built: $out" -ForegroundColor Green

# 3) quick smoke test
$p = Start-Process $out -ArgumentList "-addr","127.0.0.1:8799" -WindowStyle Hidden -PassThru
Start-Sleep -Milliseconds 700
try {
    $s = Invoke-RestMethod "http://127.0.0.1:8799/stats"
    Write-Host ("[v] stats: " + ($s | ConvertTo-Json -Compress)) -ForegroundColor Cyan
} finally { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
