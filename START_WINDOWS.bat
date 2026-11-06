@echo off
setlocal
cd /d "%~dp0"
echo MERIDIAN ERP - LOCAL DEMO ONLY
if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv
    if errorlevel 1 exit /b 1
)
.venv\Scripts\python.exe -m pip install -e ".[dev]"
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m scripts.seed_demo
if errorlevel 1 exit /b 1
echo Open http://127.0.0.1:8000 in your browser.
echo Close this window or press Ctrl+C to stop the local server.
.venv\Scripts\python.exe -m uvicorn meridian.api:app --host 127.0.0.1 --port 8000
