# 01 — Streaming playback (`tts.py`)

## Questions
1. Why does `Playback` use a producer thread *and* a sounddevice callback? What does each do?
2. `_ChunkBuffer` has no sounddevice import. Why is that deliberate?
3. In `_ChunkBuffer.read`, what happens when the queue is empty but the producer isn't finished? What if it *is* finished?
4. Why does each chunk carry a sample rate instead of one constant for the app?
5. What does `blocksize=2048, latency=0.25` trade away, and why?
6. `stop()` sets `_cancelled`, closes the buffer, aborts the stream, and sets `_finished`. Why all four?
7. In `_produce`, why is the `finally` block where the file gets written and `_finished` set?
8. Why does `wait()` re-raise `self.error` rather than the producer raising directly?
9. Why is `_keep_audio` false for "play only, no file"? When is it true?
10. `pause()` just sets a flag. What does the callback do while paused, and why not close the stream?

## Answers
1. Synthesis is slow and bursty; playback needs steady data on a hard real-time schedule. The producer fills a queue; the callback (called by PortAudio on its own thread) drains it. Decoupling lets a long PDF start speaking after the first sentence.
2. The drain logic can be unit-tested with plain numpy arrays and no audio device (CI, headless machines).
3. Empty + not closed: fills the rest with silence and returns False (playback continues, an underrun rather than a crash). Empty + closed: returns True, which raises `CallbackStop` and ends the stream.
4. Kokoro is 24 kHz, Piper 22.05 kHz. Playing 22.05k audio at 24k raises the pitch. The stream is created from the first chunk's rate.
5. Start-up delay (~0.25 s) for smooth audio; small blocks crackle on busy or virtualised sound stacks.
6. `_cancelled` stops the producer and callback; closing the buffer ends reads; `abort()/close()` stops audio now; `_finished` releases anyone in `wait()` or polling `is_finished`. Any one alone leaves something hanging.
7. `finally` runs on success, error and cancel, so the buffer is always closed and waiters always released. The `if self._stream is None` check covers the no-playback case, where no stream callback exists to set `_finished`.
8. Exceptions on a worker thread are otherwise lost. Storing then re-raising in `wait()` delivers them to the caller's thread (GUI polls `.error`).
9. Collected audio is only read by `audio()` (used for saving and `synthesise`). Playing without saving would otherwise accumulate every sample of a long document in RAM. True when saving or not playing.
10. It writes silence and returns. Closing/reopening a stream would cause a click and lose position; the buffer keeps its place.

## Reusable snippet
Copy `_ChunkBuffer` + `Playback` for any "generate audio incrementally, play it live" job (other TTS, synths, audio from a network stream). Needs `numpy`, `sounddevice` (lazy-imported), optionally `soundfile`. Replace the `engine.stream(...)` call in `_produce` with your own generator of `(samples, rate)`.
