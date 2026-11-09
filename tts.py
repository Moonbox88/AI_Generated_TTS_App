"""Streaming TTS playback across multiple engines.

Audio is played as it is synthesised rather than after the whole document
is rendered, so a long PDF starts speaking after the first sentence. Each
chunk carries its own sample rate, so Kokoro (24 kHz) and Piper (22.05 kHz)
voices both play back at the correct pitch.

Data flow:  text segments ─▶ engine.stream ─▶ chunks ─┬─▶ _ChunkBuffer ─▶ speaker
                                                      ├─▶ output file (streamed)
                                                      └─▶ _parts (synthesise() only)
Text may arrive as a lazy iterable (e.g. translated a piece at a time), so
synthesis of the first piece overlaps fetching the rest.
"""

import os
import pathlib
import queue
import threading
import time
import weakref
from typing import Callable, Iterable, Optional, Union

import numpy as np

from engines import engine_for_voice
from voices import DEFAULT_LANG, DEFAULT_VOICE, get_voice  # noqa: F401  (re-exported)

DEFAULT_SPEED = 1.0
DEFAULT_VOLUME = 1.0

StatusCallback = Optional[Callable[[str], None]]


# ----------------------------------------------------------------------
# Worker-thread registry and clean shutdown
# ----------------------------------------------------------------------
# Synthesis threads spend most of their time inside torch / onnxruntime.
# If the interpreter exits while one is mid-call, the C++ runtime aborts
# the process ("terminate called without an active exception"). Every
# thread that may enter native code is started through _spawn so that
# shutdown() can stop the jobs and wait for those threads to come out.

_registry_lock = threading.Lock()
_threads: set[threading.Thread] = set()
_jobs: "weakref.WeakSet[Playback]" = weakref.WeakSet()
_shutting_down = threading.Event()


def _spawn(target: Callable, *args) -> threading.Thread:
    def run():
        try:
            target(*args)
        finally:
            with _registry_lock:
                _threads.discard(threading.current_thread())

    thread = threading.Thread(target=run, daemon=True)
    with _registry_lock:
        if _shutting_down.is_set():
            raise RuntimeError("TTS is shutting down")
        _threads.add(thread)
    thread.start()
    return thread


def shutdown(timeout: float = 5.0) -> bool:
    """Stop every job and wait for synthesis threads to finish.

    Call before the program exits. Stop takes effect between sentences, so
    this normally returns within about a second. Returns False if a thread
    is still busy after `timeout` (e.g. a first-run model download); the
    caller should then leave with os._exit(), which skips the interpreter
    teardown that would abort. No new jobs can start afterwards.
    """
    _shutting_down.set()
    with _registry_lock:
        jobs = list(_jobs)
    for job in jobs:
        job.stop()
    deadline = time.monotonic() + timeout
    while True:
        with _registry_lock:
            threads = list(_threads)
        if not threads:
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        threads[0].join(min(remaining, 0.1))


