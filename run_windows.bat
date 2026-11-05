@echo off
rem Double-click to start Piano Note Labeler.
rem The first time, it sets itself up (needs Python 3.10 or newer from python.org).
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" goto run

echo Setting up Piano Note Labeler for the first time (about a minute)...
py -3 -m venv .venv >nul 2>&1
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo Python 3.10 or newer is needed. Get it from https://www.python.org/downloads/
    echo During install, tick "Add python.exe to PATH". Then run this file again.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo.
    echo Could not install the PDF library. Check your internet connection and try again.
    rmdir /s /q .venv
    pause
    exit /b 1
)

:run
start "" ".venv\Scripts\pythonw.exe" -m note_labeler %*
