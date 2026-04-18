@echo off
cd /d "%~dp0"
echo ================================================
echo  PaperStandeeMaker - Starting...
echo ================================================
echo.

:: ── Find a working Python ────────────────────────────────────────────────────
set PYTHON_EXE=

python -c "import sys; sys.exit(0)" >nul 2>&1
if not errorlevel 1 set PYTHON_EXE=python

if "%PYTHON_EXE%"=="" (
    py -c "import sys; sys.exit(0)" >nul 2>&1
    if not errorlevel 1 set PYTHON_EXE=py
)

if "%PYTHON_EXE%"=="" (
    echo ERROR: Python not found or Windows Store stub detected.
    echo.
    echo Install Python 3.9+ from https://www.python.org/downloads/
    echo During install tick "Add Python to PATH".
    goto end
)

echo [1/4] Python found:
%PYTHON_EXE% --version
echo.

:: ── Wipe broken venv ─────────────────────────────────────────────────────────
if exist "venv\Scripts\activate.bat" (
    if not exist "venv\Scripts\python.exe" (
        echo [2/4] Broken venv detected, removing it...
        rmdir /s /q venv
    )
)

:: ── Create venv if needed ─────────────────────────────────────────────────────
if not exist "venv\Scripts\python.exe" (
    echo [2/4] Creating virtual environment...
    %PYTHON_EXE% -m venv venv
    if errorlevel 1 (
        echo ERROR: Could not create virtual environment.
        echo Try running as Administrator or check your antivirus.
        goto end
    )
    if not exist "venv\Scripts\python.exe" (
        echo ERROR: venv folder created but python.exe is missing inside it.
        echo Delete the venv folder and try again.
        goto end
    )
    echo [2/4] Virtual environment created OK.
) else (
    echo [2/4] Virtual environment already exists, skipping.
)
echo.

set VENV_PYTHON=venv\Scripts\python.exe

:: ── Install packages if needed ────────────────────────────────────────────────
echo [3/4] Checking dependencies...
%VENV_PYTHON% -c "import gradio" >nul 2>&1
if errorlevel 1 (
    echo Installing packages - this may take a few minutes...
    %VENV_PYTHON% -m pip install --upgrade pip
    %VENV_PYTHON% -m pip install gradio pillow reportlab numpy
    if errorlevel 1 (
        echo ERROR: Package installation failed.
        echo Check your internet connection.
        goto end
    )
    echo Dependencies installed OK.
) else (
    echo Dependencies already installed, skipping.
)
echo.

:: ── Launch app ────────────────────────────────────────────────────────────────
echo [4/4] Starting app - open http://127.0.0.1:7860 in your browser.
echo       Close this window to stop the app.
echo.
%VENV_PYTHON% app.py
if errorlevel 1 (
    echo.
    echo ERROR: app.py exited with an error. See above for details.
)

:end
echo.
echo Press any key to close...
pause >nul
