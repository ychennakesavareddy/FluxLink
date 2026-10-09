@echo off
cd /d "%~dp0"
echo ========================================================
echo Launching Chennalink (Backend + CLI + Web) ...
echo ========================================================

start "Chennalink Backend" cmd /k "run_backend.bat"

echo Waiting for backend to initialize...
timeout /t 3 /nobreak >nul

start "Chennalink CLI" cmd /k "run_cli.bat"

echo Opening Web client in default browser...
start http://127.0.0.1:8000/web/

echo Done! Everything is up and running.
