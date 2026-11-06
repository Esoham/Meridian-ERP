@echo off
setlocal
cd /d "%~dp0"
echo MERIDIAN ERP - LOCAL DEMO ONLY
echo.

REM Prefer standard Python 3.12 to avoid free-threaded 3.13t wheel issues.
set "PY_SELECTOR="
py -3.12 -c "import sysconfig; raise SystemExit(bool(sysconfig.get_config_var('Py_GIL_DISABLED')))" >nul 2>&1
if not errorlevel 1 set "PY_SELECTOR=-3.12"
if not defined PY_SELECTOR (
    py -3.13 -c "import sysconfig; raise SystemExit(bool(sysconfig.get_config_var('Py_GIL_DISABLED')))" >nul 2>&1
    if not errorlevel 1 set "PY_SELECTOR=-3.13"
)
if not defined PY_SELECTOR (
    echo ERROR: Standard Python 3.12 or 3.13 is required.
    echo Run py -0p to list available versions.
    exit /b 1
)
echo Using standard Python %PY_SELECTOR%.

if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe -c "import sysconfig; raise SystemExit(bool(sysconfig.get_config_var('Py_GIL_DISABLED')))" >nul 2>&1
    if errorlevel 1 (
        echo ERROR: Existing .venv uses free-threaded Python or is damaged.
        echo Run: rmdir /s /q .venv
        echo Then rerun START_WINDOWS.bat.
        exit /b 1
    )
) else (
    echo Creating virtual environment...
    py %PY_SELECTOR% -m venv .venv
    if errorlevel 1 exit /b 1
)

echo Installing Python dependencies without persistent pip download cache...
.venv\Scripts\python.exe -m pip install --no-cache-dir -e ".[dev]"
if errorlevel 1 (
    echo ERROR: Installation failed. If Windows says there is no space left,
    echo free space on C: and rerun this script.
    exit /b 1
)
.venv\Scripts\python.exe -m scripts.seed_demo
if errorlevel 1 exit /b 1
echo.
echo Open http://127.0.0.1:8000 in your browser.
echo Leave this window open while using the dashboard.
.venv\Scripts\python.exe -m uvicorn meridian.api:app --host 127.0.0.1 --port 8000
