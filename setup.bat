@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 goto :fail
python -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)"
if errorlevel 1 (
    echo Install Python 3.12 for this clone.
    goto :fail
)
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 goto :fail
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :fail
echo Setup complete. Run launch.bat. No live feed or external storage was started.
exit /b 0
:fail
echo Setup failed. Check Python 3.12 and the error above.
exit /b 1
