@echo off
cd /d "%~dp0"
if not exist .venv (py -m venv .venv)
call .venv\Scripts\activate.bat
if not exist .venv\.jobpilot-installed (
  python -m pip install -r requirements.txt
  if errorlevel 1 (echo Install failed. & pause & exit /b 1)
  type nul > .venv\.jobpilot-installed
)
start "" /min cmd /c "timeout /t 3 /nobreak >nul && start http://127.0.0.1:8765"
python -m uvicorn app:app --host 127.0.0.1 --port 8765
pause
