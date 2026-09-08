@echo off
title Universal File Converter
echo Starting Universal File Converter...
cd /d "%~dp0"
if exist "venv\Scripts\python.exe" (
    start "" "venv\Scripts\pythonw.exe" launch_converter.py
) else (
    python launch_converter.py
)
exit
