# 02 — Engines and voices (`engines/`, `voices.py`)

## Questions
1. What is `Engine` in `engines/base.py` (a base class? something else?), and why does that suit this code?
2. Why are `KokoroEngine` / `PiperEngine` imported inside `get_engine` rather than at the top?
3. Why is `voices.py` the "single source of truth"? What would break if the GUI had its own voice list?
4. Why is Polish `pl` rather than `p`?
5. How does `KokoroEngine` avoid loading the 82M model once per language? (Check `_pipeline`.)
6. What does `PiperEngine._load` use a lock for, and what is the cost?
7. Piper's `length_scale` for 2× speed is 0.5. Why inverse?
8. How do you add a new Piper voice? A new Kokoro language?
9. What does `_to_float32` handle, and why?

## Answers
1. A `typing.Protocol`: structural typing. Any class with `name`, `stream()`, `prepare()` qualifies, with no inheritance or import needed.
2. Importing torch/onnxruntime takes seconds and lots of memory. Lazy import means the app starts fast and only pays for engines actually used.
3. CLI and GUI read the same table, so adding a voice is a one-line edit. Separate lists drift apart and one UI offers voices the other rejects.
4. Kokoro already uses `p` for Brazilian Portuguese; Piper languages use ISO codes to avoid collisions.
5. One `KModel` is created on first use and passed to every `KPipeline(model=...)`. Only the grapheme-to-phoneme front end differs by language.
6. Prevents two threads (e.g. GUI prefetch + speak) from downloading/loading the same voice twice. Cost: other voices wait while one loads.
7. Piper scales phoneme *duration*; longer = slower.
8. Piper: add a tuple to `_PIPER_VOICES` (and a `Language` row if new). Kokoro: add ids to `_KOKORO_VOICES` and a `Language` row.
9. Kokoro yields torch tensors; this detaches, moves to CPU, and converts to a flat float32 numpy array so the rest of the code is torch-free.

## Reusable snippet
`engines/__init__.py` is a ~20-line lazy plugin registry: copy it for any "pick backend by name" design. `voices.py` shows frozen dataclasses + derived registry (`_build_registry`) instead of hand-written tables.
