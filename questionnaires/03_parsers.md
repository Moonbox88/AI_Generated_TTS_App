# 03 — Parsers (`parsers.py`)

## Questions
1. Why does `clean_text` swap paragraph breaks for `\x00PARA\x00` before other regexes?
2. What does `(?<![.?!])\n` match, and why is it a lookbehind?
3. Why join soft-wrapped lines at all for TTS?
4. How is the cache keyed, and why include mtime and size rather than just the path?
5. How is the cache bounded, and what eviction policy results?
6. Why does `parse_docx` add table cells separately?
7. Why are `fitz` and `docx` imported inside their functions?
8. What would `use_cache=False` be useful for?

## Answers
1. It protects real paragraph breaks from the single-newline rules that follow; restored at the end.
2. A newline not preceded by sentence-ending punctuation: a mid-sentence wrap. Lookbehind asserts context without consuming the punctuation.
3. PDFs break lines visually, not semantically. Engines pause at newlines, so unjoined text sounds choppy.
4. `(resolved path, mtime_ns, size)`. If the file is edited the key changes, so stale text is never served.
5. `_CACHE_LIMIT = 8`; when full, `next(iter(dict))` pops the oldest insertion: FIFO (not LRU, since hits don't reorder).
6. `doc.paragraphs` skips tables, which often hold real content. Cells are joined with ". " so TTS pauses between them.
7. Optional heavy dependencies; a txt-only user never loads them (and a missing package fails only when needed).
8. Tests, or when a file changes within the filesystem's timestamp resolution.

## Reusable snippet
`_cache_key` + `extract_text` is a drop-in "memoise expensive file parse, invalidate on change" pattern. `clean_text` is reusable for any PDF-to-prose pipeline (summarisers, search indexing).
