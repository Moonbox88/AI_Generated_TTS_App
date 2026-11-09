"""Persistent user preferences (currently the GUI theme).

Stored as JSON in the platform's per-user config folder:
    Linux    $XDG_CONFIG_HOME/text-to-speech/settings.json (~/.config/...)
    Windows  %APPDATA%\\TextToSpeech\\settings.json
    macOS    ~/Library/Application Support/TextToSpeech/settings.json
Set TTS_CONFIG_DIR to use another folder (tests, portable installs).

Preferences are a convenience: a missing, corrupt or unwritable file
never stops the app, it just falls back to defaults.
"""

import json
import os
import pathlib
import sys
import tempfile
from typing import Any, Optional


def config_dir() -> pathlib.Path:
    override = os.environ.get("TTS_CONFIG_DIR")
    if override:
        return pathlib.Path(override).expanduser()
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or pathlib.Path.home() / "AppData" / "Roaming"
        return pathlib.Path(base) / "TextToSpeech"
    if sys.platform == "darwin":
        return pathlib.Path.home() / "Library" / "Application Support" / "TextToSpeech"
    base = os.environ.get("XDG_CONFIG_HOME") or pathlib.Path.home() / ".config"
    return pathlib.Path(base) / "text-to-speech"


def settings_path() -> pathlib.Path:
    return config_dir() / "settings.json"


def load(path: Optional[pathlib.Path] = None) -> dict[str, Any]:
    """All stored settings, or {} if there are none or they can't be read."""
    path = path or settings_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save(updates: dict[str, Any], path: Optional[pathlib.Path] = None) -> bool:
    """Merge `updates` into the stored settings. Returns False on failure.

    Written to a temp file and renamed into place, so a crash mid-write
    can't leave a half-written (and then unreadable) settings file.
    """
    path = path or settings_path()
    data = load(path)
    data.update(updates)
    tmp = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".settings-", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
        return True
    except OSError:
        if tmp is not None:
            pathlib.Path(tmp).unlink(missing_ok=True)
        return False
