"""Translation wrapper over deep-translator.

Google is tried first for quality, but it rate-limits scraped requests
hard (and blocks some networks outright), so MyMemory is used as a
fallback. Long input is chunked to each backend's own character limit.
"""

import re
import time
from dataclasses import dataclass
from typing import Callable, Iterator, Optional

from voices import ENGLISH_CODES, get_language, needs_translation  # noqa: F401

CHUNK_DELAY_SECONDS = 0.25
MAX_RETRIES = 3

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


class TranslationError(RuntimeError):
    """Raised when every backend fails."""


@dataclass(frozen=True)
class Backend:
    name: str
    # Stay under each service's hard cap (Google 5000, MyMemory 500).
    max_chars: int
    build: Callable[[str], object]
    target_attr: str  # which Language field holds this backend's code


def _google(target: str):
    from deep_translator import GoogleTranslator
    return GoogleTranslator(source="en", target=target)


def _mymemory(target: str):
    from deep_translator import MyMemoryTranslator
    return MyMemoryTranslator(source="en-GB", target=target)


BACKENDS = [
    Backend("google", 4000, _google, "google_code"),
    Backend("mymemory", 450, _mymemory, "mymemory_code"),
]

# Once a backend works, stick with it rather than re-probing a blocked one.
_preferred: Optional[str] = None

# Speak then Save (or a re-run) sends identical text; translations are slow
# and rate-limited, so remember the last few results.
_RESULT_LIMIT = 4
_results: dict[tuple[str, str], str] = {}


# ----------------------------------------------------------------------
# Chunking
# ----------------------------------------------------------------------

def _split_oversized(text: str, limit: int) -> Iterator[str]:
    """Break a single over-long run on sentence, then word, then character."""
    for sentence in _SENTENCE_END.split(text):
        if len(sentence) <= limit:
            if sentence:
                yield sentence
            continue
        current = ""
        for word in sentence.split(" "):
            candidate = f"{current} {word}".strip()
            if len(candidate) > limit:
                if current:
                    yield current
                while len(word) > limit:
                    yield word[:limit]
                    word = word[limit:]
                current = word
            else:
                current = candidate
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


def _translate_chunk(client, chunk: str) -> str:
    """Translate one chunk, backing off when the service rate-limits us."""
    delay = 1.0
    for attempt in range(MAX_RETRIES):
        try:
            return client.translate(chunk) or ""
        except _transient_errors():
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(delay)
            delay *= 2
    return ""


def _run_backend(backend: Backend, text: str, lang_code: str,
                 on_progress: Optional[Callable[[int, int], None]]) -> str:
    target = getattr(get_language(lang_code), backend.target_attr)
    client = backend.build(target)
    chunks = chunk_text(text, backend.max_chars)
    out = []
    for index, chunk in enumerate(chunks, start=1):
        if on_progress:
            on_progress(index, len(chunks))
        if index > 1:
            time.sleep(CHUNK_DELAY_SECONDS)
        out.append(_translate_chunk(client, chunk))
    return "\n\n".join(out)


def translate(
    text: str,
    lang_code: str,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> str:
    """Translate text from English to the target language.

    Returns the text unchanged if the target is English. Falls back to the
    next backend if one is unavailable or rate-limited.
    """
    global _preferred

    if not needs_translation(lang_code):
        return text
    if not text.strip():
        return text

    cached = _results.get((lang_code, text))
    if cached is not None:
        return cached

    ordered = sorted(BACKENDS, key=lambda b: b.name != _preferred)
    failures = []
    for backend in ordered:
        try:
            result = _run_backend(backend, text, lang_code, on_progress)
        except Exception as exc:
            failures.append(f"{backend.name}: {type(exc).__name__}")
            continue
        _preferred = backend.name
        if len(_results) >= _RESULT_LIMIT:
            _results.pop(next(iter(_results)))
        _results[(lang_code, text)] = result
        return result

    raise TranslationError(
        "All translation backends failed (" + "; ".join(failures) + ")"
    )
