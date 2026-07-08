@echo off
title SHYO Management - Installer
echo ========================================
echo   SHYO Management System Installer
echo ========================================
echo.

echo Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed!
    echo.
    echo Please install Python 3.11 from:
    echo https://www.python.org/downloads/release/python-3119/
    echo.
    echo IMPORTANT: Check "Add Python to PATH" during installation
    echo.
    pause
    exit /b 1
)

python --version
echo.

echo Creating virtual environment...
python -m venv venv

echo.
echo Activating virtual environment...
call venv\Scripts\activate

echo.
echo Upgrading pip...
python -m pip install --upgrade pip

echo.
echo Installing required packages from requirements.txt...
if exist requirements.txt (
    pip install -r requirements.txt
) else (
    echo requirements.txt not found, installing manually...
    pip install Flask==2.3.3 Flask-SQLAlchemy==3.1.1 Flask-Login==0.6.2 pandas==2.0.3 openpyxl==3.1.2 Werkzeug==2.3.7 python-dateutil==2.8.2
)

echo.
echo ========================================
echo   Installation Complete!
echo ========================================
echo.
echo To start the application:
echo 1. Run START.bat
echo 2. Open browser and go to http://127.0.0.1:5000
echo.
pause