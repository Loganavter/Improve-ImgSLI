@echo off
rem Thin Windows wrapper: locate Python 3 (py launcher, then python) and
rem exec the real launcher (launcher.py).
setlocal
py -3 -c "import sys" >nul 2>&1
if %ERRORLEVEL%==0 (
    py -3 "%~dp0launcher.py" %*
) else (
    python "%~dp0launcher.py" %*
)
exit /b %ERRORLEVEL%
