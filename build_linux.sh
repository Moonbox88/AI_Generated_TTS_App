#!/usr/bin/env bash
# Build a single-file Linux executable.
# Run from the project root with the venv active.

set -e

echo "Installing Japanese support and PyInstaller..."
pip install -r requirements-ja.txt pyinstaller

echo "Generating icon assets..."
python3 create_icon.py

echo "Building Linux executable..."
python3 -m PyInstaller --noconfirm tts_app.spec

echo ""
echo "Done. Executable is at: dist/TextToSpeech"
