"""Match in-text citation keys to parsed bibliography entries."""

from __future__ import annotations

import re


def match_citations_to_references(
    citations: list[dict], references: list[dict]
) -> list[dict]:
    """Return each citation with a matched reference, or an explicit no-match."""
    numeric = {str(reference["number"]): reference for reference in references if reference.get("number")}
    matches: list[dict] = []
    for citation in citations:
        matched: list[dict] = []
        for key in citation.get("keys", []):
            if "|" not in key:
                reference = numeric.get(str(key))
                if reference and reference not in matched:
                    matched.append(reference)
                continue
            surname, year = key.casefold().split("|", 1)
            for reference in references:
                if str(reference.get("year", "")).casefold() != year:
                    continue
                author_text = str(reference.get("authors", "")).casefold()
                first_author = re.split(r"\s*(?:,|&|\band\b)\s*", author_text)[0]
                if surname in first_author and reference not in matched:
                    matched.append(reference)
        matches.append({**citation, "matched_references": matched})
    return matches
