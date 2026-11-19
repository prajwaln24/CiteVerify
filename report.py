"""CSV and PDF report generation for pipeline output."""

from __future__ import annotations

from io import BytesIO
from typing import Any

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from xml.sax.saxutils import escape


def _claim_row(claim: dict[str, Any]) -> dict[str, Any]:
    paper = claim.get("matched_paper") or {}
    papers = claim.get("papers") or ([paper] if paper else [])
    source_checks = claim.get("source_checks") or []
    citation_text = "; ".join(
        citation.get("citation", "") for citation in claim.get("citations", [])
    )
    return {
        "claim_number": claim.get("claim_number"),
        "claim": claim.get("claim"),
        "page_number": claim.get("page_number"),
        "citation": citation_text,
        "matched_reference": "; ".join(
            dict.fromkeys(
                item["reference"].get("text", "")
                for item in source_checks
                if item.get("reference", {}).get("text")
            )
        ) or (claim.get("matched_reference") or {}).get("text"),
        "paper_title": "; ".join(
            dict.fromkeys(item["title"] for item in papers if item.get("title"))
        ),
        "publication_year": "; ".join(
            dict.fromkeys(str(item["year"]) for item in papers if item.get("year"))
        ),
        "doi": "; ".join(dict.fromkeys(item["doi"] for item in papers if item.get("doi"))),
        "source_url": "; ".join(
            dict.fromkeys(item["source_url"] for item in papers if item.get("source_url"))
        ),
        "evidence_excerpt": claim.get("evidence_excerpt"),
        "evidence_type": "; ".join(
            dict.fromkeys(item["evidence"]["evidence_type"] for item in source_checks)
        ),
        "status": claim.get("status"),
        "explanation": claim.get("explanation"),
        "confidence_indicator": claim.get("confidence"),
        "confidence_note": claim.get("confidence_note"),
        "limitations": "; ".join(claim.get("limitations", [])),
        "human_review_recommendation": claim.get("human_review_recommendation"),
    }


def results_to_csv(analysis: dict[str, Any]) -> bytes:
    """Export all claim results as UTF-8 CSV bytes."""
    rows = [_claim_row(claim) for claim in analysis.get("claims", [])]
    columns = [
        "claim_number", "claim", "page_number", "citation", "matched_reference",
        "paper_title", "publication_year", "doi", "source_url", "evidence_excerpt",
        "evidence_type", "status", "explanation", "confidence_indicator",
        "confidence_note", "limitations", "human_review_recommendation",
    ]
    return pd.DataFrame(rows, columns=columns).to_csv(index=False).encode("utf-8-sig")


def generate_pdf_report(analysis: dict[str, Any]) -> bytes:
    """Generate a downloadable PDF report; reportlab is required."""
    output = BytesIO()
    document_info = analysis.get("document", {})
    summary = analysis.get("summary", {})
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], alignment=TA_CENTER))
    story = [
        Paragraph("CiteVerify — Scientific Claim Verification Report", styles["ReportTitle"]),
        Spacer(1, 0.2 * inch),
        Paragraph(f"Document: {escape(str(document_info.get('filename') or 'Uploaded PDF'))}", styles["BodyText"]),
        Paragraph(f"Pages: {escape(str(document_info.get('page_count', 'Unknown')))}", styles["BodyText"]),
        Paragraph(f"Claims analyzed: {escape(str(summary.get('total_claims', 0)))}", styles["BodyText"]),
        Spacer(1, 0.15 * inch),
        Paragraph("Status distribution", styles["Heading2"]),
    ]
    distribution = [["Status", "Count"]] + [
        [status, str(count)]
        for status, count in summary.get("status_counts", {}).items()
    ]
    table = Table(distribution, repeatRows=1, colWidths=[3.7 * inch, 1 * inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#18324B")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([table, Spacer(1, 0.25 * inch)])

    for claim in analysis.get("claims", []):
        paper = claim.get("matched_paper") or {}
        story.append(Paragraph(f"Claim {claim.get('claim_number', '')}", styles["Heading2"]))
        fields = [
            ("Claim", claim.get("claim")),
            ("Page", claim.get("page_number")),
            ("Citation", "; ".join(c.get("citation", "") for c in claim.get("citations", []))),
            ("Matched paper", paper.get("title")),
            ("Year / DOI", " / ".join(str(item) for item in (paper.get("year"), paper.get("doi")) if item)),
            ("Source URL", paper.get("source_url")),
            ("Status", claim.get("status")),
            ("Evidence", claim.get("evidence_excerpt")),
            ("Explanation", claim.get("explanation")),
            ("Confidence indicator", claim.get("confidence")),
            ("Limitations", "; ".join(claim.get("limitations", []))),
            ("Human review", claim.get("human_review_recommendation")),
        ]
        for label, value in fields:
            if value not in (None, ""):
                story.append(
                    Paragraph(f"<b>{escape(label)}:</b> {escape(str(value))}", styles["BodyText"])
                )
                story.append(Spacer(1, 0.04 * inch))
        story.append(Spacer(1, 0.15 * inch))
    SimpleDocTemplate(output, pagesize=letter, title="CiteVerify report").build(story)
    return output.getvalue()