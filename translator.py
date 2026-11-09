"""Translation wrapper over deep-translator.

Translates between any two app languages (or from auto-detected input).
Google is tried first for quality, but it rate-limits scraped requests
hard (and blocks some networks outright), so MyMemory is used as a
fallback. Long input is chunked to each backend's own character limit.
"""

import re
import time
from dataclasses import dataclass
from typing import Callable, Iterator, Optional

from voices import (AUTO_DETECT, DEFAULT_SOURCE, ENGLISH_CODES,  # noqa: F401
                    get_language, needs_translation)

CHUNK_DELAY_SECONDS = 0.25
MAX_RETRIES = 3

# Sentence ends: Latin punctuation + whitespace, Hindi danda, and CJK full
# stops (which are not followed by spaces). "2.5" is not a sentence end.
_SENTENCE_END = re.compile(r"(?<=[.!?…।])\s+|(?<=[。！？])")

ProgressCallback = Optional[Callable[[int, int], None]]


class TranslationError(RuntimeError):
    """Raised when every backend fails."""


class BackendRefused(RuntimeError):
    """The service answered with an error message instead of a translation."""


def _never(_result: str) -> bool:
    return False


# MyMemory reports some failures (bad language pair, daily quota used up,
# over-long query) as the *translated text* with HTTP 200. Without this
# check the app would read the error message aloud.
_MYMEMORY_ERROR = re.compile(
    r"MYMEMORY WARNING|INVALID SOURCE LANGUAGE|INVALID TARGET LANGUAGE|"
    r"INVALID LANGUAGE PAIR|LANGPAIR=|QUERY LENGTH LIMIT")


def _mymemory_error(result: str) -> bool:
    return bool(_MYMEMORY_ERROR.search(result))


@dataclass(frozen=True)
class Backend:
    name: str
    # Stay under each service's hard cap (Google 5000, MyMemory 500).
    max_chars: int
    build: Callable[[str, str], object]   # (source code, target code) -> client
    code_attr: str                        # which Language field holds this backend's codes
    supports_auto: bool = False           # accepts "auto" as the source
    rejects: Callable[[str], bool] = _never  # result is really an error message


def _google(source: str, target: str):
    from deep_translator import GoogleTranslator
    return GoogleTranslator(source=source, target=target)


def _mymemory(source: str, target: str):
    from deep_translator import MyMemoryTranslator
    return MyMemoryTranslator(source=source, target=target)


BACKENDS = [
    Backend("google", 4000, _google, "google_code", supports_auto=True),
    Backend("mymemory", 450, _mymemory, "mymemory_code", rejects=_mymemory_error),
]

# Once a backend works, stick with it rather than re-probing a blocked one.
_preferred: Optional[str] = None

# Speak then Save (or a re-run) sends identical text; translations are slow
# and rate-limited, so remember the last few results.
_RESULT_LIMIT = 4
_results: dict[tuple[str, str, str], str] = {}


# ----------------------------------------------------------------------
# Chunking
# ----------------------------------------------------------------------

def _units(text: str, limit: int) -> Iterator[str]:
    """Sentences, or for a sentence over `limit`, its words (and for a word
    over `limit`, slices of it)."""
    for sentence in _SENTENCE_END.split(text):
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) <= limit:
            yield sentence
            continue
        for word in sentence.split():
            while len(word) > limit:
                yield word[:limit]
                word = word[limit:]
            if word:
                yield word


def _split_oversized(text: str, limit: int) -> Iterator[str]:
    """Split one over-long paragraph into pieces of at most `limit` chars.

    Whole sentences are packed together up to the limit, so a long
    paragraph costs a few requests rather than one per sentence.
    """
    current = ""
    for unit in _units(text, limit):
        candidate = f"{current} {unit}" if current else unit
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            yield current
        current = unit
    if current:
        yield current


