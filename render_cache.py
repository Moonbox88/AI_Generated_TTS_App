"""Remembers the last finished render so Save after Speak is a file copy.

Speak streams its audio to a temp WAV while it plays (disk, not RAM). If the
user then saves with the same inputs, that file is copied to the target
instead of translating and synthesising everything again.

Volume is not part of the key: it is applied at playback only, so saved
audio is identical at any volume.
"""

import pathlib
import shutil
import tempfile
import threading
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class RenderKey:
    """Everything that changes the synthesised audio."""
    text: str          # the loaded source text (a changed file gives a new key)
    lang: str
    voice: str
    speed: float
    translate: bool    # whether translation actually applies to this job
    source: str = "a"  # translate-from language (or "auto")


class RenderCache:
    def __init__(self, directory: Optional[pathlib.Path] = None):
        self._dir = directory or pathlib.Path(tempfile.mkdtemp(prefix="tts-render-"))
        self._lock = threading.Lock()
        self._counter = 0
        self._key: Optional[RenderKey] = None
        self._path: Optional[pathlib.Path] = None
        self._translated: Optional[str] = None

    def new_path(self) -> pathlib.Path:
        """A fresh file for the next job, so a running job can never
        overwrite the render that is currently cached."""
        with self._lock:
            self._counter += 1
            return self._dir / f"render-{self._counter}.wav"

    def store(self, key: RenderKey, path: pathlib.Path,
              translated: Optional[str]) -> None:
        """Record a completed render, deleting the one it replaces."""
        with self._lock:
            old = self._path
            self._key, self._path, self._translated = key, path, translated
        if old is not None and old != path:
            old.unlink(missing_ok=True)

    def export(self, key: RenderKey, output: str) -> bool:
        """Write the cached render to `output` if it matches `key`.

        Also writes the translated text next to it as .txt, as a fresh Save
        would. Returns False on a miss; the caller must then synthesise.
        """
        with self._lock:  # held so store() can't delete the file mid-copy
            if key != self._key or self._path is None or not self._path.is_file():
                return False
            write_audio(self._path, output)
            if self._translated is not None:
                pathlib.Path(output).with_suffix(".txt").write_text(
                    self._translated, encoding="utf-8")
            return True

    def close(self) -> None:
        with self._lock:
            self._key = self._path = None
        shutil.rmtree(self._dir, ignore_errors=True)


def write_audio(source_wav: pathlib.Path, output: str) -> None:
    """Copy a WAV to `output`, converting if the extension asks for another
    format soundfile supports (e.g. .flac)."""
    target = pathlib.Path(output)
    fmt = target.suffix.lstrip(".").upper()
    if fmt in ("", "WAV"):
        shutil.copyfile(source_wav, target)
        return
    import soundfile as sf
    if fmt not in sf.available_formats():
        shutil.copyfile(source_wav, target)
        return
    data, rate = sf.read(str(source_wav), dtype="float32")
    sf.write(str(target), data, rate, format=fmt)
