@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" -m sensorlinx_desktop.main %*
    exit /b 0
)

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m sensorlinx_desktop.main %*
    exit /b %ERRORLEVEL%
)

echo Virtual environment (.venv) not found. Please install dependencies first:
echo   uv venv .venv ^&^& uv pip install -e .
pause
exit /b 1
