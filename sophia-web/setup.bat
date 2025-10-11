@echo off
echo 🚀 Setting up SophiaAMS Web Interface...

:: Check if Node.js is installed
where node >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ❌ Node.js is not installed. Please install Node.js 18+ first.
    exit /b 1
)

for /f "tokens=*" %%i in ('node --version') do set NODE_VERSION=%%i
echo ✅ Node.js version: %NODE_VERSION%

:: Install server dependencies
echo.
echo 📦 Installing server dependencies...
cd server
call npm install

if %ERRORLEVEL% NEQ 0 (
    echo ❌ Failed to install server dependencies
    exit /b 1
)

:: Install client dependencies
echo.
echo 📦 Installing client dependencies...
cd ..\client
call npm install

if %ERRORLEVEL% NEQ 0 (
    echo ❌ Failed to install client dependencies
    exit /b 1
)

cd ..

echo.
echo ✅ Setup complete!
echo.
echo 📋 Next steps:
echo   1. Make sure Python API server is running:
echo      python api_server.py
echo.
echo   2. Start Node.js server (in new terminal):
echo      cd server ^&^& npm start
echo.
echo   3. Start React client (in new terminal):
echo      cd client ^&^& npm run dev
echo.
echo   4. Open browser to http://localhost:3000
echo.
pause
