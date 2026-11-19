def summarize_verdicts(results: list[dict]) -> dict:
    """Count claims across key verification categories."""
    summary = {
        "total": len(results),
        "supported": 0,
        "partially_supported": 0,
        "contradictory_or_outdated": 0,
        "unsupported_or_review": 0,
    }
    for item in results:
        verdict = str(item.get("verdict", "")).strip().lower()
        if verdict == "supported":
            summary["supported"] += 1
        elif "part" in verdict:
            summary["partially_supported"] += 1
        elif "contradict" in verdict or "outdated" in verdict:
            summary["contradictory_or_outdated"] += 1
        else:
            summary["unsupported_or_review"] += 1
    return summary


def build_markdown_report(paper_name: str, results: list[dict]) -> str:
    """Create a clean Markdown verification report for download or review."""
    summary = summarize_verdicts(results)
    lines = [
        f"# CiteVerify Verification Report: {paper_name}",
        "",
        "## Summary",
        f"- **Total Claims Checked:** {summary['total']}",
        f"- **Supported:** {summary['supported']}",
        f"- **Partially Supported:** {summary['partially_supported']}",
        f"- **Contradictory / Possibly Outdated:** {summary['contradictory_or_outdated']}",
        f"- **Unsupported / Needs Human Review:** {summary['unsupported_or_review']}",
        "",
        "> **Human Review Notice:** Automated verdicts and confidence scores indicate evidence strength "
        "and potential uncertainty—they are not final academic judgment. Please review original sources.",
        "",
        "## Claim-by-Claim Verification Findings",
        "",
    ]

    for idx, item in enumerate(results, start=1):
        raw_conf = item.get("confidence", 0.0)
        try:
            conf_val = max(0.0, min(1.0, float(raw_conf)))
        except (TypeError, ValueError):
            conf_val = 0.0
        confidence_pct = int(round(conf_val * 100))

        lines.extend([
            f"### {idx}. {item.get('verdict', 'Needs Review')} ({confidence_pct}% confidence)",
            f"- **Claim:** {item.get('claim', 'N/A')}",
            f"- **Citation:** {item.get('citation', 'N/A')}",
            f"- **Citation Status:** {item.get('citation_status', 'Matched / Needs Check')}",
            f"- **Explanation:** {item.get('reason', 'No explanation provided.')}",
            f"- **Evidence & Context:** {item.get('evidence', 'No evidence passage available.')}",
            f"- **Uncertainty / Limitations:** {item.get('uncertainty', 'Verify full source context.')}",
            f"- **Source Link:** {item.get('source_link', 'N/A')}",
            "",
        ])

    return "\n".join(lines)