import requests


def _reconstruct_abstract(inverted_index: dict | None) -> str:
    if not inverted_index:
        return ""
    words_by_pos: list[tuple[int, str]] = []
    for word, positions in inverted_index.items():
        for pos in positions:
            words_by_pos.append((pos, word))
    words_by_pos.sort(key=lambda item: item[0])
    return " ".join(word for _, word in words_by_pos)


def fetch_by_doi(doi: str) -> dict | None:
    clean_doi = doi.strip().removeprefix("https://doi.org/").removeprefix("http://doi.org/")
    if not clean_doi:
        return None
    url = f"https://api.openalex.org/works/https://doi.org/{clean_doi}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        authors = [
            a.get("author", {}).get("display_name", "")
            for a in data.get("authorships", [])
            if a.get("author", {}).get("display_name")
        ]
        abstract = _reconstruct_abstract(data.get("abstract_inverted_index"))
        return {
            "doi": clean_doi,
            "title": data.get("title") or "Unknown Title",
            "authors": authors,
            "year": data.get("publication_year"),
            "venue": (data.get("primary_location") or {}).get("source", {}).get("display_name") or "Unknown Venue",
            "abstract": abstract,
            "source_link": data.get("doi") or f"https://doi.org/{clean_doi}",
        }
    except requests.RequestException:
        return None


def search_by_title_author(title: str, author: str = "") -> dict | None:
    query = f"{title} {author}".strip()
    if not query:
        return None
    params = {"search": query, "per-page": 1}
    try:
        resp = requests.get("https://api.openalex.org/works", params=params, timeout=10)
        if resp.status_code != 200:
            return None
        results = resp.json().get("results", [])
        if not results:
            return None
        top = results[0]
        authors = [
            a.get("author", {}).get("display_name", "")
            for a in top.get("authorships", [])
            if a.get("author", {}).get("display_name")
        ]
        abstract = _reconstruct_abstract(top.get("abstract_inverted_index"))
        doi_raw = top.get("doi") or ""
        return {
            "doi": doi_raw.removeprefix("https://doi.org/"),
            "title": top.get("title") or title,
            "authors": authors,
            "year": top.get("publication_year"),
            "venue": (top.get("primary_location") or {}).get("source", {}).get("display_name") or "Unknown Venue",
            "abstract": abstract,
            "source_link": doi_raw or top.get("id") or "",
        }
    except requests.RequestException:
        return None


def retrieve_publication(doi: str = "", title: str = "", author: str = "") -> dict:
    paper = fetch_by_doi(doi) if doi else None
    if not paper and title:
        paper = search_by_title_author(title=title, author=author)
    if paper:
        return paper
    return {
        "doi": doi,
        "title": title or "Unresolved Source",
        "authors": [author] if author else [],
        "year": None,
        "venue": "Not Found",
        "abstract": "",
        "source_link": f"https://doi.org/{doi}" if doi else "",
    }
