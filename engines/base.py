"""Engine interface shared by Kokoro and Piper."""

from typing import Iterator, Protocol

import numpy as np

# A synthesised chunk: float32 samples in [-1, 1], plus the rate they were
# produced at. The rate travels with the audio so a 22.05 kHz Piper voice and
# a 24 kHz Kokoro voice can never be played back at the wrong pitch.
Chunk = tuple[np.ndarray, int]


class Engine(Protocol):
    name: str

    def stream(self, text: str, voice: str, speed: float) -> Iterator[Chunk]:
        """Yield audio chunks as they are synthesised."""
        ...

    def prepare(self, voice: str) -> None:
        """Load (and if needed download) everything required to synthesise.

        Safe to call from a background thread to avoid a cold-start stall.
        """
        ...
