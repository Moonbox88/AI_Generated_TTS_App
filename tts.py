"""Streaming TTS playback across multiple engines.

Audio is played as it is synthesised rather than after the whole document
is rendered, so a long PDF starts speaking after the first sentence. Each
chunk carries its own sample rate, so Kokoro (24 kHz) and Piper (22.05 kHz)
voices both play back at the correct pitch.
"""

import queue
import threading
from typing import Callable, Optional

import numpy as np

from engines import engine_for_voice
from voices import DEFAULT_LANG, DEFAULT_VOICE, get_voice  # noqa: F401  (re-exported)

DEFAULT_SPEED = 1.0
DEFAULT_VOLUME = 1.0

StatusCallback = Optional[Callable[[str], None]]


class _ChunkBuffer:
    """Thread-safe queue of audio chunks, drained by the audio callback.

    Kept free of any sounddevice dependency so the drain logic is testable
    without an audio device.
    """

    def __init__(self):
        self._queue: queue.Queue = queue.Queue()
        self._current: Optional[np.ndarray] = None
        self._pos = 0
        self._closed = threading.Event()

    def put(self, samples: np.ndarray) -> None:
        self._queue.put(samples)

    def close(self) -> None:
        """Signal that no further chunks will arrive."""
        self._closed.set()

    @property
    def is_closed(self) -> bool:
        return self._closed.is_set()

    def read(self, out: np.ndarray, frames: int, volume: float = 1.0) -> bool:
        """Fill out[:frames, 0] with audio. Returns True once exhausted.

        If the producer has not kept up, the remainder is filled with
        silence and False is returned so playback can continue.
        """
        written = 0
        while written < frames:
            if self._current is None or self._pos >= len(self._current):
                try:
                    self._current = self._queue.get_nowait()
                    self._pos = 0
                    continue
                except queue.Empty:
                    out[written:frames, 0] = 0.0
                    return self.is_closed
            take = min(frames - written, len(self._current) - self._pos)
            out[written:written + take, 0] = self._current[self._pos:self._pos + take] * volume
            self._pos += take
            written += take
        return False


