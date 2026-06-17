@echo off
echo Starting ONE - Platform...
cd /d "%~dp0"

IF EXIST venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
) ELSE (
    echo Virtual environment not found. Please create it and install requirements.
    pause
    exit /b
)

:: Start Flask server in a minimized window
start "ONE Server" /min python app.py

:: Wait 2 seconds for server to start
timeout /t 2 /nobreak >nul

:: Open browser automatically
start http://localhost:5000
