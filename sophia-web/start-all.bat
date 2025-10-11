@echo off
echo 🚀 Starting SophiaAMS Web Interface...
echo.

:: Start Python API server in background
echo 📡 Starting Python API server...
start "Python API" cmd /k "cd .. && python api_server.py"
timeout /t 3 /nobreak >nul

:: Start Node.js server in background
echo 🔧 Starting Node.js server...
start "Node Server" cmd /k "cd server && npm start"
timeout /t 3 /nobreak >nul

:: Start React client
echo ⚛️ Starting React client...
start "React Client" cmd /k "cd client && npm run dev"

echo.
echo ✅ All services started!
echo.
echo 📋 Services running:
echo   - Python API: http://localhost:8000
echo   - Node Server: http://localhost:3001
echo   - React Client: http://localhost:3000
echo.
echo 🌐 Open your browser to: http://localhost:3000
echo.
echo Press any key to close this window...
pause >nul
