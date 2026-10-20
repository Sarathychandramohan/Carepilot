@echo off
setlocal enabledelayedexpansion

set PROJECT=D:\Final project\Carepilot
set BACKEND_VENV=%PROJECT%\.venv\Scripts\python.exe

echo ========================================
echo   CAREPILOT AI - FULL STACK STARTUP
echo ========================================
echo.

echo [1/5] Starting PostgreSQL...
net start postgresql-x64-18 >nul 2>&1
if errorlevel 1 (
    echo   Could not start PostgreSQL automatically. Start it manually in services.msc.
) else (
    echo   PostgreSQL started.
)

echo.
echo [2/5] Skipping Ollama --- using NVIDIA API fallback

echo.
echo [3/5] Starting FastAPI Backend (port 8000)...
start "Backend" cmd /c "%BACKEND_VENV% -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload"
echo   Backend starting in separate window.

echo   Waiting for backend to be ready...
for /L %%i in (1,1,15) do (
    timeout /t 2 >nul
    curl -s http://127.0.0.1:8000/docs >nul 2>&1
    if !errorlevel! equ 0 (
        echo   Backend ready at http://127.0.0.1:8000/docs
        goto backend_ready
    )
)
echo   Backend not yet ready --- check logs.
:backend_ready

echo.
echo [4/5] Starting Doctor Dashboard (port 5173)...
start "DoctorDashboard" cmd /c "cd /d "%PROJECT%\doctor-dashboard" && npm run dev"
echo   Doctor Dashboard: http://localhost:5173

echo.
echo [5/5] Starting Patient App (port 8081)...
start "PatientApp" cmd /c "cd /d "%PROJECT%\patient-app" && npx expo start --web"
echo   Patient App: http://localhost:8081

echo.
echo ========================================
echo   ALL SERVICES STARTED
echo ========================================
echo   Backend API:    http://127.0.0.1:8000/docs
echo   Doctor Dash:    http://localhost:5173
echo   Patient App:    http://localhost:8081
echo.
echo   To stop: Close each terminal window
echo   Or run: taskkill /F /IM uvicorn.exe /IM node.exe