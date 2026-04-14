# PyInstaller spec file — works on Linux and Windows.
# Build on each platform separately:
#   Linux:   pyinstaller tts_app.spec
#   Windows: pyinstaller tts_app.spec

import sys
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# Collect kokoro and misaki package data before Analysis
kokoro_datas, kokoro_binaries, kokoro_hiddenimports = collect_all("kokoro")
misaki_datas, misaki_binaries, misaki_hiddenimports = collect_all("misaki")

a = Analysis(
    ["gui.py"],
    pathex=[],
    binaries=kokoro_binaries + misaki_binaries,
    datas=[
        ("assets/icon.png", "assets"),
        ("assets/icon.ico", "assets"),
    ] + kokoro_datas + misaki_datas,
    hiddenimports=[
        "misaki.en",
        "misaki.ja",
        "misaki.zh",
        "misaki.ko",
        "deep_translator",
        "deep_translator.google",
        "fitz",
        "docx",
    ] + kokoro_hiddenimports + misaki_hiddenimports,
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
