"""PDF text and document metadata extraction using PyMuPDF."""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

import pymupdf as fitz


class PDFProcessingError(ValueError):
    """Raised when a source cannot be read as a text PDF."""


def read_pdf(source: bytes | bytearray | str | Path | BinaryIO) -> dict:
    """Extract page text and metadata from a PDF path, bytes, or binary stream."""
    try:
        if isinstance(source, (bytes, bytearray)):
            document = fitz.open(stream=bytes(source), filetype="pdf")
        elif isinstance(source, (str, Path)):
            document = fitz.open(str(source))
        else:
            data = source.read()
            if not isinstance(data, (bytes, bytearray)):
                raise PDFProcessingError("The PDF input stream must return bytes.")
            document = fitz.open(stream=bytes(data), filetype="pdf")
    except PDFProcessingError:
        raise
    except (fitz.FileDataError, OSError, TypeError, ValueError) as exc:
        raise PDFProcessingError(f"Unable to read the uploaded PDF: {exc}") from exc

    with document:
        pages = [
            {"page_number": page_number, "text": page.get_text("text").strip()}
            for page_number, page in enumerate(document, start=1)
        ]
        metadata = document.metadata or {}
        text = "\n\n".join(
            f"[Page {page['page_number']}]\n{page['text']}" for page in pages
        ).strip()
        return {
            "filename": Path(source).name if isinstance(source, (str, Path)) else None,
            "page_count": len(pages),
            "metadata": {
                key: value
                for key, value in metadata.items()
                if value not in (None, "")
            },
            "pages": pages,
            "text": text,
            "is_scanned": not any(page["text"] for page in pages),
        }