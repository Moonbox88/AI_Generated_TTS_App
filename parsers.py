"""Document parsers for txt, pdf, and docx files."""

import pathlib
import re
from typing import Optional

# Extraction is re-run on every Speak and every Save, and a large PDF takes
# seconds to parse, so results are cached against the file's mtime and size.
_CACHE_LIMIT = 8
_cache: dict[tuple, str] = {}


def clean_text(text: str) -> str:
    """Normalise extracted text for TTS.

    Joins mid-sentence line wraps introduced by PDF layout so the engine
    doesn't pause at every visual line break.
    """
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    # Protect real paragraph breaks (2+ consecutive newlines)
    text = re.sub(r'\n{2,}', '\x00PARA\x00', text)

    # Rejoin hyphenated line breaks: "word-\nnext" → "word-next"
    text = re.sub(r'-\n([a-z])', r'-\1', text)

    # Join mid-sentence soft wraps (line doesn't end with terminal punctuation)
    text = re.sub(r'(?<![.?!])\n', ' ', text)

    # Flatten post-sentence newlines — punctuation already signals the pause
    text = re.sub(r'([.?!])\n', r'\1 ', text)

    # Restore paragraph breaks and clean up whitespace
    text = text.replace('\x00PARA\x00', '\n\n')
    text = re.sub(r'  +', ' ', text)

    return text.strip()


def parse_txt(path: pathlib.Path) -> str:
    return clean_text(path.read_text(encoding="utf-8"))


def parse_pdf(path: pathlib.Path) -> str:
    import fitz  # PyMuPDF
    with fitz.open(str(path)) as doc:
        raw = "\n".join(page.get_text() for page in doc)
    return clean_text(raw)


def parse_docx(path: pathlib.Path) -> str:
    from docx import Document
    doc = Document(str(path))

    blocks = [p.text for p in doc.paragraphs if p.text.strip()]
    # Tables hold real prose in many documents and were previously dropped.
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                blocks.append(". ".join(cells))

    return clean_text("\n\n".join(blocks))


PARSERS = {
    ".txt": parse_txt,
    ".pdf": parse_pdf,
    ".docx": parse_docx,
}


def _cache_key(path: pathlib.Path) -> Optional[tuple]:
    try:
        stat = path.stat()
    except OSError:
        return None
    return (str(path.resolve()), stat.st_mtime_ns, stat.st_size)


def clear_cache() -> None:
    _cache.clear()


def extract_text(path: str, use_cache: bool = True) -> str:
    p = pathlib.Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")
    suffix = p.suffix.lower()
    if suffix not in PARSERS:
        raise ValueError(f"Unsupported file type '{suffix}'. Supported: {list(PARSERS)}")

    key = _cache_key(p) if use_cache else None
    if key is not None and key in _cache:
        return _cache[key]

    text = PARSERS[suffix](p)

    if key is not None:
        if len(_cache) >= _CACHE_LIMIT:
            _cache.pop(next(iter(_cache)))
        _cache[key] = text
    return text
