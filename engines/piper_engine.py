"""Piper engine — used for Polish and Romanian.

Voice models (~63 MB each) are not bundled; they are fetched from
rhasspy/piper-voices on first use and cached on disk, mirroring how the
kokoro package pulls its own model down on first run.
"""

import os
import pathlib
import threading
from typing import Callable, Iterator, Optional

import numpy as np

from .base import Chunk


def voice_dir() -> pathlib.Path:
    """Where downloaded .onnx models live. Override with PIPER_VOICE_DIR."""
    env = os.environ.get("PIPER_VOICE_DIR")
    if env:
        return pathlib.Path(env).expanduser()
    cache = os.environ.get("XDG_CACHE_HOME") or (pathlib.Path.home() / ".cache")
    return pathlib.Path(cache) / "piper-voices"


class PiperEngine:
    name = "piper"

    def __init__(self, on_download: Optional[Callable[[str], None]] = None):
        self._voices: dict[str, object] = {}
        self._lock = threading.Lock()
        self.on_download = on_download

    # ------------------------------------------------------------------
    # Model acquisition
    # ------------------------------------------------------------------

    def model_path(self, voice: str) -> pathlib.Path:
        return voice_dir() / f"{voice}.onnx"

    def is_downloaded(self, voice: str) -> bool:
        model = self.model_path(voice)
        return model.is_file() and model.with_suffix(".onnx.json").is_file()

    def download(self, voice: str) -> pathlib.Path:
        """Fetch the model and its config if they are not already cached."""
        model = self.model_path(voice)
        if self.is_downloaded(voice):
            return model

        from piper.download_voices import download_voice

        target = voice_dir()
        target.mkdir(parents=True, exist_ok=True)
        if self.on_download:
            self.on_download(voice)
        download_voice(voice, target)
        return model

    # ------------------------------------------------------------------
    # Synthesis
    # ------------------------------------------------------------------

    def _load(self, voice: str):
        with self._lock:
            if voice not in self._voices:
                from piper import PiperVoice
                self._voices[voice] = PiperVoice.load(str(self.download(voice)))
            return self._voices[voice]

    def prepare(self, voice: str) -> None:
        self._load(voice)

    def stream(self, text: str, voice: str, speed: float) -> Iterator[Chunk]:
        from piper import SynthesisConfig

        loaded = self._load(voice)
        # Piper scales phoneme length, which is the inverse of speed:
        # 2.0x faster == length_scale 0.5.
        config = SynthesisConfig(length_scale=1.0 / speed if speed > 0 else 1.0)
        for chunk in loaded.synthesize(text, config):
            samples = np.asarray(chunk.audio_float_array, dtype=np.float32).reshape(-1)
            if samples.size:
                yield samples, chunk.sample_rate
