import unittest
import os
from types import SimpleNamespace
from unittest.mock import patch

import pymupdf as fitz

from citation_extractor import extract_citations, extract_references
from evidence_checker import verify_claim
from evidence_extractor import extract_source_evidence
from pdf_reader import read_pdf
from reference_matcher import match_citations_to_references
from report import results_to_csv, generate_pdf_report
from verification_pipeline import run_verification
from llm_service import LLMConfigurationError, generate_json


class BackendTests(unittest.TestCase):
    @patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True)
    @patch("llm_service.OpenAI")
    def test_llm_service_uses_openrouter_json_mode(self, openai_client):
        openai_client.return_value.chat.completions.create.return_value = SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))
            ]
        )
        self.assertEqual(generate_json("Return a JSON object."), {"ok": True})
        openai_client.assert_called_once_with(
            api_key="test-key",
            base_url="https://openrouter.ai/api/v1",
        )
        openai_client.return_value.chat.completions.create.assert_called_once_with(
            model="openrouter/free",
            messages=[{"role": "user", "content": "Return a JSON object."}],
            response_format={"type": "json_object"},
        )

    @patch.dict(os.environ, {}, clear=True)
    def test_llm_service_requires_openrouter_key(self):
        with self.assertRaisesRegex(LLMConfigurationError, "OPENROUTER_API_KEY"):
            generate_json("Return a JSON object.")

    def test_reads_pdf_bytes_and_metadata(self):
        pdf = fitz.open()
        page = pdf.new_page()
        page.insert_text((72, 72), "A scientific finding.")
        pdf.set_metadata({"title": "Sample Study"})
        data = pdf.tobytes()
        pdf.close()

        parsed = read_pdf(data)
        self.assertEqual(parsed["page_count"], 1)
        self.assertEqual(parsed["metadata"]["title"], "Sample Study")
        self.assertIn("scientific finding", parsed["pages"][0]["text"])

    def test_extracts_numeric_and_author_year_citations_and_matches_refs(self):
        pages = [{
            "page_number": 2,
            "text": "Results support the effect [1-3]. Smith et al. (2020) reported it. (Doe, 2021).",
        }]
        citations = extract_citations(pages)
        self.assertTrue(any(citation["keys"] == ["1", "2", "3"] for citation in citations))
        self.assertTrue(any("smith|2020" in citation["keys"] for citation in citations))

        refs = extract_references(
            "References\n[1] Smith, J. (2020). A useful study. Journal. DOI:10.1234/abc\n"
            "[2] Doe, A. (2021). Another study. Journal."
        )
        matched = match_citations_to_references(citations, refs)
        numeric = next(item for item in matched if item["style"] == "numeric")
        self.assertEqual(len(numeric["matched_references"]), 2)

    def test_does_not_count_bibliography_entries_as_in_text_citations(self):
        citations = extract_citations([{
            "page_number": 1,
            "text": "The result is promising [1].\nReferences\n[1] Smith, J. (2020). A study.",
        }])
        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0]["text"], "[1]")

    def test_abstract_fallback_is_labeled_and_never_calls_it_full_text(self):
        result = extract_source_evidence(
            {"abstract": "The treatment improved outcomes in adults."},
            "The treatment improved outcomes.",
        )
        self.assertEqual(result["evidence_type"], "abstract_only")
        self.assertTrue(any("Abstract-only" in item for item in result["limitations"]))

    def test_missing_evidence_requires_review_without_calling_model(self):
        result = verify_claim(
            "A claim", {}, {"evidence_text": "", "evidence_excerpts": []},
            lambda _: self.fail("Model should not be called without evidence"),
        )
        self.assertEqual(result["status"], "NEEDS HUMAN REVIEW")

    def test_reports_export_claims_to_csv_and_pdf(self):
        analysis = {
            "document": {"filename": "sample.pdf", "page_count": 1},
            "summary": {"total_claims": 1, "status_counts": {"SUPPORTED": 1}},
            "claims": [{
                "claim_number": 1, "claim": "Sample claim.", "page_number": 1,
                "citations": [], "matched_paper": {}, "status": "SUPPORTED",
                "confidence": 80, "confidence_note": "Uncalibrated indicator",
                "limitations": [], "source_checks": [],
            }],
        }
        csv_bytes = results_to_csv(analysis)
        self.assertIn(b"Sample claim.", csv_bytes)
        self.assertTrue(generate_pdf_report(analysis).startswith(b"%PDF"))

    @patch("verification_pipeline.search_papers")
    def test_pipeline_runs_with_injected_ai_and_retrieval(self, search_papers):
        pdf = fitz.open()
        page = pdf.new_page()
        page.insert_textbox(
            fitz.Rect(50, 50, 550, 750),
            "The treatment improved outcomes in adults [1].\n\n"
            "References\n[1] Smith, J. (2020). Treatment outcomes. Journal. DOI:10.1234/abc",
        )
        data = pdf.tobytes()
        pdf.close()
        search_papers.return_value = {
            "papers": [{
                "title": "Treatment outcomes", "authors": ["Jane Smith"], "year": 2020,
                "doi": "10.1234/abc", "source_url": "https://doi.org/10.1234/abc",
                "abstract": "The treatment improved outcomes in adults.",
                "open_access_pdf": None, "match_score": 1.0,
            }],
            "errors": [],
        }

        def fake_ai(prompt):
            if "Identify explicit, testable" in prompt:
                return {"claims": [{
                    "claim": "The treatment improved outcomes in adults",
                    "page_number": 1, "claim_type": "finding", "citations": ["[1]"],
                }]}
            return {
                "status": "SUPPORTED",
                "explanation": "The abstract reports the same finding.",
                "evidence_excerpt": "The treatment improved outcomes in adults.",
                "confidence": 85,
                "limitations": [],
                "human_review_recommendation": "Review the full paper.",
                "comparison_flags": [],
            }

        result = run_verification(data, generate_json_fn=fake_ai)
        self.assertEqual(result["summary"]["total_claims"], 1)
        self.assertEqual(result["claims"][0]["status"], "SUPPORTED")
        self.assertEqual(
            result["claims"][0]["source_checks"][0]["evidence"]["evidence_type"],
            "abstract_only",
        )
        self.assertEqual(result["claims"][0]["matched_paper"]["doi"], "10.1234/abc")

    @patch("research_retriever.requests.get")
    def test_doi_search_returns_api_metadata_without_fabrication(self, get):
        from research_retriever import search_papers

        crossref = unittest.mock.Mock()
        crossref.json.return_value = {"message": {
            "DOI": "10.1234/abc", "title": ["A real paper"],
            "author": [{"given": "Jane", "family": "Smith"}],
            "published": {"date-parts": [[2020]]}, "URL": "https://doi.org/10.1234/abc",
        }}
        crossref.raise_for_status.return_value = None
        semantic = unittest.mock.Mock()
        semantic.json.return_value = {
            "title": "A real paper", "authors": [{"name": "Jane Smith"}], "year": 2020,
            "externalIds": {"DOI": "10.1234/abc"}, "url": "https://www.semanticscholar.org/paper/id",
        }
        semantic.raise_for_status.return_value = None
        get.side_effect = [crossref, semantic]
        result = search_papers({"doi": "10.1234/abc"})
        self.assertEqual(len(result["papers"]), 1)
        self.assertEqual(result["papers"][0]["doi"], "10.1234/abc")
        self.assertEqual(result["papers"][0]["match_score"], 1.0)
        self.assertIsNone(result["papers"][0]["abstract"])


if __name__ == "__main__":
    unittest.main()
