param([switch]$SkipOllama)

$ErrorActionPreference = "Continue"
$PROJECT = "D:\Final project\Carepilot"
$BACKEND_VENV = "$PROJECT\.venv\Scripts\python.exe"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  CAREPILOT AI — FULL STACK STARTUP" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

Write-Host ""
Write-Host "[1/5] Starting PostgreSQL..." -ForegroundColor Yellow
try {
    Get-Service postgresql-x64-18 -ErrorAction Stop | Start-Service
    Write-Host "   PostgreSQL started." -ForegroundColor Green
} catch {
    Write-Host "   Could not start PostgreSQL automatically. Start it manually in services.msc." -ForegroundColor Red
}

if (-not $SkipOllama) {
    Write-Host ""
    Write-Host "[2/5] Starting Ollama..." -ForegroundColor Yellow
    try {
        Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden -ErrorAction Stop
        Start-Sleep -Seconds 3
        Write-Host "   Ollama server started." -ForegroundColor Green
    } catch {
        Write-Host "   Ollama not found or failed to start. System will use NVIDIA API fallback." -ForegroundColor Red
    }
} else {
    Write-Host ""
    Write-Host "[2/5] Skipping Ollama (NVIDIA API fallback will be used)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "[3/5] Starting FastAPI Backend (port 8000)..." -ForegroundColor Yellow
$backend = Start-Process -FilePath $BACKEND_VENV -ArgumentList "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8000", "--reload" -WorkingDirectory $PROJECT -PassThru -WindowStyle Normal
Write-Host "   Backend PID: $($backend.Id)" -ForegroundColor Green

Write-Host "   Waiting for backend to be ready..."
for ($i=0; $i -lt 15; $i++) {
    Start-Sleep -Seconds 2
    try {
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8000/docs" -TimeoutSec 3 -ErrorAction Stop
        Write-Host "   Backend ready at http://127.0.0.1:8000/docs" -ForegroundColor Green
        break
    } catch {
        if ($i -eq 14) {
            Write-Host "   Backend not yet ready — check logs." -ForegroundColor Red
        }
    }
}

Write-Host ""
Write-Host "[4/5] Starting Doctor Dashboard (port 5173)..." -ForegroundColor Yellow
Start-Process -FilePath "npm" -ArgumentList "run", "dev" -WorkingDirectory "$PROJECT\doctor-dashboard" -PassThru -WindowStyle Normal
Write-Host "   Doctor Dashboard: http://localhost:5173" -ForegroundColor Green

Write-Host ""
Write-Host "[5/5] Starting Patient App (port 8081)..." -ForegroundColor Yellow
Start-Process -FilePath "npx" -ArgumentList "expo", "start", "--web" -WorkingDirectory "$PROJECT\patient-app" -PassThru -WindowStyle Normal
Write-Host "   Patient App: http://localhost:8081" -ForegroundColor Green

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  ALL SERVICES STARTED" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Backend API:    http://127.0.0.1:8000/docs" -ForegroundColor Green
Write-Host "  Doctor Dash:    http://localhost:5173" -ForegroundColor Green
Write-Host "  Patient App:    http://localhost:8081" -ForegroundColor Green
Write-Host ""
Write-Host "  To stop: Close each terminal window" -ForegroundColor Yellow
Write-Host "  Or run: taskkill /F /IM uvicorn.exe /IM node.exe" -ForegroundColor Yellow