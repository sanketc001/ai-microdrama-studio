@echo off
REM ============================================================
REM  AI Microdrama Studio - one-click launcher (Windows)
REM  Starts ComfyUI (if down), the FastAPI backend, and the
REM  Vite frontend, each in its own console window.
REM ============================================================
setlocal
cd /d "%~dp0"
title AI Microdrama Studio

REM Prefer the dedicated conda env's Python; fall back to PATH.
set "ENVPY=%USERPROFILE%\anaconda3\envs\microdrama\python.exe"
call conda activate microdrama >nul 2>&1

if exist "%ENVPY%" (
    "%ENVPY%" "scripts\start_all.py"
) else (
    python "scripts\start_all.py"
)

echo.
echo If the windows didn't open, ensure the 'microdrama' conda env exists
echo (see README.md - Setup).
pause