class Playback:
    """A single synthesis + playback job.

    Synthesis runs on a producer thread; playback is driven by the
    sounddevice callback. Both can be cancelled mid-flight.
    """

    def __init__(self, volume: float = DEFAULT_VOLUME, on_status: StatusCallback = None):
        self._buffer = _ChunkBuffer()
        self._volume = float(volume)
        self._stream = None
        self._sample_rate: Optional[int] = None
        self._paused = False
        self._cancelled = threading.Event()
        self._finished = threading.Event()
        self._producer: Optional[threading.Thread] = None
        self._parts: list[np.ndarray] = []
        self._keep_audio = True
        self._on_status = on_status
        self.error: Optional[BaseException] = None

    # ------------------------------------------------------------------
    # Public controls
    # ------------------------------------------------------------------

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def stop(self) -> None:
        """Cancel synthesis and stop playback immediately."""
        self._cancelled.set()
        self._buffer.close()
        stream = self._stream
        if stream is not None:
            try:
                stream.abort()
                stream.close()
            except Exception:
                pass
        self._finished.set()

    def wait(self) -> None:
        """Block until playback finishes, re-raising any synthesis error."""
        self._finished.wait()
        if self._producer is not None:
            self._producer.join(timeout=5)
        if self.error is not None:
            raise self.error

    def set_volume(self, volume: float) -> None:
        """Adjust volume live, mid-playback."""
        self._volume = float(volume)

    @property
    def volume(self) -> float:
        return self._volume

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def is_playing(self) -> bool:
        return not self._finished.is_set() and not self._paused

    @property
    def is_finished(self) -> bool:
        return self._finished.is_set()

    @property
    def sample_rate(self) -> Optional[int]:
        return self._sample_rate

    def audio(self) -> np.ndarray:
        """All audio synthesised so far, concatenated."""
        if not self._parts:
            return np.array([], dtype=np.float32)
        return np.concatenate(self._parts)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _status(self, message: str) -> None:
        if self._on_status:
            self._on_status(message)

    def _callback(self, outdata, frames, time_info, status):
        import sounddevice as sd
        if self._cancelled.is_set():
            outdata.fill(0)
            raise sd.CallbackStop
        if self._paused:
            outdata.fill(0)
            return
        if self._buffer.read(outdata, frames, self._volume):
            raise sd.CallbackStop

    def _ensure_stream(self, sample_rate: int) -> None:
        if self._stream is not None:
            return
        import sounddevice as sd
        self._sample_rate = sample_rate
        self._stream = sd.OutputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            # PortAudio's defaults (~9 ms blocks) crackle and stutter on
            # virtualised or busy sound stacks. Nothing here needs low
            # latency, so trade ~0.25 s of start-up delay for smooth audio.
            blocksize=2048,
            latency=0.25,
            callback=self._callback,
            finished_callback=self._finished.set,
        )
        self._stream.start()
        self._status("Playing...")

    def _produce(self, text: str, voice: str, speed: float,
                 output_file: Optional[str], play: bool) -> None:
        try:
            engine = engine_for_voice(voice)
            self._status("Synthesising...")
            for samples, rate in engine.stream(text, voice, speed):
                if self._cancelled.is_set():
                    break
                if self._sample_rate is None:
                    self._sample_rate = rate
                if self._keep_audio:
                    self._parts.append(samples)
                if play:
                    self._ensure_stream(rate)
                    self._buffer.put(samples)
        except BaseException as exc:  # surfaced via wait() / .error
            self.error = exc
        finally:
            self._buffer.close()
            if output_file and not self._cancelled.is_set() and self.error is None:
                self._write(output_file)
            # Nothing was ever queued, so no stream exists to signal completion.
            if self._stream is None:
                self._finished.set()

    def _write(self, output_file: str) -> None:
        audio = self.audio()
        if audio.size == 0:
            return
        import soundfile as sf
        sf.write(output_file, audio, self._sample_rate)
        self._status(f"Saved to {output_file}")

    def start(self, text: str, voice: str, speed: float,
              output_file: Optional[str], play: bool) -> "Playback":
        # Playing without saving never reads the audio back, so don't hold
        # a whole document's samples in memory for nothing.
        self._keep_audio = bool(output_file) or not play
        self._producer = threading.Thread(
            target=self._produce,
            args=(text, voice, speed, output_file, play),
            daemon=True,
        )
        self._producer.start()
        return self


# ----------------------------------------------------------------------
# Convenience API
# ----------------------------------------------------------------------

def speak(
    text: str,
    voice: str = DEFAULT_VOICE,
    speed: float = DEFAULT_SPEED,
    volume: float = DEFAULT_VOLUME,
    output_file: Optional[str] = None,
    play: bool = True,
    on_status: StatusCallback = None,
) -> Playback:
    """Synthesise text and start streaming playback.

    Returns immediately with a Playback handle; call .wait() to block.
    """
    get_voice(voice)  # fail fast on an unknown voice
    playback = Playback(volume=volume, on_status=on_status)
    return playback.start(text, voice, speed, output_file, play)


def synthesise(
    text: str,
    voice: str = DEFAULT_VOICE,
    speed: float = DEFAULT_SPEED,
) -> tuple[np.ndarray, Optional[int]]:
    """Render text to a single array without playing it. Blocks."""
    playback = speak(text, voice=voice, speed=speed, play=False)
    playback.wait()
    return playback.audio(), playback.sample_rate


def prepare(voice: str, on_status: StatusCallback = None) -> None:
    """Load (and download if needed) a voice ahead of time."""
    engine = engine_for_voice(voice)
    if on_status:
        on_status(f"Loading voice {voice}...")
    engine.prepare(voice)
