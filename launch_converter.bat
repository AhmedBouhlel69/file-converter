@echo off
setlocal
title Universal File Converter
cd /d "%~dp0"

:: Check if user requested shortcut creation
if /i "%~1"=="--create-shortcut" goto make_shortcut
if /i "%~1"=="create-shortcut" goto make_shortcut
if /i "%~1"=="shortcut" goto make_shortcut

:: Determine Python executable
if exist "%~dp0venv\Scripts\python.exe" (
    set "PY_CONSOLE=%~dp0venv\Scripts\python.exe"
    set "PY_WINDOWED=%~dp0venv\Scripts\pythonw.exe"
) else (
    set "PY_CONSOLE=python.exe"
    set "PY_WINDOWED=pythonw.exe"
)

:: If CLI arguments were provided, run in console mode synchronously
if not "%~1"=="" (
    "%PY_CONSOLE%" "%~dp0launch_converter.py" %*
    exit /b %ERRORLEVEL%
)

:: Otherwise, launch Desktop GUI seamlessly with pythonw
echo Starting Universal File Converter GUI...
if exist "%PY_WINDOWED%" (
    start "" "%PY_WINDOWED%" "%~dp0launch_converter.py"
) else (
    start "" "%PY_CONSOLE%" "%~dp0launch_converter.py"
)
exit /b 0

:make_shortcut
echo Creating Desktop Shortcut with application icon...
if exist "%~dp0venv\Scripts\python.exe" (
    "%~dp0venv\Scripts\python.exe" "%~dp0create_shortcut.py"
) else (
    python "%~dp0create_shortcut.py"
)
pause
exit /b %ERRORLEVEL%
