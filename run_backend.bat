@echo off
cd /d "%~dp0"
echo Starting Chennalink Backend on http://127.0.0.1:8000 ...
".venv\Scripts\python.exe" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
pause
