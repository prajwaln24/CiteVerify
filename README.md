# CiteVerify backend

CiteVerify is a Python backend that extracts text, citations, references, and
verbatim scientific claims from a research-paper PDF, looks up cited papers,
compares claims with available source evidence, and exports CSV/PDF reports.
This project stage is **backend only**; the existing `app.py` is intentionally
not changed into a user interface.

## Architecture

```text
PDF bytes/path
  -> pdf_reader.py (PyMuPDF text and document metadata)
  -> citation_extractor.py (in-text citations and bibliography entries)
  -> claim_extractor.py (verbatim claims via OpenRouter)
  -> reference_matcher.py (citation keys to bibliography)
  -> research_retriever.py (Crossref + Semantic Scholar metadata)
  -> evidence_extractor.py (open PDF when available, otherwise abstract)
  -> evidence_checker.py (evidence-constrained OpenRouter assessment)
  -> verification_pipeline.py (orchestration and conservative statuses)
  -> report.py (CSV and PDF exports)
```

The public entry point is `verification_pipeline.run_verification`. Individual
modules can also be called directly. The function returns a dictionary with
document metadata, page text, citations, references, claim results, source
evidence, per-status totals, and explicit limitations.

## Requirements and API keys

- Python 3.10 or later (Python 3.13 is supported by the current environment).
- **OpenRouter API key is required** for claim extraction and evidence
  comparison. Create one at <https://openrouter.ai/keys> and configure it
  locally as `OPENROUTER_API_KEY`. Gemini and direct OpenAI API keys cannot be
  used with this integration. The default `openrouter/free` model router selects
  from currently available free models; free-model availability and rate limits
  can change.
- Crossref lookups need **no API key**.
- Semantic Scholar lookups are attempted without a key; an optional
  `SEMANTIC_SCHOLAR_API_KEY` can be set for its API quotas.
- Neither API key is stored in this repository. Do not commit `.env`.
- Document text sent for AI extraction and verification is transmitted to the
  configured OpenRouter service. Do not upload documents you are not permitted to
  share with that provider.

## Setup on Windows

1. Install Python 3.10+ from <https://www.python.org/downloads/windows/>. During
   installation, enable **Add python.exe to PATH**.
2. Open PowerShell in this project folder.
3. Create and activate a virtual environment:

   ```powershell
   py -3 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope
   CurrentUser RemoteSigned` once, then activate again. Alternatively, skip
   activation and use `.\.venv\Scripts\python.exe` for the commands below.
4. Install dependencies:

   ```powershell
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```
5. Create the local environment file and add your OpenRouter API key:

   ```powershell
   Copy-Item .env.example .env
   notepad .env
   ```

   Set `OPENROUTER_API_KEY=your_key_here`. Leave the Semantic Scholar key empty if
   you do not have one. `.env` is ignored by Git.
6. Run the tests:

   ```powershell
   python -m unittest discover -s tests -v
   ```

## Backend usage

```python
from pathlib import Path

from report import generate_pdf_report, results_to_csv
from verification_pipeline import run_verification


def progress(message: str) -> None:
    print(message)


analysis = run_verification(
    Path("paper.pdf"),
    progress_callback=progress,
)

Path("verification.csv").write_bytes(results_to_csv(analysis))
Path("verification-report.pdf").write_bytes(generate_pdf_report(analysis))
print(analysis["summary"])
```

`run_verification` accepts a filesystem path, PDF bytes, or a binary stream.
The optional `filename` argument sets the displayed document name. The optional
`progress_callback` receives stage messages. Tests and other callers can pass
`generate_json_fn` to inject a controlled JSON-producing function; normal usage
uses the OpenRouter service.

## Evidence and result interpretation

- The report distinguishes **full-text** from **abstract-only** evidence.
  When an open PDF is advertised by Semantic Scholar, the backend attempts to
  retrieve it (20 MB and 80 page limits); failed retrieval falls back to the
  abstract when available and records why.
- Metadata-only results are not treated as evidence. Missing sources, uncertain
  citation matches, or unverifiable AI evidence excerpts produce
  `NEEDS HUMAN REVIEW`.
- Returned paper searches are API metadata candidates, not proof that a
  citation supports a claim. Title-only candidates must clear a similarity
  threshold before verification. DOI and source links are included only when
  returned/validated through source metadata.
- Evidence excerpts are checked against the retrieved source text. The backend
  preserves extracted claim wording and does not treat an abstract as a full
  paper.
- Confidence is an **uncalibrated model indicator**, not a scientifically
  calibrated probability. Results are decision support, not a final scientific
  judgment. A researcher should inspect linked sources and resolve every
  `NEEDS HUMAN REVIEW` result.

## Tests

The test suite creates its own small PDF and mocks research API calls. It checks
PDF extraction, citation/reference matching, abstract labeling, missing-evidence
fallback, metadata deduplication, and report exports. It does not require a live
OpenRouter key or make live Crossref/Semantic Scholar calls.
