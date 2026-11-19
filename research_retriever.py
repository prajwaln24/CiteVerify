"""Metadata lookup against Crossref and Semantic Scholar."""

from __future__ import annotations

import html
import os
import re
from typing import Any
from urllib.parse import quote

import requests
from dotenv import load_dotenv

load_dotenv()

_TIMEOUT = (5, 20)
_USER_AGENT = "CiteVerify/1.0 (academic citation verification)"


def _year(item: dict[str, Any]) -> int | None:
    for key in ("published-print", "published-online", "published", "issued", "created"):
        parts = item.get(key, {}).get("date-parts", [])
        if parts and parts[0]:
            try:
                return int(parts[0][0])
            except (TypeError, ValueError):
                return None
    return None


def _crossref_paper(item: dict[str, Any]) -> dict[str, Any]:
    doi = item.get("DOI")
    title_list = item.get("title") or []
    authors = [
        " ".join(filter(None, (author.get("given"), author.get("family"))))
        for author in item.get("author", [])
    ]
    abstract = item.get("abstract")
    if abstract:
        abstract = re.sub(r"<[^>]+>", " ", html.unescape(abstract))
        abstract = re.sub(r"\s+", " ", abstract).strip()
    return {
        "title": title_list[0] if title_list else None,
        "authors": authors,
        "year": _year(item),
        "doi": doi,
        "abstract": abstract or None,
        "source_url": item.get("URL") or (f"https://doi.org/{doi}" if doi else None),
        "open_access_pdf": None,
        "metadata_source": "Crossref",
        "source_id": doi,
    }


def _semantic_paper(item: dict[str, Any]) -> dict[str, Any]:
    external_ids = item.get("externalIds") or {}
    doi = external_ids.get("DOI")
    open_access = item.get("openAccessPdf") or {}
    paper_id = item.get("paperId")
    authors = [
        author.get("name")
        for author in item.get("authors", [])
        if author.get("name")
    ]
    return {
        "title": item.get("title"),
        "authors": authors,
        "year": item.get("year"),
        "doi": doi,
        "abstract": item.get("abstract"),
        "source_url": item.get("url")
        or (f"https://www.semanticscholar.org/paper/{paper_id}" if paper_id else None),
        "open_access_pdf": open_access.get("url"),
        "metadata_source": "Semantic Scholar",
        "source_id": paper_id,
    }


def _request_json(url: str, *, params: dict | None = None, headers: dict | None = None) -> dict:
    response = requests.get(
        url,
        params=params,
        headers={"User-Agent": _USER_AGENT, **(headers or {})},
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def _normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    normalized = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi.strip(), flags=re.I)
    normalized = re.sub(r"^doi:\s*", "", normalized, flags=re.I)
    return normalized.rstrip(".,;")


def _title_score(reference_title: str | None, paper_title: str | None) -> float:
    if not reference_title or not paper_title:
        return 0.0
    from difflib import SequenceMatcher

    clean = lambda text: re.sub(r"\W+", " ", text.casefold()).strip()
    return SequenceMatcher(None, clean(reference_title), clean(paper_title)).ratio()


def search_papers(reference: dict, limit: int = 5) -> dict[str, Any]:
    """Search the configured scholarly APIs; candidates remain visibly unverified."""
    errors: list[str] = []
    candidates: list[dict[str, Any]] = []
    doi = _normalize_doi(reference.get("doi"))
    title = str(reference.get("title") or "").strip()
    authors = reference.get("authors") or ""
    author_query = " ".join(authors) if isinstance(authors, list) else str(authors)
    semantic_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip()

    if doi:
        try:
            payload = _request_json(
                f"https://api.crossref.org/works/{quote(doi, safe='')}"
            )
            item = payload.get("message")
            if isinstance(item, dict):
                candidates.append(_crossref_paper(item))
        except (requests.RequestException, ValueError, KeyError) as exc:
            errors.append(f"Crossref DOI lookup failed: {exc}")
        semantic_url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{quote(doi, safe='')}"
        try:
            payload = _request_json(
                semantic_url,
                params={
                    "fields": "title,authors,year,abstract,externalIds,url,openAccessPdf"
                },
                headers={"x-api-key": semantic_key} if semantic_key else None,
            )
            candidates.append(_semantic_paper(payload))
        except (requests.RequestException, ValueError, KeyError) as exc:
            errors.append(f"Semantic Scholar DOI lookup failed: {exc}")
    elif title:
        try:
            payload = _request_json(
                "https://api.crossref.org/works",
                params={
                    "query.bibliographic": " ".join(filter(None, (title, author_query))),
                    "rows": max(1, min(limit, 10)),
                },
            )
            candidates.extend(
                _crossref_paper(item)
                for item in payload.get("message", {}).get("items", [])
                if isinstance(item, dict)
            )
        except (requests.RequestException, ValueError, KeyError) as exc:
            errors.append(f"Crossref title search failed: {exc}")
        try:
            payload = _request_json(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params={
                    "query": " ".join(filter(None, (title, author_query))),
                    "limit": max(1, min(limit, 10)),
                    "fields": "title,authors,year,abstract,externalIds,url,openAccessPdf",
                },
                headers={"x-api-key": semantic_key} if semantic_key else None,
            )
            candidates.extend(
                _semantic_paper(item)
                for item in payload.get("data", [])
                if isinstance(item, dict)
            )
        except (requests.RequestException, ValueError, KeyError) as exc:
            errors.append(f"Semantic Scholar title search failed: {exc}")
    else:
        return {"papers": [], "errors": ["Reference has neither a DOI nor a title."]}

    deduplicated: dict[str, dict[str, Any]] = {}
    for paper in candidates:
        paper_doi = _normalize_doi(paper.get("doi"))
        paper["doi"] = paper_doi
        paper["match_score"] = (
            1.0 if doi and paper_doi and doi.casefold() == paper_doi.casefold()
            else _title_score(title, paper.get("title"))
        )
        identity = paper_doi.casefold() if paper_doi else str(paper.get("source_id") or paper.get("title"))
        existing = deduplicated.get(identity)
        if existing:
            sources = set(existing["metadata_sources"])
            sources.add(paper["metadata_source"])
            existing["metadata_sources"] = sorted(sources)
            for field in ("abstract", "open_access_pdf", "source_url"):
                if not existing.get(field) and paper.get(field):
                    existing[field] = paper[field]
            existing["match_score"] = max(existing["match_score"], paper["match_score"])
        else:
            paper["metadata_sources"] = [paper["metadata_source"]]
            deduplicated[identity] = paper
    papers = sorted(
        deduplicated.values(),
        key=lambda paper: (paper["match_score"], bool(paper.get("abstract"))),
        reverse=True,
    )
    return {"papers": papers[: max(1, limit)], "errors": errors}