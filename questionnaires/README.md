# Code questionnaires

Self-test quizzes on the key parts of this project. Goal: understand how it
works and know which pieces can be lifted into other programs.

**How to use:** read the module, answer each question on paper, then compare
with the answers at the bottom of the file. Each file ends with a
"Reusable snippet" section: what to copy, what it depends on.

| File | Module | Core idea |
|---|---|---|
| 01_streaming_playback.md | `tts.py` | producer thread + audio callback |
| 02_engines_and_voices.md | `engines/`, `voices.py` | plugin registry, lazy imports |
| 03_parsers.md | `parsers.py` | text cleanup + mtime cache |
| 04_translator.md | `translator.py` | any-to-any translation, chunking, fallback |
| 05_gui_threading.md | `gui.py`, `gui_theme.py` | keeping Tk responsive, layout, theming |
| 06_render_cache.md | `render_cache.py` | reuse last render on Save |

Add a new file per module as the project grows (Phase 3: FastAPI backend).

The behaviour these quizzes describe is checked by `tests/test_dataflow.py`
(`python -m unittest discover -s tests -v`). Reading a test next to its
question is a good way to confirm an answer.
