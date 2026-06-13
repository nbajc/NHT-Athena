@echo off
echo ========================================================
echo               NHT ATHENA LAUNCHER v1.2
echo ========================================================
echo.

cd /d "%~dp0"

:: Check for python installation
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python and try again.
    pause
    exit /b 1
)

:: Check if virtual env exists, if not create it
if not exist .venv (
    echo [INFO] Creating Python virtual environment .venv...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

:: Activate virtual environment
echo [INFO] Activating virtual environment...
call .venv\Scripts\activate.bat

:: Install/Upgrade dependencies
echo [INFO] Syncing Python dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

:: Start Flask app
echo.
echo [SUCCESS] Virtual environment ready.
echo [INFO] Starting NHT Athena Core Agent Server...
echo [INFO] Local dashboard will be accessible at: http://localhost:5000
echo.
python app.py

pause
