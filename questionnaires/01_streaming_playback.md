# 01 — Streaming playback (`tts.py`)

## Questions
1. Why does `Playback` use a producer thread *and* a sounddevice callback? What does each do?
2. `_ChunkBuffer` has no sounddevice import. Why is that deliberate?
3. In `_ChunkBuffer.read`, what happens when the queue is empty but the producer isn't finished? What if it *is* finished?
4. Why does each chunk carry a sample rate instead of one constant for the app?
5. What does `blocksize=2048, latency=0.25` trade away, and why?
6. `stop()` sets `_cancelled`, closes the buffer, aborts the stream, and sets `_finished`. Why all four?
7. The output file is written chunk by chunk to `name.wav.part` and renamed at the end. Why not write straight to `name.wav`, and why is the rename in `finally`?
8. Why does `wait()` re-raise `self.error` rather than the producer raising directly?
9. `_keep_audio` is only true for `synthesise()`. Where does audio go when playing, and when saving, if it isn't kept?
10. `pause()` just sets a flag. What does the callback do while paused, and why not close the stream?
11. `_ChunkBuffer` has `maxsize=8` and `put()` waits with a 0.1 s timeout loop. What problem does the bound solve, and why the loop instead of a plain blocking `put()`?
12. `speak()` accepts an iterable of strings. What does that enable, and why is `engine.prepare()` started on a separate thread in `_produce`?

## Answers
1. Synthesis is slow and bursty; playback needs steady data on a hard real-time schedule. The producer fills a queue; the callback (called by PortAudio on its own thread) drains it. Decoupling lets a long PDF start speaking after the first sentence.
2. The drain logic can be unit-tested with plain numpy arrays and no audio device (CI, headless machines).
3. Empty + not closed: fills the rest with silence and returns False (playback continues, an underrun rather than a crash). Empty + closed: returns True, which raises `CallbackStop` and ends the stream.
4. Kokoro is 24 kHz, Piper 22.05 kHz. Playing 22.05k audio at 24k raises the pitch. The stream is created from the first chunk's rate.
5. Start-up delay (~0.25 s) for smooth audio; small blocks crackle on busy or virtualised sound stacks.
6. `_cancelled` stops the producer and callback; closing the buffer ends reads; `abort()/close()` stops audio now; `_finished` releases anyone in `wait()` or polling `is_finished`. Any one alone leaves something hanging.
7. Streaming to disk means saving never holds the whole document in memory. A temp name plus `os.replace` (atomic) means a cancelled or failed job never leaves a truncated file under the real name: `_finish_file(ok=False)` deletes the `.part`. `finally` runs on success, error and cancel, so the file is always finalised, the buffer closed and waiters released (`_stream is None` covers the no-playback case).
8. Exceptions on a worker thread are otherwise lost. Storing then re-raising in `wait()` delivers them to the caller's thread (GUI polls `.error`).
9. Playing: into the bounded `_ChunkBuffer`, then the speaker. Saving: straight into the `SoundFile` writer. Only `synthesise()` needs one array back, so only it keeps `_parts`. `_consume()` is the fan-out point.
10. It writes silence and returns. Closing/reopening a stream would cause a click and lose position; the buffer keeps its place.
11. Synthesis is faster than real time, so an unbounded queue ends up holding the whole document. The bound gives backpressure: the producer pauses when 8 chunks are waiting. A plain blocking `put()` would hang forever after Stop (nothing drains the queue); the timeout loop re-checks `cancelled`.
12. Translation (or any slow source) can feed text a piece at a time, so speech starts after the first paragraph instead of after the whole document. The prepare thread loads the model *while* that first piece is still being fetched; the engine lock makes the later `stream()` wait for, not duplicate, that load.

## Reusable snippet
Copy `_ChunkBuffer` + `Playback` for any "generate audio incrementally, play it live" job (other TTS, synths, audio from a network stream). Needs `numpy`, `sounddevice` (lazy-imported), optionally `soundfile`. Replace the `engine.stream(...)` call in `_produce` with your own generator of `(samples, rate)`. The `_write_chunk`/`_finish_file` pair is a standalone "stream to temp file, atomically publish on success" pattern.
