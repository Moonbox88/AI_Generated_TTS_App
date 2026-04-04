# PyInstaller spec file — works on Linux and Windows.
# Build on each platform separately:
#   Linux:   pyinstaller tts_app.spec
#   Windows: pyinstaller tts_app.spec

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ["gui.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("assets/icon.png", "assets"),
        ("assets/icon.ico", "assets"),
    ],
    hiddenimports=[
        # Kokoro / misaki language modules
        "misaki.en",
        "misaki.ja",
        "misaki.zh",
        "misaki.es",
        "misaki.fr",
        "misaki.hi",
        "misaki.it",
        "misaki.pt",
        "misaki.ko",
        # Deep-translator
        "deep_translator",
        "deep_translator.google",
        # Document parsers
        "fitz",
        "docx",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Collect all files from kokoro and misaki packages
from PyInstaller.utils.hooks import collect_all

for pkg in ("kokoro", "misaki"):
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(pkg)
    a.datas += pkg_datas
    a.binaries += pkg_binaries
    a.hiddenimports += pkg_hiddenimports

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

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
    console=False,  # No terminal window
    icon="assets/icon.ico",
    onefile=True,
)
