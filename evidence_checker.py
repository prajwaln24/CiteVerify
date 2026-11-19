import re

NEGATION_WORDS = {
    "no", "not", "never", "none", "neither", "fail", "failed", "fails",
    "ineffective", "contradict", "contradicts", "refute", "refutes",
    "decrease", "decreases", "reduced", "lack", "lacks", "without",
}


def _tokenize(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    stop_words = {
        "the", "and", "for", "with", "that", "this", "from", "are", "was",
        "were", "has", "have", "had", "into", "using", "used", "study", "paper",
    }
    return {t for t in tokens if len(t) > 2 and t not in stop_words}


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in parts if len(s.strip()) > 15]


def compare_claim_to_source(claim_text: str, source_paper: dict) -> dict:
    findings_text = (source_paper.get("abstract") or "").strip()
    if not findings_text:
        return {
            "evidence": "No source abstract or findings text was retrieved for verification.",
            "overlap_score": 0.0,
            "stance": "insufficient",
        }

    claim_tokens = _tokenize(claim_text)
    sentences = _split_sentences(findings_text) or [findings_text]

    best_sentence = sentences[0]
    best_score = 0.0

    for sent in sentences:
        sent_tokens = _tokenize(sent)
        if not claim_tokens or not sent_tokens:
            continue
        score = len(claim_tokens & sent_tokens) / len(claim_tokens)
        if score > best_score:
            best_score = score
            best_sentence = sent

    claim_neg = bool(claim_tokens & NEGATION_WORDS)
    sent_neg = bool(_tokenize(best_sentence) & NEGATION_WORDS)

    if best_score < 0.15:
        stance = "insufficient"
    elif claim_neg != sent_neg and best_score >= 0.25:
        stance = "contradict"
    elif best_score >= 0.25:
        stance = "support"
    else:
        stance = "insufficient"

    return {
        "evidence": best_sentence,
        "overlap_score": round(min(best_score, 1.0), 2),
        "stance": stance,
    }