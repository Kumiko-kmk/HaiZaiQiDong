@echo off
setlocal

cd /d "%~dp0"
set "VENV_PYTHON=%~dp0.venv\Scripts\python.exe"

if not exist "%VENV_PYTHON%" (
    echo [ERROR] Virtual environment not found: .venv
    echo Run scripts\setup.ps1 once, then double-click this file again.
    pause
    exit /b 1
)

"%VENV_PYTHON%" "%~dp0main.py"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [ERROR] Application exited with code %EXIT_CODE%.
    pause
)

exit /b %EXIT_CODE%
