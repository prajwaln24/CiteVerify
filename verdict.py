def generate_verdict(
    claim_id: str,
    claim_text: str,
    citation_label: str,
    source_paper: dict,
    comparison: dict,
) -> dict:
    stance = comparison.get("stance", "insufficient")
    overlap = float(comparison.get("overlap_score", 0.0))
    evidence = comparison.get("evidence", "No evidence passage available.")

    if stance == "support":
        verdict = "Supported"
        confidence = round(min(0.95, 0.55 + overlap * 0.4), 2)
        uncertainty = (
            "Supported by matching source abstract text; verify full methodology "
            "and sample conditions in the original paper."
        )
    elif stance == "contradict":
        verdict = "Refuted"
        confidence = round(min(0.92, 0.5 + overlap * 0.4), 2)
        uncertainty = (
            "Potential polarity/negation mismatch against retrieved source text; "
            "requires human review of full context."
        )
    else:
        verdict = "Uncertain"
        confidence = round(max(0.2, min(0.54, 0.25 + overlap * 0.5)), 2)
        uncertainty = (
            "Insufficient overlap or missing full-text findings; manual verification "
            "recommended before accepting."
        )

    return {
        "claim_id": claim_id,
        "claim": claim_text,
        "citation": citation_label,
        "verdict": verdict,
        "confidence": confidence,
        "evidence": evidence,
        "uncertainty": uncertainty,
        "source_link": source_paper.get("source_link", ""),
    }