def chunk_text(text: str, limit: int) -> list[str]:
    """Split text into translatable pieces, preferring paragraph breaks."""
    if len(text) <= limit:
        return [text] if text else []

    chunks: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        if len(paragraph) <= limit:
            current = paragraph
        else:
            chunks.extend(_split_oversized(paragraph, limit))
    if current:
        chunks.append(current)
    return chunks


# ----------------------------------------------------------------------
# Translation
# ----------------------------------------------------------------------

def _transient_errors() -> tuple:
    from deep_translator import exceptions
    return (exceptions.TooManyRequests, exceptions.RequestError)


def _translate_chunk(backend: Backend, client, chunk: str) -> str:
    """Translate one chunk, backing off when the service rate-limits us."""
    delay = 1.0
    for attempt in range(MAX_RETRIES):
        try:
            result = client.translate(chunk) or ""
        except _transient_errors():
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(delay)
            delay *= 2
            continue
        if backend.rejects(result):
            raise BackendRefused(result[:120])
        return result
    return ""


def _code(backend: Backend, lang: str) -> str:
    if lang == AUTO_DETECT:
        return "auto"
    return getattr(get_language(lang), backend.code_attr)


def _run_backend(backend: Backend, text: str, target: str, source: str) -> str:
    client = backend.build(_code(backend, source), _code(backend, target))
    out = []
    for index, chunk in enumerate(chunk_text(text, backend.max_chars), start=1):
        if index > 1:
            time.sleep(CHUNK_DELAY_SECONDS)
        out.append(_translate_chunk(backend, client, chunk))
    return "\n\n".join(out)


def _translate_piece(piece: str, target: str, source: str) -> str:
    """Translate one piece, trying the last working backend first."""
    global _preferred
    ordered = sorted(BACKENDS, key=lambda b: b.name != _preferred)
    usable = [b for b in ordered if source != AUTO_DETECT or b.supports_auto]
    failures = []
    for backend in usable:
        try:
            result = _run_backend(backend, piece, target, source)
        except Exception as exc:
            failures.append(f"{backend.name}: {type(exc).__name__}")
            continue
        _preferred = backend.name
        return result

    message = "All translation backends failed (" + "; ".join(failures) + ")"
    if len(usable) < len(BACKENDS):
        message += (". Auto-detect only works with Google Translate; choose the"
                    " source language to allow the fallback service.")
    raise TranslationError(message)


def iter_translate(
    text: str,
    lang_code: str,
    on_progress: ProgressCallback = None,
    source: str = DEFAULT_SOURCE,
) -> Iterator[str]:
    """Translate text from `source` to `lang_code`, yielding each translated
    piece as soon as it is ready.

    Feeding this straight into tts.speak() lets the first paragraph start
    speaking while the rest is still being translated. Pieces are sized to
    the largest backend limit; if a backend fails part-way, only the
    remaining pieces move to the fallback (re-split to its own limit).
    The full result is cached once every piece has been translated.
    """
    if not needs_translation(lang_code, source) or not text.strip():
        yield text
        return

    cache_key = (source, lang_code, text)
    cached = _results.get(cache_key)
    if cached is not None:
        yield cached
        return

    pieces = chunk_text(text, max(b.max_chars for b in BACKENDS))
    out: list[str] = []
    for index, piece in enumerate(pieces, start=1):
        if on_progress:
            on_progress(index, len(pieces))
        if index > 1:
            time.sleep(CHUNK_DELAY_SECONDS)
        result = _translate_piece(piece, lang_code, source)
        out.append(result)
        yield result

    if len(_results) >= _RESULT_LIMIT:
        _results.pop(next(iter(_results)))
    _results[cache_key] = "\n\n".join(out)


def translate(
    text: str,
    lang_code: str,
    on_progress: ProgressCallback = None,
    source: str = DEFAULT_SOURCE,
) -> str:
    """Translate text from `source` (default English) to `lang_code`.

    Returns the text unchanged if no translation is needed. Falls back to
    the next backend if one is unavailable or rate-limited.
    """
    return "\n\n".join(iter_translate(text, lang_code, on_progress, source))