class _ChunkBuffer:
    """Thread-safe queue of audio chunks, drained by the audio callback.

    Kept free of any sounddevice dependency so the drain logic is testable
    without an audio device.
    """

    # Synthesis runs much faster than real time, so an unbounded queue would
    # end up holding a whole document's audio. A few chunks (each a sentence
    # or so) is plenty of headroom; beyond that the producer waits.
    MAX_QUEUED = 8

    def __init__(self, max_queued: int = MAX_QUEUED):
        self._queue: queue.Queue = queue.Queue(maxsize=max_queued)
        self._current: Optional[np.ndarray] = None
        self._pos = 0
        self._closed = threading.Event()

    def put(self, samples: np.ndarray, cancelled: Optional[threading.Event] = None) -> bool:
        """Queue a chunk, waiting while the buffer is full.

        Returns False if `cancelled` was set while waiting (the chunk is
        dropped), so a stopped job never leaves its producer blocked.
        """
        while cancelled is None or not cancelled.is_set():
            try:
                self._queue.put(samples, timeout=0.1)
                return True
            except queue.Full:
                continue
        return False

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
            src = self._current[self._pos:self._pos + take]
            dst = out[written:written + take, 0]
            # Runs on the real-time audio thread: write in place rather than
            # allocating a scaled temporary on every callback.
            if volume == 1.0:
                dst[:] = src
            else:
                np.multiply(src, volume, out=dst)
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
        self._finished = threading.Event()     # everything done, file included
        self._stream_done = threading.Event()  # speaker has played the last sample
        self._stream_lock = threading.Lock()
        self._stream_closing = False
        self._producer: Optional[threading.Thread] = None
        self._parts: list[np.ndarray] = []
        self._keep_audio = True
        self._writer = None  # soundfile.SoundFile, opened on the first chunk
        self._tmp_path: Optional[pathlib.Path] = None
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
        self._close_stream(abort=True)
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
        """True once playback has ended and any output file is complete."""
        return self._finished.is_set()

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

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

    def _close_stream(self, abort: bool = False) -> None:
        """Close the stream exactly once.

        stop() (UI thread) and the producer can both get here; PortAudio
        handles must not be closed twice, so the first caller takes it.
        """
        with self._stream_lock:
            stream = self._stream
            if stream is None or self._stream_closing:
                return
            self._stream_closing = True
        try:
            if abort:
                stream.abort()
            stream.close()
        except Exception:
            pass

    def _ensure_stream(self, sample_rate: int) -> None:
        if self._stream is not None or self._cancelled.is_set():
            return
        import sounddevice as sd
        self._sample_rate = sample_rate
        stream = sd.OutputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            # PortAudio's defaults (~9 ms blocks) crackle and stutter on
            # virtualised or busy sound stacks. Nothing here needs low
            # latency, so trade ~0.25 s of start-up delay for smooth audio.
            blocksize=2048,
            latency=0.25,
            callback=self._callback,
            finished_callback=self._stream_done.set,
        )
        try:
            stream.start()
        except BaseException:
            stream.close()
            raise
        # Only publish a stream that is actually running: _produce waits on
        # _stream_done, which a stream that never started would never set.
        # Under the lock so a stop() racing with start-up can't miss it.
        with self._stream_lock:
            if not self._cancelled.is_set():
                self._stream = stream
                stream = None
        if stream is not None:  # stopped while starting: discard it
            stream.abort()
            stream.close()
            return
        self._status("Playing...")

    def _produce(self, segments: Iterable[str], voice: str, speed: float,
                 output_file: Optional[str], play: bool) -> None:
        try:
            engine = engine_for_voice(voice)
            # Load the model while the first segment is still being fetched
            # (e.g. translated). Failures are ignored here: engine.stream()
            # retries the load and raises properly.
            _spawn(self._prefetch, engine, voice)
            announced = False
            for text in segments:
                if self._cancelled.is_set():
                    break
                if not text.strip():
                    continue
                if not announced:
                    self._status("Synthesising...")
                    announced = True
                for samples, rate in engine.stream(text, voice, speed):
                    if self._cancelled.is_set():
                        break
                    self._consume(samples, rate, output_file, play)
        except BaseException as exc:  # surfaced via wait() / .error
            self.error = exc
        finally:
            self._buffer.close()
            try:
                self._finish_file(output_file,
                                  ok=not self._cancelled.is_set() and self.error is None)
            except BaseException as exc:
                self.error = self.error or exc
            # Signal completion only when the file is in place *and* the
            # speaker is done, so a caller that sees is_finished can use the
            # file immediately. stop() aborts the stream, which sets
            # _stream_done, so this never outlives a cancelled job.
            if self._stream is not None:
                self._stream_done.wait()
                self._close_stream()  # release the audio device
            self._finished.set()

    @staticmethod
    def _prefetch(engine, voice: str) -> None:
        try:
            engine.prepare(voice)
        except Exception:
            pass

    def _consume(self, samples: np.ndarray, rate: int,
                 output_file: Optional[str], play: bool) -> None:
        """Fan one chunk out to every sink that wants it."""
        if self._sample_rate is None:
            self._sample_rate = rate
        if self._keep_audio:
            self._parts.append(samples)
        if output_file:
            self._write_chunk(output_file, samples, rate)
        if play:
            self._ensure_stream(rate)
            self._buffer.put(samples, self._cancelled)

    # Streaming the file means saving never needs the whole document in
    # memory. It is written to a temp name and renamed only on success, so a
    # cancelled or failed job leaves no truncated file behind.

    def _write_chunk(self, output_file: str, samples: np.ndarray, rate: int) -> None:
        if self._writer is None:
            import soundfile as sf
            target = pathlib.Path(output_file)
            fmt = target.suffix.lstrip(".").upper()
            if fmt not in sf.available_formats():
                fmt = "WAV"
            self._tmp_path = target.with_name(target.name + ".part")
            self._writer = sf.SoundFile(str(self._tmp_path), "w", samplerate=rate,
                                        channels=1, format=fmt)
        self._writer.write(samples)

    def _finish_file(self, output_file: Optional[str], ok: bool) -> None:
        if self._writer is None:
            return
        self._writer.close()
        self._writer = None
        if ok:
            os.replace(self._tmp_path, output_file)
        else:
            self._tmp_path.unlink(missing_ok=True)

    def start(self, text: Union[str, Iterable[str]], voice: str, speed: float,
              output_file: Optional[str], play: bool) -> "Playback":
        segments = [text] if isinstance(text, str) else text
        # Saving streams to disk and playing streams to the speaker; only a
        # caller of synthesise() needs the samples kept in memory.
        self._keep_audio = not output_file and not play
        with _registry_lock:
            _jobs.add(self)
        self._producer = _spawn(self._produce, segments, voice, speed,
                                output_file, play)
        return self


# ----------------------------------------------------------------------
# Convenience API
# ----------------------------------------------------------------------

def speak(
    text: Union[str, Iterable[str]],
    voice: str = DEFAULT_VOICE,
    speed: float = DEFAULT_SPEED,
    volume: float = DEFAULT_VOLUME,
    output_file: Optional[str] = None,
    play: bool = True,
    on_status: StatusCallback = None,
) -> Playback:
    """Synthesise text and start streaming playback.

    `text` is a string or an iterable of strings consumed lazily on the
    producer thread; an exception raised by the iterable surfaces through
    .wait() / .error like any synthesis error.

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
