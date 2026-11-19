"""Retrieve openly accessible source text or clearly labeled abstracts."""

from __future__ import annotations

import re

import pymupdf as fitz
import requests

_MAX_PDF_BYTES = 20 * 1024 * 1024
_MAX_PAGES = 80


def select_relevant_evidence(text: str, claim: str, max_sentences: int = 5) -> list[str]:
    """Select exact source sentences with claim-term overlap."""
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", text)
        if sentence.strip()
    ]
    if not sentences:
        return []
    stop_words = {
        "about", "after", "among", "also", "and", "are", "because", "been",
        "before", "being", "between", "from", "have", "into", "more", "most",
        "that", "their", "there", "these", "they", "this", "those", "through",
        "were", "which", "with", "would",
    }
    terms = {
        token.casefold()
        for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9-]{2,}", claim)
        if token.casefold() not in stop_words
    }
    ranked = sorted(
        enumerate(sentences),
        key=lambda pair: (
            len(terms & {word.casefold() for word in re.findall(r"[A-Za-z0-9-]+", pair[1])}),
            -pair[0],
        ),
        reverse=True,
    )
    chosen = sorted(index for index, _ in ranked[:max_sentences])
    return [sentences[index] for index in chosen]


def extract_source_evidence(paper: dict, claim: str) -> dict:
    """Try a paper's public PDF, then fall back to its abstract without overclaiming."""
    limitations: list[str] = []
    pdf_url = paper.get("open_access_pdf")
    if pdf_url:
        try:
            response = requests.get(pdf_url, timeout=(5, 25), stream=True)
            response.raise_for_status()
            chunks: list[bytes] = []
            size = 0
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                size += len(chunk)
                if size > _MAX_PDF_BYTES:
                    raise ValueError("The public PDF exceeds the 20 MB retrieval limit.")
                chunks.append(chunk)
            pdf_bytes = b"".join(chunks)
            if not pdf_bytes.startswith(b"%PDF"):
                raise ValueError("The source URL did not return a PDF.")
            with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
                if document.page_count > _MAX_PAGES:
                    raise ValueError("The public PDF exceeds the 80-page processing limit.")
                full_text = "\n".join(page.get_text("text") for page in document).strip()
            if full_text:
                return {
                    "evidence_text": full_text,
                    "evidence_type": "full_text",
                    "evidence_excerpts": select_relevant_evidence(full_text, claim),
                    "limitations": [],
                }
            limitations.append("The accessible PDF contained no extractable text.")
        except (requests.RequestException, fitz.FileDataError, OSError, ValueError) as exc:
            limitations.append(f"Full-text retrieval failed: {exc}")

    abstract = str(paper.get("abstract") or "").strip()
    if abstract:
        limitations.append(
            "Abstract-only evidence: the full research paper was not available for verification."
        )
        return {
            "evidence_text": abstract,
            "evidence_type": "abstract_only",
            "evidence_excerpts": select_relevant_evidence(abstract, claim),
            "limitations": limitations,
        }

    limitations.append("No full text or abstract was available from the retrieved source.")
    return {
        "evidence_text": "",
        "evidence_type": "metadata_only" if paper else "unavailable",
        "evidence_excerpts": [],
        "limitations": limitations,
    }
