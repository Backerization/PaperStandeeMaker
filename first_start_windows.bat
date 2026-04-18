@echo off
setlocal enabledelayedexpansion

REM === PaperStandeeMaker Setup for Windows ===

REM Check Python Installation
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo Error: Python not found. Please install Python 3.9+ from python.org.
    pause
) else (
    REM Create Virtual Environment in project root
    py -m venv .venv
    
    REM Activate Virtual Environment
    call .venv\Scripts\activate.bat
    
    echo === Installing Dependencies ===
    pip install --upgrade pip --no-cache-dir
    pip install gradio pillow reportlab numpy --no-cache-dir
    
    REM Optional: Install rembg if background removal is required
    REM pip install rembg --no-cache-dir || true
    
    echo === Starting Application ===
    call .venv\Scripts\python app.py
    
    pause
)

REM Deactivate venv on exit (handled by script end)

