# 05 — GUI threading (`gui.py`)

## Questions
1. Why can't worker threads touch Tk widgets directly? How does `_status_async` get around that?
2. What is `_gather_job` for, and why does it run before the thread starts?
3. Why poll with `after(200, ...)` instead of a callback when playback ends?
4. In `do_speak`, why `lambda err=e:` rather than `lambda: ... e`?
5. What's wrong with `_get_text()` parsing a big PDF on the Tk thread? (Hint: what freezes?)
6. Why does `_set_busy` exist alongside `_set_playback_active`?
7. How does the translate checkbox interact with language selection?
8. What is `selftest` for?

## Answers
1. Tk isn't thread-safe. `self.after(0, fn)` queues `fn` to run on the Tk main loop, which is the safe cross-thread hop.
2. It snapshots every widget value on the Tk thread so the worker uses a consistent job dict, and the user changing a slider mid-job can't alter it.
3. `Playback` is Tk-agnostic (also used by the CLI). Polling `is_finished` keeps the engine free of GUI imports.
4. Python closures capture variables, not values; `e` is deleted when the `except` block exits. The default argument binds it at definition time.
5. The window stops responding until parsing finishes (seconds for large PDFs). Known limitation; the parser cache only helps the second call. Fix: parse inside the worker and return errors via `after`.
6. `_set_busy` covers the pre-playback window (translating/loading); `_set_playback_active` handles Pause/Stop once audio exists.
7. Non-English languages enable it; English disables, unchecks and hides the preview.
8. Synthesises one phrase per language headlessly, so a frozen PyInstaller build can be checked for missing bundled data.

## Reusable snippet
`_status_async` + `_gather_job` + worker-thread-then-`after` is the standard recipe for any Tk app doing slow work. Copy those three methods as a template.
