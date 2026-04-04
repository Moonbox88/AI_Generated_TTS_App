"""Document parsers for txt, pdf, and docx files."""

import pathlib


def parse_txt(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_pdf(path: pathlib.Path) -> str:
    import fitz  # PyMuPDF
    doc = fitz.open(str(path))
    return "\n".join(page.get_text() for page in doc)


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
