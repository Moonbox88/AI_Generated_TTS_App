"""TTS engine wrapper around Kokoro-82M."""

import threading

import numpy as np
import sounddevice as sd
import soundfile as sf

DEFAULT_VOICE = "af_heart"
DEFAULT_LANG = "a"  # American English
DEFAULT_SPEED = 1.0
DEFAULT_VOLUME = 1.0
SAMPLE_RATE = 24000


_pipeline_cache: dict[str, object] = {}


def _get_pipeline(lang_code: str):
    if lang_code not in _pipeline_cache:
        from kokoro import KPipeline
        _pipeline_cache[lang_code] = KPipeline(lang_code=lang_code)
    return _pipeline_cache[lang_code]


class PlaybackController:
    """Controls playback of a pre-synthesised audio array."""

    def __init__(self, audio: np.ndarray, volume: float = DEFAULT_VOLUME):
        self._audio = (audio * volume).astype(np.float32)
        self._pos = 0
        self._paused = False
        self._stream: sd.OutputStream | None = None
        self._finished = threading.Event()

    # ------------------------------------------------------------------
    # Public controls
    # ------------------------------------------------------------------

    def play(self):
        self._finished.clear()
        self._stream = sd.OutputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            callback=self._callback,
            finished_callback=self._finished.set,
        )
        self._stream.start()

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def stop(self):
        if self._stream and self._stream.active:
            self._stream.stop()
            self._stream.close()
        self._finished.set()

    def wait(self):
        self._finished.wait()

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def is_playing(self) -> bool:
        return self._stream is not None and self._stream.active and not self._paused

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _callback(self, outdata: np.ndarray, frames: int, time, status):
        if self._paused:
            outdata.fill(0)
            return

        remaining = len(self._audio) - self._pos
        if remaining <= 0:
            outdata.fill(0)
            raise sd.CallbackStop()

        chunk = min(frames, remaining)
        outdata[:chunk, 0] = self._audio[self._pos : self._pos + chunk]
        if chunk < frames:
            outdata[chunk:] = 0
            raise sd.CallbackStop()
        self._pos += chunk


def synthesise(
    text: str,
    voice: str = DEFAULT_VOICE,
    lang: str = DEFAULT_LANG,
    speed: float = DEFAULT_SPEED,
) -> np.ndarray:
    """Generate and return audio as a numpy array without playing it."""
    pipeline = _get_pipeline(lang)
    chunks = []
    print(f"Synthesising with voice '{voice}' at speed {speed}x...")
    for _, _, audio in pipeline(text, voice=voice, speed=speed):
        chunks.append(audio)
    if not chunks:
        return np.array([], dtype=np.float32)
    return np.concatenate(chunks)


def speak(
    text: str,
    voice: str = DEFAULT_VOICE,
    lang: str = DEFAULT_LANG,
    speed: float = DEFAULT_SPEED,
    volume: float = DEFAULT_VOLUME,
    output_file: str | None = None,
) -> PlaybackController:
    """Synthesise text and begin playback. Returns a PlaybackController."""
    audio = synthesise(text, voice=voice, lang=lang, speed=speed)

    if audio.size == 0:
        print("No audio generated.")
        ctrl = PlaybackController(audio, volume)
        ctrl._finished.set()
        return ctrl

    if output_file:
        sf.write(output_file, audio, SAMPLE_RATE)
        print(f"Saved to {output_file}")

    print("Playing audio...")
    ctrl = PlaybackController(audio, volume)
    ctrl.play()
    return ctrl
