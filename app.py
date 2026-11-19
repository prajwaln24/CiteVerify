import streamlit as st
import pymupdf
from report import build_markdown_report, summarize_verdicts

st.set_page_config(page_title="CiteVerify", page_icon="📄", layout="wide")

st.title("CiteVerify — Scientific Claim & Citation Verification")
st.caption(
    "Upload a research paper PDF to inspect extracted claims, citations, source evidence, "
    "confidence indicators, and downloadable verification reports."
)
st.info(
    "**Human Review Reminder:** Confidence scores reflect evidence alignment and uncertainty—"
    "not a guarantee or final academic judgment. Always inspect original sources for critical claims."
)

SAMPLE_RESULTS = [
    {
        "claim": "A particular study found that a learning app improved test scores by 30%.",
        "citation": "[1] Author et al., 2024",
        "citation_status": "Source Found — Metric Mismatch Check",
        "verdict": "Partially Supported",
        "confidence": 0.68,
        "reason": "The cited study reports score gains in a small pilot group, but does not state a 30% improvement.",
        "evidence": "Pilot participants showed modest post-test gains over baseline; exact percentage gains varied across subgroups.",
        "uncertainty": "Small pilot sample size; exact 30% claim was not found in the retrieved excerpt.",
        "source_link": "https://example.org/pilot-study",
    },
    {
        "claim": "Transformer models eliminate recurrence by relying on self-attention mechanisms.",
        "citation": "(Vaswani et al., 2017)",
        "citation_status": "Citation Matched",
        "verdict": "Supported",
        "confidence": 0.94,
        "reason": "Directly aligns with the architecture introduced in the cited paper.",
        "evidence": "The Transformer relies entirely on self-attention to compute representations without sequence-aligned RNNs or convolution.",
        "uncertainty": "High alignment with primary paper abstract/introduction.",
        "source_link": "https://arxiv.org/abs/1706.03762",
    },
    {
        "claim": "All deep learning models require zero labeled data to reach state-of-the-art accuracy.",
        "citation": "[4] Survey on Deep Learning, 2020",
        "citation_status": "Potentially Misleading / Overstated",
        "verdict": "Contradictory",
        "confidence": 0.22,
        "reason": "The cited survey highlights reliance on labeled or fine-tuned data for top benchmarks.",
        "evidence": "Supervised pretraining and labeled task datasets remain central across many benchmarks reviewed.",
        "uncertainty": "Low confidence due to conflicting statement against cited literature.",
        "source_link": "https://example.org/dl-survey",
    },
]


def normalize_result(raw: dict) -> dict:
    """Safely normalize fields so varying teammate output keys won't crash the UI."""
    conf_raw = raw.get("confidence", raw.get("score", 0.0))
    try:
        conf_val = float(conf_raw)
        if conf_val > 1.0:
            conf_val = conf_val / 100.0
        conf_val = max(0.0, min(1.0, conf_val))
    except (TypeError, ValueError):
        conf_val = 0.0

    return {
        "claim": str(raw.get("claim", "Untitled claim")),
        "citation": str(raw.get("citation", "No citation detected")),
        "citation_status": str(raw.get("citation_status", "Needs verification")),
        "verdict": str(raw.get("verdict", "Needs Review")),
        "confidence": conf_val,
        "reason": str(raw.get("reason", "No explanation provided.")),
        "evidence": str(raw.get("evidence", "No source passage available.")),
        "uncertainty": str(raw.get("uncertainty", "Review full source text to confirm context.")),
        "source_link": str(raw.get("source_link", "")),
    }


if "results" not in st.session_state:
    st.session_state["results"] = []
if "paper_name" not in st.session_state:
    st.session_state["paper_name"] = ""

col_upload, col_actions = st.columns([3, 1])
with col_upload:
    uploaded_pdf = st.file_uploader("Upload a research paper (PDF)", type=["pdf"])
    if uploaded_pdf is not None:
        st.caption(f"Selected file: **{uploaded_pdf.name}** ({round(uploaded_pdf.size / 1024, 1)} KB)")

with col_actions:
    st.write("")
    st.write("")
    run_verify = st.button("Verify Paper", type="primary", use_container_width=True)
    use_sample = st.button("Load Sample Demo Data", use_container_width=True)
    clear_btn = st.button("Clear Results", use_container_width=True)

