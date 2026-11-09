# 04 — Translator (`translator.py`)

## Questions
1. Why two backends, and why try Google first?
2. What does `chunk_text` prefer to split on, and what is the fallback order?
3. Why do the backends have different `max_chars`?
4. How does `_translate_chunk` back off? What counts as transient?
5. What does the module-level `_preferred` do, and what's the downside of module state?
6. Why `CHUNK_DELAY_SECONDS` between chunks?
7. `translate()` catches broad `Exception` per backend. Is that reasonable here?
8. What does the `_results` memo save in the GUI flow, and why is it small?
9. `iter_translate` is a generator and `translate` just joins it. Why build it that way round?
10. If Google fails on piece 2 of 5, what happens to pieces 1, 3, 4, 5? How did the older whole-document fallback differ?
11. Why is the result cached only after the loop finishes?

12. `Backend.build` takes *two* codes now. Why can't the source code be the same string for every backend? (Compare `google_code` and `mymemory_code` in `voices.py`.)
13. With source `auto`, MyMemory is never tried. Why, and how does the error message help the user?
14. What is `Backend.rejects` for? What would the app do without it when MyMemory's daily quota runs out?
15. `needs_translation("b", "a")` is False. Why is British → American English not a translation?
16. `_split_oversized` packs sentences together. What did the old version cost in requests for a 4,500-character paragraph of short sentences?
## Answers
1. Google has better quality but rate-limits scraping and is blocked on some networks; MyMemory is the fallback.
2. Paragraphs, then sentences, then words, then raw characters, so meaning is kept intact as far as the limit allows.
3. Each service has its own hard cap (Google ~5000, MyMemory 500); limits sit below them.
4. Exponential: 1 s, 2 s, then re-raises on the last attempt. Transient = `TooManyRequests` and `RequestError`.
5. Remembers the last working backend so a blocked one isn't re-probed every call. Downside: hidden global state, shared across threads and tests (reset it in tests).
6. Politeness and avoiding rate-limit triggers.
7. Yes: the goal is "try the next backend on any failure"; failures are collected and reported in `TranslationError`.
8. Speak followed by Save (or repeats) translate identical text; a hit skips the network entirely. Small because texts can be large.
9. Streaming is the general case: a consumer (TTS, preview) can act on piece 1 while piece 2 is in flight. A blocking version is a one-line wrapper; you can't go the other way.
10. Piece 1 keeps Google's result; piece 2 is retried on MyMemory (re-split to 450 chars); `_preferred` becomes MyMemory so 3-5 go straight there. Before, a mid-document failure threw away finished work and re-translated everything.
11. If the consumer stops early (user hits Stop) the generator is closed partway; caching then would store a truncated translation as if complete.

12. Each service names languages differently: Google wants `pl`/`en`, MyMemory wants locales like `pl-PL`/`en-US`. `_code()` reads the right `Language` field per backend (`code_attr`), and returns `auto` for auto-detect.
13. MyMemory rejects `auto` (and returns the complaint as text). `_translate_piece` filters to `supports_auto` backends, and if that leaves only Google and it fails, the message says to pick the source language so the fallback can run.
14. Some MyMemory failures arrive as HTTP 200 with the error as the "translation". `rejects` spots those markers and raises `BackendRefused`, so the fallback chain treats it as a failure. Without it the app would read the quota warning aloud.
15. Both map to Google code `en`; the comparison is on translation codes, not app codes. The source list also collapses them to one "English" entry.
16. One request per sentence (hundreds, each with a 0.25 s delay and rate-limit risk). Packing makes it about two 4,000-char requests.
## Reusable snippet
`chunk_text` / `_split_oversized` are generic "split to a size limit while preserving structure" helpers (LLM context windows, API limits). `translate()` shows a fallback-chain pattern: ordered backends, preferred-first sort, aggregated error.
