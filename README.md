# AI Generated TTS App

A text-to-speech desktop app powered by [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) — a fast, high-quality, fully local TTS model.

## Features

- 54 voices across 9 languages
- Read text directly, or load `.txt`, `.pdf`, or `.docx` files
- Translate English input to the target language before speaking
- Play, pause, resume, and stop playback
- Adjustable speed (0.5x – 2.0x) and volume
- Save audio as `.wav` (with optional translated `.txt` alongside)
- Command-line interface included

## Requirements

- Python 3.10–3.12
- Linux: `espeak-ng`, `libportaudio2`

```bash
sudo apt install espeak-ng libportaudio2 python3-tk
```

## Installation

```bash
git clone https://github.com/Moonbox88/AI_Generated_TTS_App.git
cd AI_Generated_TTS_App
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

### GUI
```bash
python3 gui.py
```

### CLI
```bash
python3 main.py -t "Hello, world!"
python3 main.py -f document.pdf
python3 main.py -f document.docx -v am_michael -o out.wav
python3 main.py -t "Hello" -l f -v ff_siwis --translate
python3 main.py --stdin
python3 main.py --list-voices
python3 main.py --list-langs
```

## Building an Executable

Generate the icon first, then build:

```bash
pip install pyinstaller
python3 create_icon.py

# Linux
bash build_linux.sh

# Windows
build_windows.bat
```

The executable will be in `dist/`.

> **Note:** The Kokoro model (~300MB) is downloaded from Hugging Face on first run and cached locally.

## Voices

54 voices across American English, British English, Japanese, Mandarin Chinese, Spanish, French, Hindi, Italian, and Brazilian Portuguese.

Run `python3 main.py --list-voices` to see all voice IDs.

## Licence

Kokoro-82M is released under the Apache 2.0 licence.
