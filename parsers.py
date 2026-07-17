"""Document parsers for txt, pdf, and docx files."""

import pathlib
import re


def clean_text(text: str) -> str:
    """Normalise PDF/plain-text extracted text for TTS.

    Joins mid-sentence line wraps introduced by PDF layout so Kokoro
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
    doc = fitz.open(str(path))
    raw = "\n".join(page.get_text() for page in doc)
    return clean_text(raw)


def parse_docx(path: pathlib.Path) -> str:
    from docx import Document
    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


PARSERS = {
    ".txt": parse_txt,
    ".pdf": parse_pdf,
    ".docx": parse_docx,
}


def extract_text(path: str) -> str:
    p = pathlib.Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")
    suffix = p.suffix.lower()
    if suffix not in PARSERS:
        raise ValueError(f"Unsupported file type '{suffix}'. Supported: {list(PARSERS)}")
    return PARSERS[suffix](p)
