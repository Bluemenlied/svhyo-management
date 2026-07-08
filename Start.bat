@echo off
title SHYO Management System
color 0A

echo ========================================
echo   Starting SHYO Management System
echo ========================================
echo.

if not exist venv\Scripts\activate (
    color 0C
    echo [ERROR] Virtual environment not found!
    echo Please run INSTALL.bat first.
    echo.
    pause
    exit /b 1
)

echo Activating virtual environment...
call venv\Scripts\activate

echo.
echo Getting local IP address...
set "IP="
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4 Address"') do (
    set "IP=%%a"
    set "IP=!IP: =!"
)

echo.
echo ========================================
echo   SHYO Management System - READY!
echo ========================================
echo.
echo Access from THIS computer:
echo   http://127.0.0.1:5000
echo   http://localhost:5000
echo.
if defined IP (
    echo Access from OTHER computers on the SAME network:
    echo   http://!IP!:5000
    echo.
    echo ========================================
    echo   Share this IP with others: !IP!
    echo ========================================
) else (
    echo To find your IP manually:
    echo 1. Open Command Prompt
    echo 2. Type: ipconfig
    echo 3. Look for "IPv4 Address"
)
echo.
echo Press Ctrl+C to stop the server
echo ========================================
echo.

python app.py

pause