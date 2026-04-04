#!/usr/bin/env bash
# Build a single-file Linux executable.
# Run from the project root with the venv active.

set -e

echo "Generating icon assets..."
python3 create_icon.py

echo "Building Linux executable..."
pyinstaller tts_app.spec

echo ""
echo "Done. Executable is at: dist/TextToSpeech"
