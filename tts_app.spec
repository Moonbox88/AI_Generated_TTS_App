# PyInstaller spec file — works on Linux and Windows.
# Build on each platform separately:
#   Linux:   pyinstaller tts_app.spec
#   Windows: pyinstaller tts_app.spec

import sys
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs

block_cipher = None

# Collect package data before Analysis
kokoro_datas, kokoro_binaries, kokoro_hiddenimports = collect_all("kokoro")
misaki_datas, misaki_binaries, misaki_hiddenimports = collect_all("misaki")
sd_datas, sd_binaries, sd_hiddenimports = collect_all("sounddevice")
sf_datas, sf_binaries, sf_hiddenimports = collect_all("soundfile")
# Piper: bundle espeak-ng-data and the espeakbridge extension, but not the
# training/http-server submodules that collect_all would drag in.
piper_datas = collect_data_files("piper", excludes=["train/**", "templates/**"])
piper_binaries = collect_dynamic_libs("piper") + collect_dynamic_libs("onnxruntime")
# Kokoro's non-English languages phonemise through espeak-ng via
# misaki -> phonemizer -> segments -> csvw -> language_tags, and each of those
# reads data files at import time.
espeak_datas, espeak_binaries, espeak_hiddenimports = collect_all("espeakng_loader")
phonemizer_datas = []
for pkg in ("phonemizer", "language_tags", "csvw", "segments", "jsonschema_specifications"):
    phonemizer_datas += collect_data_files(pkg)

a = Analysis(
    ["gui.py"],
    pathex=[],
    binaries=kokoro_binaries + misaki_binaries + sd_binaries + sf_binaries + piper_binaries + espeak_binaries,
    datas=[
        ("assets/icon.png", "assets"),
        ("assets/icon.ico", "assets"),
    ] + kokoro_datas + misaki_datas + sd_datas + sf_datas + piper_datas + espeak_datas + phonemizer_datas,
    hiddenimports=[
        "misaki.en",
        "misaki.ja",
        "misaki.zh",
        "misaki.ko",
        "sounddevice",
        "soundfile",
        "deep_translator",
        "deep_translator.google",
        "fitz",
        "docx",
        "engines.kokoro_engine",
        "engines.piper_engine",
        "piper",
        "piper.voice",
        "piper.config",
        "piper.download_voices",
        "piper.phonemize_espeak",
        "piper.espeakbridge",
        "onnxruntime",
    ] + kokoro_hiddenimports + misaki_hiddenimports + sd_hiddenimports + sf_hiddenimports + espeak_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Icon is only supported on Windows and macOS by PyInstaller
icon = "assets/icon.ico" if sys.platform == "win32" else None

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="TextToSpeech",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    icon=icon,
    onefile=True,
)
