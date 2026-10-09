# =====================================================================
# Chennalink Unified Startup Script for Windows PowerShell
# =====================================================================

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot

Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "            Starting Chennalink Environment         " -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan

# 1. Verify Virtual Environment
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$VenvUvicorn = Join-Path $ProjectRoot ".venv\Scripts\uvicorn.exe"
$VenvCli = Join-Path $ProjectRoot ".venv\Scripts\chennalink.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Error "Virtual environment not found at .venv. Please create it or install dependencies first."
    exit 1
}

# 2. Check if Backend is already running on port 8000
$portInUse = $false
try {
    $conn = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
    if ($conn) { $portInUse = $true }
} catch {
    # Get-NetTCPConnection might fail on some Windows configurations; fallback to Test-NetConnection
    $t = Test-NetConnection -ComputerName 127.0.0.1 -Port 8000 -WarningAction SilentlyContinue
    if ($t.TcpTestSucceeded) { $portInUse = $true }
}

if ($portInUse) {
    Write-Host "[✓] Backend already listening on http://127.0.0.1:8000" -ForegroundColor Green
} else {
    Write-Host "[→] Launching FastAPI backend on http://127.0.0.1:8000..." -ForegroundColor Yellow
    $backendCmd = "Set-Location '$ProjectRoot'; & '$VenvUvicorn' backend.main:app --host 127.0.0.1 --port 8000 --reload"
    Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $backendCmd -WindowStyle Normal
    
    # 3. Wait for Backend Readiness (up to 15 seconds)
    Write-Host "[→] Waiting for backend readiness..." -NoNewline
    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        try {
            $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8000/web/" -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
            if ($resp.StatusCode -eq 200) {
                $ready = $true
                break
            }
        } catch {}
        Write-Host "." -NoNewline
    }
    Write-Host ""
    if (-not $ready) {
        Write-Warning "Backend is taking longer than expected to report ready. Proceeding anyway..."
    } else {
        Write-Host "[✓] Backend is online and responding." -ForegroundColor Green
    }
}

# 4. Launch CLI Client in a dedicated interactive window
Write-Host "[→] Launching Chennalink CLI in a separate terminal window..." -ForegroundColor Yellow
$cliCmd = "Set-Location '$ProjectRoot'; & '$VenvPython' -m chennalink"
Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $cliCmd -WindowStyle Normal

# 5. Open Web Client in Default Web Browser
$WebUrl = "http://127.0.0.1:8000/web/"
Write-Host "[→] Opening Web Client in default browser: $WebUrl" -ForegroundColor Yellow
Start-Process $WebUrl

Write-Host "=====================================================" -ForegroundColor Green
Write-Host " Chennalink services are up and running!" -ForegroundColor Green
Write-Host " - Backend API:  http://127.0.0.1:8000"
Write-Host " - Web Client:   http://127.0.0.1:8000/web/"
Write-Host " - CLI Client:   Active in separate PowerShell window"
Write-Host "=====================================================" -ForegroundColor Green
