# 06 — Render cache (`render_cache.py`, Save after Speak)

## Questions
1. Speak writes its audio to a temp WAV even when no output path is set. Why disk rather than keeping the samples in memory?
2. Which fields make up `RenderKey`, and why is volume *not* one of them?
3. The key stores the loaded text, not the file path. What case does that handle?
4. Why does `new_path()` hand out a new file name for every job instead of reusing one?
5. `export()` copies while holding the lock. What would go wrong without it?
6. When does Speak *not* store its render? Where is that decided?
7. Why did `Playback.is_finished` need to change for this to work? (Look at `_stream_done`.)
8. `stop()` and the producer thread can both close the audio stream. Why is that dangerous, and how does `_close_stream` prevent it?
9. A Save with a `.flac` name reuses a WAV render. How?

## Answers
1. Audio is about 96 KB per second of speech at 24 kHz float32 (roughly 350 MB per hour). On disk that costs nothing while it plays, and Playback already had a streaming file sink, so Speak only had to pass `output_file`.
2. Text, language, voice, speed and whether translation applies: everything that changes the synthesised samples. Volume is applied only in the playback callback, so saved audio is identical at any volume.
3. If the file is edited between Speak and Save, the reloaded text differs, the key misses, and Save synthesises fresh audio instead of saving a stale render.
4. A job writes its file while the previous render is still cached. With one shared name, a new (or stopped) job would overwrite or delete audio that `export()` might be copying.
5. `store()` from a finishing Speak could delete the old file halfway through the copy, giving a truncated or failed save.
6. When the job was stopped (`is_cancelled`) or failed (`wait()` raised). `do_speak` checks both after `ctrl.wait()`. Playback has already deleted the `.part` file in those cases.
7. Previously "finished" came from the speaker stream ending, which could happen slightly *before* the producer renamed `.part` to the real file. Now `_finished` is set only after the file is in place and `_stream_done` has fired, so whoever sees "finished" can use the file at once.
8. PortAudio frees the native stream on close; closing it twice from two threads is a double free, which can crash the process. `_close_stream` lets only the first caller (under `_stream_lock`) close it, and `_ensure_stream` won't publish a stream if `stop()` already happened.
9. `write_audio` looks at the target extension: WAV is a straight copy; another format soundfile supports is read and re-encoded.

## Reusable snippet
`RenderCache` is a general "remember the last expensive output by input key, and publish by copying" pattern: key = frozen dataclass of every input that changes the result, value = file on disk, with a lock around replace and copy. It fits any slow export: video renders, report generation, image processing.
