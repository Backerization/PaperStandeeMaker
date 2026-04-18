#!/bin/bash
set -e

# Ensure script is executable
chmod +x "$0"

echo "=== PaperStandeeMaker Setup for macOS ==="

# 1. Check Python Version (Required: 3.9+)
PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
if [[ "$PYTHON_VERSION" != *"3.9"* ]]; then
    echo "Warning: Detected Python version $PYTHON_VERSION. Recommended: 3.9+"
fi

# 2. Create Virtual Environment (Optimized for size)
VENV_DIR=".venv"
python3 -m venv "$VENV_DIR" --no-site-packages || true

# 3. Activate Virtual Environment
source "$VENV_DIR/bin/activate"

echo "=== Installing Dependencies ==="
# Use --no-cache-dir to minimize disk usage during installation
pip install --upgrade pip --no-cache-dir
pip install gradio pillow reportlab numpy --no-cache-dir

# Optional: Install rembg if background removal is required (can be omitted for smaller venv)
# pip install rembg --no-cache-dir || true

echo "=== Starting Application ==="
python -m app.py

if [ $? -eq 0 ]; then
    echo "Application started successfully."
else
    echo "Application failed. Check logs above."
fi

deactivate

