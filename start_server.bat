@echo off
cd /d "%~dp0"
title BorrowHub - Full-Stack Campus Resource Sharing Platform
echo ================================================================================
echo BORROWHUB — SVNIT SURAT CAMPUS RESOURCE SHARING PLATFORM
echo Share - Borrow - Grow
echo ================================================================================
echo.
echo Starting FastAPI + MySQL Backend & Serving Frontend on http://localhost:8000 ...
echo.

REM Open browser after 2 seconds in background once server is initialized
start "" powershell -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://localhost:8000'"

REM Run Uvicorn server
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
pause
