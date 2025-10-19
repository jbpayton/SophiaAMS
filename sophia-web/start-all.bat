@echo off
echo 🚀 Starting SophiaAMS with Episodic Memory...
echo.

:: Start Agent Server (with episodic memory) in background
echo 🤖 Starting Sophia Agent Server (with episodic memory)...
start "Sophia Agent" cmd /k "cd .. && venv\Scripts\python.exe agent_server.py"
timeout /t 5 /nobreak >nul

:: Start Node.js server in background
echo 🔧 Starting Node.js web server...
start "Node Server" cmd /k "cd server && npm start"
timeout /t 3 /nobreak >nul

:: Start React client
echo ⚛️ Starting React client...
start "React Client" cmd /k "cd client && npm run dev"

echo.
echo ✅ All services started!
echo.
echo 📋 Services running:
echo   - Sophia Agent (episodic memory): http://localhost:5001
echo   - Node Server (web proxy): http://localhost:3001
echo   - React Client: http://localhost:3000
echo.
echo 🌐 Open your browser to: http://localhost:3000
echo 💬 Chat with Sophia - she now has episodic memory and temporal awareness!
echo.
echo Press any key to close this window...
pause >nul
