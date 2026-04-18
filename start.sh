#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
python3 app.py
echo ""
echo "App stopped. Press Enter to close."
read
