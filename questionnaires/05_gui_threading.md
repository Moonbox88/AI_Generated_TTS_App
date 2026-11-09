# 05 — GUI threading (`gui.py`)

## Questions
1. Why can't worker threads touch Tk widgets directly? How does `_status_async` get around that?
2. What is `_gather_job` for, and why does it run before the thread starts?
3. Why poll with `after(200, ...)` instead of a callback when playback ends?
4. In `do_speak`, why `lambda err=e:` rather than `lambda: ... e`?
5. Why does `_gather_job` store the file *path* and leave parsing to `_load_text` on the worker?
6. Why does `_set_busy` exist alongside `_set_playback_active`?
7. How does the translate checkbox interact with language selection?
8. What is `selftest` for?
9. `_segments` is a generator consumed on the *synthesis* thread. Why does it use `self.after(0, ...)` for the preview, and why `lambda p=piece:`?

10. The main column uses `grid` but the inside of each card uses `pack`. Why did the main column need `grid`? (What happened to the buttons on a short screen?)
11. Why is the progress bar `grid_remove()`d rather than `grid_forget()`ten when hidden?
12. Shortcuts are bound on the root *and* on the text box. Why both, and why does the handler return `"break"`?
13. Why does `gui_theme.py` use the `clam` theme, and why are plain `tk.Text` widgets styled separately (`style_text`)?
14. Why does the GUI only use symbols like ▶ ⇄ ☾ and never emoji such as 📄 or 💾?
15. How does `_on_swap` turn "Polish → American English" into "English → Polish"? Why can't it just copy the target code into the source box?
16. Where does `settings.py` store the theme on Linux and on Windows, and why does `save()` write a temp file and then `os.replace` it?
17. `settings.load()` returns `{}` for a missing, corrupt or non-object file, and `save()` returns False instead of raising. Why is that the right behaviour for preferences?

## Answers
1. Tk isn't thread-safe. `self.after(0, fn)` queues `fn` to run on the Tk main loop, which is the safe cross-thread hop.
2. It snapshots every widget value on the Tk thread so the worker uses a consistent job dict, and the user changing a slider mid-job can't alter it.
3. `Playback` is Tk-agnostic (also used by the CLI). Polling `is_finished` keeps the engine free of GUI imports.
4. Python closures capture variables, not values; `e` is deleted when the `except` block exits. The default argument binds it at definition time.
5. Parsing a big PDF takes seconds; on the Tk thread the window would freeze. The worker raises on a bad/empty file and `_on_job_failed` shows the error via `after`.
6. `_set_busy` covers the pre-playback window (translating/loading); `_set_playback_active` handles Pause/Stop once audio exists.
7. Non-English languages enable it; English disables, unchecks and hides the preview.
8. Synthesises one phrase per language headlessly, so a frozen PyInstaller build can be checked for missing bundled data.
9. It runs off the Tk thread, so widget updates must be queued with `after`. The default argument binds each piece's value; a bare closure would see only the loop variable's final value by the time Tk runs it.

10. When the window is shorter than everything requested, `pack` clips whichever widgets were packed last, which here were the Save-to card and the action buttons. `grid` shrinks rows by weight, and only the text row has weight, so the text box gives up space and the buttons stay visible.
11. `grid_remove` remembers the row/padding options, so a bare `.grid()` restores it exactly; `grid_forget` discards them.
12. A root binding fires for any focused widget, but Tk's Text class has its own bindings (Ctrl+O inserts a newline, Return inserts a line break) that would run as well. A widget-level binding runs first, and returning "break" stops the class and root bindings from also firing.
13. `clam` ships with Tk and, unlike native themes, lets every colour be set, so light/dark work everywhere with no new dependency (important for the PyInstaller build). ttk styles don't apply to classic Tk widgets such as Text and the combobox drop-down listbox, so those are configured directly.
14. Tk 8.6 can't handle characters above U+FFFF (most emoji) and raises an error; the chosen symbols are in the Basic Multilingual Plane.
15. The old source becomes the new target language (and voice list); the old target becomes the new source. The source list has one entry per language (one English), so the target is matched by translation code rather than copied (British English becomes the single English entry).
16. `~/.config/text-to-speech/settings.json` (or `$XDG_CONFIG_HOME`), and `%APPDATA%\TextToSpeech\settings.json`. Writing then renaming is atomic: a crash mid-write leaves the old file intact rather than a truncated one that would no longer parse.
17. A preference is a convenience. A bad file, a read-only home folder or a full disk should cost the user their theme, not the app; the GUI falls back to light (it also ignores unknown theme names).

## Reusable snippet
`_status_async` + `_gather_job` + worker-thread-then-`after` is the standard recipe for any Tk app doing slow work. Copy those three methods as a template. `gui_theme.py` is a self-contained light/dark ttk theme you can drop into any Tkinter app: call `setup_fonts`, `apply_theme`, then `style_text` on Text widgets. `settings.py` is a drop-in per-user JSON preferences store (platform paths, atomic write, never throws).
