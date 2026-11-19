"""Citation occurrence and bibliography parsing helpers."""

from __future__ import annotations

import re
from typing import Any


_NUMERIC = re.compile(
    r"\[(?P<body>\s*\d+(?:\s*(?:,|;|[-–])\s*\d+)*\s*)\]"
)
_PARENTHETICAL = re.compile(
    r"\((?P<body>[^()\n]{0,180}\b(?:19|20)\d{2}[a-z]?"
    r"(?:\s*[,;]\s*[^()\n]{0,100}\b(?:19|20)\d{2}[a-z]?)*)\)",
    re.IGNORECASE,
)
_NARRATIVE = re.compile(
    r"\b(?P<author>[A-Z][A-Za-z'’\-]+(?:\s+et\s+al\.?)?)"
    r"\s*\((?P<year>(?:19|20)\d{2}[a-z]?)\)",
    re.IGNORECASE,
)
_REFERENCE_HEADING = re.compile(
    r"(?im)^\s*(?:references|bibliography|works cited|literature cited)\s*:?\s*$"
)
_NUMBERED_REFERENCE = re.compile(r"(?m)^\s*\[(\d+)\]\s*|^\s*(\d+)[.)]\s+")
_DOI = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)


def _citation_keys(body: str) -> list[str]:
    keys: list[str] = []
    for group in re.split(r"\s*;\s*", body):
        if re.fullmatch(r"\s*\d+(?:\s*(?:,|[-–])\s*\d+)*\s*", group):
            for part in re.split(r"\s*,\s*", group.strip()):
                range_match = re.fullmatch(r"(\d+)\s*[-–]\s*(\d+)", part)
                if range_match:
                    first, last = map(int, range_match.groups())
                    if first <= last and last - first <= 100:
                        keys.extend(str(number) for number in range(first, last + 1))
                    else:
                        keys.append(part.strip())
                else:
                    keys.append(part.strip())
            continue

        for author_year in re.split(r"\s*;\s*", group):
            year_match = re.search(r"\b((?:19|20)\d{2}[a-z]?)\b", author_year, re.I)
            if year_match:
                author = author_year[: year_match.start()].strip(" ,")
                if author:
                    surname = re.split(r"\s+(?:and|&)\s+|,\s*", author)[0]
                    surname = re.sub(r"\bet\s+al\.?", "", surname, flags=re.I).strip()
                    if surname:
                        keys.append(f"{surname.casefold()}|{year_match.group(1).casefold()}")
    return list(dict.fromkeys(keys))


def extract_citations(pages_or_text: list[dict[str, Any]] | list[str] | str) -> list[dict]:
    """Return citation occurrences with page numbers and normalized lookup keys."""
    if isinstance(pages_or_text, str):
        pages = [{"page_number": None, "text": pages_or_text}]
    else:
        pages = [
            page if isinstance(page, dict) else {"page_number": None, "text": page}
            for page in pages_or_text
        ]

    citations: list[dict] = []
    reference_page: int | None = None
    for page_index, page in enumerate(pages):
        if reference_page is not None and page_index > reference_page:
            break
        text = str(page.get("text", ""))
        heading = _REFERENCE_HEADING.search(text)
        if heading:
            text = text[: heading.start()]
            reference_page = page_index
        for pattern, style in ((_NUMERIC, "numeric"), (_PARENTHETICAL, "author_year")):
            for match in pattern.finditer(text):
                citations.append(
                    {
                        "text": match.group(0),
                        "style": style,
                        "keys": _citation_keys(match.group("body")),
                        "page_number": page.get("page_number"),
                    }
                )
        for match in _NARRATIVE.finditer(text):
            citations.append(
                {
                    "text": match.group(0),
                    "style": "author_year",
                    "keys": [
                        f"{match.group('author').split()[0].casefold()}|"
                        f"{match.group('year').casefold()}"
                    ],
                    "page_number": page.get("page_number"),
                }
            )
    citations.sort(key=lambda citation: (citation["page_number"] or 0, citation["text"]))
    return citations


def _reference_entry(raw: str, number: str | None = None) -> dict:
    text = re.sub(r"\s+", " ", raw).strip()
    doi_match = _DOI.search(text)
    year_match = re.search(r"\b((?:19|20)\d{2}[a-z]?)\b", text, re.IGNORECASE)
    authors = text[: year_match.start()].strip(" ,.") if year_match else ""
    title = ""
    if year_match:
        remainder = text[year_match.end() :].lstrip(" .,:;")
        title = re.split(r"(?<!\b[A-Z])[.!?]\s", remainder, maxsplit=1)[0].strip(" .")
    return {
        "number": number,
        "text": text,
        "authors": authors,
        "year": year_match.group(1) if year_match else None,
        "title": title or None,
        "doi": doi_match.group(0).rstrip(".,;") if doi_match else None,
    }


def extract_references(document_text: str) -> list[dict]:
    """Parse reference entries after a recognizable bibliography heading."""
    heading = _REFERENCE_HEADING.search(document_text)
    if not heading:
        return []
    bibliography = document_text[heading.end() :]
    markers = list(_NUMBERED_REFERENCE.finditer(bibliography))
    references: list[dict] = []
    if markers:
        for index, marker in enumerate(markers):
            end = markers[index + 1].start() if index + 1 < len(markers) else len(bibliography)
            number = marker.group(1) or marker.group(2)
            entry = bibliography[marker.end() : end].strip()
            if entry:
                references.append(_reference_entry(entry, number))
        return references

    # Unnumbered bibliographies commonly use blank lines between entries.
    blocks = [block.strip() for block in re.split(r"\n\s*\n", bibliography) if block.strip()]
    if len(blocks) <= 1:
        blocks = [
            line.strip()
            for line in bibliography.splitlines()
            if re.search(r"\b(?:19|20)\d{2}[a-z]?\b", line, re.IGNORECASE)
        ]
    return [_reference_entry(block) for block in blocks]