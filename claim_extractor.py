"""LLM-based extraction of verbatim scientific claims."""

from __future__ import annotations

import json
from typing import Any, Callable

from llm_service import generate_json


class ClaimExtractionError(RuntimeError):
    """Raised when claim extraction fails or returns invalid data."""


def _chunks(pages: list[dict[str, Any]], max_chars: int = 18000) -> list[list[dict[str, Any]]]:
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_size = 0
    for page in pages:
        page_text = str(page.get("text", ""))
        if current and current_size + len(page_text) > max_chars:
            chunks.append(current)
            current, current_size = [], 0
        if len(page_text) > max_chars:
            for start in range(0, len(page_text), max_chars):
                if current:
                    chunks.append(current)
                    current, current_size = [], 0
                chunks.append(
                    [
                        {
                            "page_number": page.get("page_number"),
                            "text": page_text[start : start + max_chars],
                        }
                    ]
                )
        else:
            current.append(page)
            current_size += len(page_text)
    if current:
        chunks.append(current)
    return chunks


def extract_claims(
    pages: list[dict[str, Any]],
    citations: list[dict[str, Any]] | None = None,
    generate_json_fn: Callable[[str], dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Extract document claims in page-sized batches and preserve their wording."""
    if not pages or not any(str(page.get("text", "")).strip() for page in pages):
        raise ClaimExtractionError("The PDF contains no extractable text.")

    generator = generate_json_fn or generate_json
    claims: list[dict[str, Any]] = []
    for chunk in _chunks(pages):
        page_text = "\n\n".join(
            f"[Page {page.get('page_number')}]\n{page.get('text', '')}" for page in chunk
        )
        page_numbers = {page.get("page_number") for page in chunk}
        page_citations = [
            citation
            for citation in citations or []
            if citation.get("page_number") in page_numbers
        ]
        prompt = (
            "Identify explicit, testable scientific or empirical claims stated in this "
            "research document excerpt. Do not invent, paraphrase, or strengthen claims. "
            "Return JSON only as {\"claims\":[{\"claim\":\"exact verbatim sentence or "
            "clause\",\"page_number\":1,\"claim_type\":\"...\",\"citations\":[\"exact "
            "citation text\"]}]}. Include only claims that can be copied verbatim from "
            "the excerpt. Use null if page is unknown. A citation belongs to a claim "
            "only when the document clearly associates it with that claim. If no such "
            "citation is present, return an empty citations list. Claim types should be "
            "short labels such as finding, numerical, causal, population, or conclusion.\n\n"
            f"Document excerpt:\n{page_text}\n\n"
            f"Detected citation occurrences (for exact matching only): "
            f"{json.dumps(page_citations, ensure_ascii=False)}"
        )
        try:
            response = generator(prompt)
        except Exception as exc:
            raise ClaimExtractionError(f"Claim extraction failed: {exc}") from exc
        items = response.get("claims")
        if not isinstance(items, list):
            raise ClaimExtractionError("The AI response did not contain a claims list.")
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("claim"), str):
                continue
            claim_text = item["claim"].strip()
            if not claim_text:
                continue
            raw_page = item.get("page_number")
            page_number = raw_page if isinstance(raw_page, int) else None
            chunk_text = "\n".join(str(page.get("text", "")) for page in chunk)
            normalized_claim = " ".join(claim_text.split())
            normalized_text = " ".join(chunk_text.split())
            if normalized_claim.casefold() not in normalized_text.casefold():
                raise ClaimExtractionError(
                    "The AI returned claim wording that is not present verbatim in the PDF."
                )
            claim_citations = item.get("citations", [])
            if not isinstance(claim_citations, list):
                claim_citations = []
            claims.append(
                {
                    "claim": claim_text,
                    "page_number": page_number,
                    "claim_type": str(item.get("claim_type") or "scientific claim"),
                    "citation_texts": [
                        str(value).strip()
                        for value in claim_citations
                        if isinstance(value, str) and value.strip()
                    ],
                }
            )

    unique_claims: list[dict[str, Any]] = []
    seen: set[tuple[str, int | None]] = set()
    for claim in claims:
        identity = (claim["claim"].casefold(), claim["page_number"])
        if identity not in seen:
            unique_claims.append(claim)
            seen.add(identity)
    for index, claim in enumerate(unique_claims, start=1):
        claim["claim_number"] = index
    return unique_claims