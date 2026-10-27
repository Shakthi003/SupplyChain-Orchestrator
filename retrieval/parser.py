"""
retrieval/parser.py -- Document Text Extractor

Extracts plain text from uploaded files before embedding.
Supports: PDF (.pdf), Word (.docx), plain text (.txt)

This is Layer 1 of upload validation:
  - Can we extract text at all?
  - Is there enough text to be useful?
"""

import io


# Minimum characters required to consider a document usable
MIN_CONTENT_LENGTH = 100


def extract_text(filename: str, file_bytes: bytes) -> tuple[str, str | None]:
    """
    Extract plain text from an uploaded file.

    Args:
        filename:   Original filename (used to detect type, e.g. "contract.pdf")
        file_bytes: Raw bytes of the uploaded file

    Returns:
        (text, error)
        - text:  Extracted plain text (empty string on failure)
        - error: Human-readable error message, or None on success
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == "pdf":
        return _extract_pdf(file_bytes)
    elif ext == "docx":
        return _extract_docx(file_bytes)
    elif ext in ("txt", "md", "csv"):
        return _extract_text(file_bytes)
    else:
        return "", f"Unsupported file type '.{ext}'. Please upload a PDF, DOCX, or TXT file."


def _extract_pdf(file_bytes: bytes) -> tuple[str, str | None]:
    try:
        import pypdf
    except ImportError:
        return "", "pypdf is not installed. Run: uv add pypdf"

    try:
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(pages).strip()
        if not text:
            return "", (
                "Could not extract text from this PDF. "
                "It may be a scanned image. Please use a text-based PDF or convert to DOCX/TXT."
            )
        return text, None
    except Exception as e:
        return "", f"Failed to read PDF: {e}"


def _extract_docx(file_bytes: bytes) -> tuple[str, str | None]:
    try:
        import docx
    except ImportError:
        return "", "python-docx is not installed. Run: uv add python-docx"

    try:
        doc = docx.Document(io.BytesIO(file_bytes))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        text = "\n".join(paragraphs).strip()
        if not text:
            return "", "The DOCX file appears to be empty or contains only images."
        return text, None
    except Exception as e:
        return "", f"Failed to read DOCX: {e}"


def _extract_text(file_bytes: bytes) -> tuple[str, str | None]:
    for encoding in ("utf-8", "latin-1", "cp1252"):
        try:
            text = file_bytes.decode(encoding).strip()
            if text:
                return text, None
        except UnicodeDecodeError:
            continue
    return "", "Could not decode the text file. Please ensure it is UTF-8 encoded."


def is_long_enough(text: str) -> bool:
    """Layer 1 length check — rejects near-empty extracts."""
    return len(text.strip()) >= MIN_CONTENT_LENGTH
