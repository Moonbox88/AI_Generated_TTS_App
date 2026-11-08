"""Kokoro-82M engine."""

from typing import Iterator

import numpy as np

from voices import get_voice

from .base import Chunk

SAMPLE_RATE = 24000
REPO_ID = "hexgrad/Kokoro-82M"


def _to_float32(audio) -> np.ndarray:
    """Kokoro yields torch tensors; normalise to a float32 numpy array."""
    if hasattr(audio, "detach"):
        audio = audio.detach().cpu().numpy()
    return np.asarray(audio, dtype=np.float32).reshape(-1)


class KokoroEngine:
    name = "kokoro"

    def __init__(self):
        self._pipelines: dict[str, object] = {}
        self._model = None

    def _pipeline(self, lang_code: str):
        if lang_code not in self._pipelines:
            from kokoro import KModel, KPipeline
            # The 82M model is language-agnostic; only the G2P front end
            # differs per language. Load the weights once and share them
            # instead of once per language pipeline.
            if self._model is None:
                self._model = KModel(repo_id=REPO_ID).eval()
            self._pipelines[lang_code] = KPipeline(
                lang_code=lang_code, repo_id=REPO_ID, model=self._model)
        return self._pipelines[lang_code]

    def prepare(self, voice: str) -> None:
        self._pipeline(get_voice(voice).lang)

    def stream(self, text: str, voice: str, speed: float) -> Iterator[Chunk]:
        pipeline = self._pipeline(get_voice(voice).lang)
        for _, _, audio in pipeline(text, voice=voice, speed=speed):
            samples = _to_float32(audio)
            if samples.size:
                yield samples, SAMPLE_RATE
