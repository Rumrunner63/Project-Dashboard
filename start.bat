@echo off
title PM Command Center - API Server
echo ==========================================
echo   PM Command Center - Starting API Server
echo ==========================================
echo.

:: Check Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python from https://python.org
    pause
    exit /b
)

:: Install each dependency individually so none gets skipped
echo Checking dependencies...
pip show flask >nul 2>&1      || pip install flask
pip show flask-cors >nul 2>&1  || pip install flask-cors
pip show pyodbc >nul 2>&1      || pip install pyodbc
echo.

:: Confirm server.py exists in the same folder
if not exist "%~dp0server.py" (
    echo ERROR: server.py not found. Make sure server.py is in the same folder as start.bat.
    pause
    exit /b
)

:: Confirm the dashboard HTML exists in the same folder
if not exist "%~dp0pm_dashboard*.html" (
    echo WARNING: No pm_dashboard*.html found in this folder.
    echo Make sure the dashboard HTML file is in the same folder as server.py.
    echo.
)

:: Change to the folder where start.bat lives
cd /d "%~dp0"

:: Open browser after 2 second delay (gives server time to start)
echo Opening dashboard in browser...
start "" /b cmd /c "timeout /t 2 >nul && start http://localhost:5000"

:: Start server
echo.
echo ==========================================
echo   Dashboard: http://localhost:5000
echo   API Health: http://localhost:5000/api/health
echo ==========================================
echo   IMPORTANT: Use the URL above, NOT the HTML file directly
echo   Press Ctrl+C to stop the server.
echo ==========================================
echo.
python server.py
pause
