@echo off
echo Checking for running server...

REM Kill any running uvicorn processes
taskkill /F /IM python.exe /FI "WINDOWTITLE eq AIClinic Server" 2>nul
taskkill /F /IM python.exe /FI "COMMANDLINE eq *uvicorn*" 2>nul

echo Starting server...
echo Server will be available at:
echo - Web Interface: http://localhost:8000
echo - API Documentation: http://localhost:8000/docs
echo.

REM Start the server with a specific window title
start "AIClinic Server" cmd /c "python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000"