if clear_btn:
    st.session_state["results"] = []
    st.session_state["paper_name"] = ""
    st.rerun()

if use_sample:
    st.session_state["paper_name"] = "sample_research_paper.pdf"
    st.session_state["results"] = [normalize_result(r) for r in SAMPLE_RESULTS]

if run_verify:
    if uploaded_pdf is None:
        st.warning("Please upload a PDF file first, or click 'Load Sample Demo Data' to test the interface.")
    else:
        st.session_state["paper_name"] = uploaded_pdf.name
        try:
            with st.spinner("Extracting claims, matching citations, retrieving sources, and checking evidence..."):
                # TODO: Replace SAMPLE_RESULTS with your team's pipeline functions:
                # text = pdf_reader.extract_text(uploaded_pdf)
                # claims = claim_extractor.extract_claims(text)
                # citations = citation_extractor.extract_citations(text)
                # sources = research_retriever.retrieve_sources(citations)
                # raw_results = evidence_checker.verify_claims(claims, citations, sources)
                raw_results = SAMPLE_RESULTS

            st.session_state["results"] = [normalize_result(r) for r in raw_results]
            if not st.session_state["results"]:
                st.warning("No claims were returned for this document. Try another PDF or inspect the extractor output.")
        except Exception as exc:
            st.error(f"Something went wrong while processing the PDF: {exc}")

results = st.session_state["results"]

if results:
    st.divider()
    st.subheader(f"Verification Dashboard — {st.session_state['paper_name']}")

    summary = summarize_verdicts(results)
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total Claims", summary["total"])
    m2.metric("Supported", summary["supported"])
    m3.metric("Partially Supported", summary["partially_supported"])
    m4.metric("Contradictory / Outdated", summary["contradictory_or_outdated"])
    m5.metric("Unsupported / Review", summary["unsupported_or_review"])

    f1, f2 = st.columns([2, 2])
    with f1:
        verdict_options = ["All"] + sorted({r["verdict"] for r in results})
        selected_verdict = st.selectbox("Filter by verdict", verdict_options)
    with f2:
        sort_order = st.selectbox(
            "Sort claims by",
            ["Default Order", "Lowest Confidence First (Needs Review)", "Highest Confidence First"],
        )

    filtered_results = [
        r for r in results if selected_verdict == "All" or r["verdict"] == selected_verdict
    ]
    if sort_order == "Lowest Confidence First (Needs Review)":
        filtered_results = sorted(filtered_results, key=lambda x: x["confidence"])
    elif sort_order == "Highest Confidence First":
        filtered_results = sorted(filtered_results, key=lambda x: x["confidence"], reverse=True)

    report_md = build_markdown_report(st.session_state["paper_name"] or "paper.pdf", results)
    st.download_button(
        label="Download Verification Report (.md)",
        data=report_md,
        file_name="citeverify_report.md",
        mime="text/markdown",
    )

    st.subheader("Verification Result Cards")
    for item in filtered_results:
        verdict = item["verdict"]
        confidence = item["confidence"]
        conf_pct = int(round(confidence * 100))

        with st.container(border=True):
            left, right = st.columns([3, 1])

            with left:
                st.markdown(f"**Claim:** {item['claim']}")
                st.caption(f"**Citation:** {item['citation']}  |  **Citation Check:** {item['citation_status']}")
                st.write(f"**Explanation:** {item['reason']}")

            with right:
                v_lower = verdict.lower()
                if v_lower == "supported":
                    st.success(f"Verdict: {verdict}")
                elif "part" in v_lower or "outdated" in v_lower:
                    st.warning(f"Verdict: {verdict}")
                else:
                    st.error(f"Verdict: {verdict}")

                st.progress(confidence, text=f"Confidence: {conf_pct}%")

            with st.expander("Evidence, Uncertainty & Source Trace"):
                st.markdown("**Retrieved Evidence / Source Passage:**")
                st.write(item["evidence"])
                st.markdown("**Uncertainty & Review Notes:**")
                st.caption(item["uncertainty"])
                if item["source_link"]:
                    st.markdown(f"**Source Link:** [{item['source_link']}]({item['source_link']})")
                else:
                    st.caption("No source link available.")