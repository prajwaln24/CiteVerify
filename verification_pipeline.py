"""End-to-end backend pipeline for PDF claim and citation verification."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Callable

from claim_extractor import extract_claims
from citation_extractor import extract_citations, extract_references
from evidence_checker import verify_claim
from evidence_extractor import extract_source_evidence
from pdf_reader import read_pdf
from reference_matcher import match_citations_to_references
from research_retriever import search_papers

_TITLE_MATCH_THRESHOLD = 0.72


def _same_citation(left: str, right: str) -> bool:
    normalize = lambda value: re.sub(r"\s+", "", value).casefold()
    return normalize(left) == normalize(right)


def _combine_verifications(verifications: list[dict]) -> dict:
    if not verifications:
        return {
            "status": "NEEDS HUMAN REVIEW",
            "explanation": "No citation could be reliably matched to a research source.",
            "evidence_excerpt": None,
            "confidence": None,
            "confidence_note": "No confidence score is available without source evidence.",
            "limitations": ["Citation-to-reference matching or research retrieval was unsuccessful."],
            "human_review_recommendation": "Check the citation and locate the original research paper.",
            "comparison_flags": [],
        }
    statuses = [result["verification"]["status"] for result in verifications]
    if "NEEDS HUMAN REVIEW" in statuses:
        status = "NEEDS HUMAN REVIEW"
    elif "CONTRADICTORY" in statuses:
        status = "CONTRADICTORY"
    elif all(value == "SUPPORTED" for value in statuses):
        status = "SUPPORTED"
    elif "POTENTIALLY OUTDATED" in statuses and all(
        value in {"SUPPORTED", "POTENTIALLY OUTDATED"} for value in statuses
    ):
        status = "POTENTIALLY OUTDATED"
    elif all(value == "UNSUPPORTED" for value in statuses):
        status = "UNSUPPORTED"
    else:
        status = "PARTIALLY SUPPORTED"
    parts = [
        f"{item['paper'].get('title') or 'Retrieved source'}: "
        f"{item['verification']['explanation']}"
        for item in verifications
    ]
    confidence_values = [
        item["verification"]["confidence"]
        for item in verifications
        if item["verification"].get("confidence") is not None
    ]
    return {
        "status": status,
        "explanation": " ".join(parts),
        "evidence_excerpt": "\n\n".join(
            f"[{item['paper'].get('title') or 'Source'}; {item['evidence']['evidence_type']}]\n"
            f"{item['verification'].get('evidence_excerpt') or ''}"
            for item in verifications
        ),
        "confidence": round(sum(confidence_values) / len(confidence_values))
        if confidence_values
        else None,
        "confidence_note": "Uncalibrated model confidence indicator; not a probability.",
        "limitations": list(
            dict.fromkeys(
                limitation
                for item in verifications
                for limitation in item["verification"].get("limitations", [])
            )
        ),
        "human_review_recommendation": " ".join(
            dict.fromkeys(
                item["verification"].get("human_review_recommendation", "")
                for item in verifications
            )
        ),
        "comparison_flags": list(
            dict.fromkeys(
                flag
                for item in verifications
                for flag in item["verification"].get("comparison_flags", [])
            )
        ),
    }


def run_verification(
    pdf_source: Any,
    filename: str | None = None,
    generate_json_fn: Callable[[str], dict] | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> dict:
    """Run extraction, source lookup, evidence comparison, and summarization."""

    def report_progress(message: str) -> None:
        if progress_callback:
            progress_callback(message)

    report_progress("Extracting PDF text and document information")
    document = read_pdf(pdf_source)
    if filename:
        document["filename"] = filename
    citations = extract_citations(document["pages"])
    references = extract_references(document["text"])
    matched_citations = match_citations_to_references(citations, references)

    report_progress("Extracting scientific claims with OpenRouter")
    claims = extract_claims(document["pages"], citations, generate_json_fn)
    paper_cache: dict[str, dict] = {}
    results: list[dict] = []
    for claim in claims:
        claim_citations: list[dict] = []
        for requested_text in claim["citation_texts"]:
            for citation in matched_citations:
                if _same_citation(requested_text, citation["text"]):
                    claim_citations.append(citation)
                    break
        source_checks: list[dict] = []
        all_papers: list[dict] = []
        search_errors: list[str] = []
        for citation in claim_citations:
            for reference in citation["matched_references"]:
                reference_key = str(reference.get("doi") or reference.get("text"))
                if reference_key not in paper_cache:
                    report_progress(f"Searching scholarly indexes for: {reference.get('title') or reference_key}")
                    paper_cache[reference_key] = search_papers(reference)
                search = paper_cache[reference_key]
                search_errors.extend(search["errors"])
                paper = next(
                    (
                        candidate
                        for candidate in search["papers"]
                        if candidate["match_score"] >= _TITLE_MATCH_THRESHOLD
                        or (
                            reference.get("doi")
                            and candidate.get("doi")
                            and reference["doi"].casefold() == candidate["doi"].casefold()
                        )
                    ),
                    None,
                )
                if not paper:
                    continue
                paper_identity = (
                    str(paper.get("doi") or paper.get("source_id") or paper.get("title") or "")
                    .casefold()
                )
                if not any(
                    str(existing.get("doi") or existing.get("source_id") or existing.get("title") or "")
                    .casefold() == paper_identity
                    for existing in all_papers
                ):
                    all_papers.append(paper)
                evidence = extract_source_evidence(paper, claim["claim"])
                verification = verify_claim(
                    claim["claim"], paper, evidence, generate_json_fn
                )
                if search["errors"]:
                    verification["limitations"].extend(search["errors"])
                source_checks.append(
                    {"citation": citation, "reference": reference, "paper": paper,
                     "evidence": evidence, "verification": verification}
                )

        summary = _combine_verifications(source_checks)
        if search_errors:
            summary["limitations"] = list(
                dict.fromkeys([*summary["limitations"], *search_errors])
            )
            if not source_checks:
                summary["status"] = "NEEDS HUMAN REVIEW"
                summary["explanation"] += " Research-index lookup did not produce a verified match."
        citations_for_claim = [
            {
                "citation": citation["text"],
                "matched_references": citation["matched_references"],
            }
            for citation in claim_citations
        ]
        results.append(
            {
                **claim,
                "citations": citations_for_claim,
                "matched_reference": (
                    source_checks[0]["reference"]
                    if source_checks
                    else (
                        claim_citations[0]["matched_references"][0]
                        if claim_citations and claim_citations[0]["matched_references"]
                        else None
                    )
                ),
                "matched_paper": source_checks[0]["paper"] if source_checks else None,
                "papers": all_papers,
                "source_checks": source_checks,
                **summary,
            }
        )

    status_counts = Counter(result["status"] for result in results)
    summary = {
        "total_claims": len(results),
        "status_counts": {status: status_counts.get(status, 0) for status in (
            "SUPPORTED", "PARTIALLY SUPPORTED", "UNSUPPORTED", "CONTRADICTORY",
            "POTENTIALLY OUTDATED", "NEEDS HUMAN REVIEW"
        )},
    }
    report_progress("Verification analysis complete")
    return {
        "document": document,
        "citations": citations,
        "references": references,
        "claims": results,
        "summary": summary,
    }
