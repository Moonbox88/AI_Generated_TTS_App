@echo off
REM Build a single-file Windows executable.
REM Run from the project root with the venv active.

echo Generating icon assets...
python create_icon.py

echo Building Windows executable...
pyinstaller tts_app.spec

echo.
echo Done. Executable is at: dist\TextToSpeech.exe
