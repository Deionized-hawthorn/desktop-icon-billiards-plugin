@echo off
rem Run Desktop Icon Billiards from source using the local virtual environment.
rem Keep this file ASCII-only: cmd.exe decodes batch files with the console code
rem page before any chcp switch takes effect, so UTF-8 Chinese text can corrupt
rem the block syntax on non-UTF-8 consoles.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    echo [error] .venv was not found, cannot run from source.
    echo         Build the environment first: pwsh -File build.ps1
    echo         Or manually: uv venv --managed-python --python 3.12 .venv
    echo         Then: uv pip install --python .venv\Scripts\python.exe -r requirements.txt
    pause
    exit /b 1
)

start "" ".venv\Scripts\pythonw.exe" "app.pyw" %*
