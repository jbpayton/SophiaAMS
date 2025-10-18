@echo off
echo ====================================
echo  SophiaAMS Agent System Launcher
echo ====================================
echo.
echo This script will start all required services:
echo   1. FastAPI Server (Port 5000)
echo   2. Agent Server (Port 5001)
echo   3. Node.js Server (Port 3001)
echo.
echo NOTE: React frontend must be started separately:
echo   cd sophia-web/client
echo   npm start
echo.
echo Press Ctrl+C to stop all services
echo ====================================
echo.

REM Start FastAPI server in background
echo [1/3] Starting FastAPI Server...
start "FastAPI Server" cmd /k "python api_server.py"
timeout /t 3 /nobreak >nul

REM Start Agent server in background
echo [2/3] Starting Agent Server...
start "Agent Server" cmd /k "python agent_server.py"
timeout /t 3 /nobreak >nul

REM Start Node.js server in background
echo [3/3] Starting Node.js Server...
start "Node.js Server" cmd /k "cd sophia-web\server && npm start"
timeout /t 3 /nobreak >nul

echo.
echo ====================================
echo  All services started!
echo ====================================
echo.
echo Services running:
echo   - FastAPI:  http://localhost:5000
echo   - Agent:    http://localhost:5001
echo   - Node.js:  http://localhost:3001
echo.
echo To start the frontend:
echo   cd sophia-web/client
echo   npm start
echo.
echo To stop all services:
echo   Close all command windows
echo ====================================
echo.
pause
