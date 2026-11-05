@echo off
rem Builds the Windows downloads into the dist folder:
rem   PianoNoteLabeler.exe          the app on its own (Audiveris installed separately)
rem   PianoNoteLabeler-Windows.zip  the app + Audiveris together, nothing to install
rem                                 (made when an "Audiveris" folder is in this project)
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

if exist "Audiveris\Audiveris.exe" (
    ".venv\Scripts\python.exe" make_release_zip.py
    if errorlevel 1 exit /b 1
) else (
    echo No Audiveris folder here, so no all-in-one zip. See README.md.
)
