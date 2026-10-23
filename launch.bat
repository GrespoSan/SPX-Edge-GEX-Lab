@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup.bat first.
    exit /b 1
)
if "%EDGE_PORT%"=="" set "EDGE_PORT=8501"
".venv\Scripts\python.exe" -m streamlit run edge_streamlit.py --server.address 127.0.0.1 --server.port %EDGE_PORT%
exit /b %errorlevel%
