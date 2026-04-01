@echo off
setlocal

cd /d "%~dp0..\.."
if not exist "src\__main__.py" (
    echo Error: src\__main__.py not found. Run from repo root.
    pause
    exit /b 1
)

set "PY=python"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"

echo Repo root: %CD%
echo Using: %PY%
"%PY%" "build\Windows-template\build_windows.py"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo Windows build failed with exit code %EXIT_CODE%.
    pause
    exit /b %EXIT_CODE%
)

pause
exit /b 0
