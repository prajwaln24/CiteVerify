"""Evidence-constrained claim verification with conservative fallbacks."""

from __future__ import annotations

import json
from typing import Any, Callable

from llm_service import generate_json

STATUSES = {
    "SUPPORTED",
    "PARTIALLY SUPPORTED",
    "UNSUPPORTED",
    "CONTRADICTORY",
    "POTENTIALLY OUTDATED",
    "NEEDS HUMAN REVIEW",
}


def verify_claim(
    claim: str,
    paper: dict,
    evidence: dict,
    generate_json_fn: Callable[[str], dict[str, Any]] | None = None,
) -> dict:
    """Compare a claim with only the supplied source evidence."""
    source_text = str(evidence.get("evidence_text") or "")
    excerpts = evidence.get("evidence_excerpts") or []
    limitations = list(evidence.get("limitations") or [])
    if not source_text.strip() or not excerpts:
        return {
            "status": "NEEDS HUMAN REVIEW",
            "explanation": "No usable source evidence was available to assess this claim.",
            "evidence_excerpt": None,
            "confidence": None,
            "confidence_note": "No confidence score is available without source evidence.",
            "limitations": limitations,
            "human_review_recommendation": "Inspect the original paper or locate accessible full text.",
            "comparison_flags": [],
        }

    prompt = (
        "You are a cautious scientific evidence reviewer, not a final scientific authority. "
        "Assess only whether the exact claim is supported by the supplied source evidence. "
        "Do not use outside knowledge or infer missing results. Consider numerical values, "
        "population, conditions, causation versus correlation, qualifications, and scope. "
        "Use NEEDS HUMAN REVIEW if evidence is inadequate or ambiguous. Return a JSON object "
        "with: status (one of SUPPORTED, PARTIALLY SUPPORTED, UNSUPPORTED, CONTRADICTORY, "
        "POTENTIALLY OUTDATED, NEEDS HUMAN REVIEW), explanation, evidence_excerpt (must be "
        "an exact substring of supplied source evidence, otherwise null), confidence (integer "
        "0-100 as an uncalibrated model indicator, not a probability), limitations (array of "
        "strings), human_review_recommendation, comparison_flags (array; use relevant labels "
        "such as numerical mismatch, missing qualification, population mismatch, causation/"
        "correlation, unsupported generalization, or contradictory evidence). Do not invent "
        "quotes, DOIs, source details, or evidence.\n\n"
        f"Claim:\n{claim}\n\n"
        f"Paper metadata:\n{json.dumps({key: paper.get(key) for key in ('title', 'year', 'doi', 'source_url')}, ensure_ascii=False)}\n\n"
        f"Evidence type: {evidence.get('evidence_type')}\n"
        f"Source evidence (only permissible evidence):\n{source_text[:24000]}\n\n"
        f"Candidate exact excerpts for reference:\n{json.dumps(excerpts, ensure_ascii=False)}"
    )
    response = (generate_json_fn or generate_json)(prompt)
    status = str(response.get("status", "")).upper()
    if status not in STATUSES:
        status = "NEEDS HUMAN REVIEW"
    excerpt = response.get("evidence_excerpt")
    if not isinstance(excerpt, str) or excerpt not in source_text:
        excerpt = excerpts[0] if excerpts else None
        status = "NEEDS HUMAN REVIEW"
        explanation = (
            "The AI did not return a verifiable exact evidence excerpt. "
            "The claim requires human review."
        )
        limitations.append("The model's evidence excerpt could not be verified against source text.")
    else:
        explanation = str(response.get("explanation") or "The evidence comparison was inconclusive.")

    raw_confidence = response.get("confidence")
    confidence = (
        max(0, min(100, int(raw_confidence)))
        if isinstance(raw_confidence, (int, float)) and not isinstance(raw_confidence, bool)
        else None
    )
    model_limitations = response.get("limitations")
    if isinstance(model_limitations, list):
        limitations.extend(str(item) for item in model_limitations if item)
    flags = response.get("comparison_flags")
    if not isinstance(flags, list):
        flags = []
    recommendation = response.get("human_review_recommendation")
    if not isinstance(recommendation, str) or not recommendation.strip():
        recommendation = "Review the original source before relying on this result."
    return {
        "status": status,
        "explanation": explanation,
        "evidence_excerpt": excerpt,
        "confidence": confidence,
        "confidence_note": "Uncalibrated model confidence indicator; not a probability.",
        "limitations": list(dict.fromkeys(limitations)),
        "human_review_recommendation": recommendation,
        "comparison_flags": [str(flag) for flag in flags],
    }