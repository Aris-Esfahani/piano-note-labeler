@echo off
rem Builds dist\PianoNoteLabeler.exe: one file people can download and double-click
rem (no Python needed). Audiveris still has to be installed separately.
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv >nul 2>&1
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if not exist ".venv\Scripts\python.exe" (
    echo Python 3.10 or newer is needed: https://www.python.org/downloads/
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt pyinstaller
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name PianoNoteLabeler launcher.py
if errorlevel 1 exit /b 1
echo.
echo Built: dist\PianoNoteLabeler.exe
