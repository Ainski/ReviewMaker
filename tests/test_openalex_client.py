from src.openalex_client import OpenAlexClient, OpenAlexWork


def test_verify_foundational_returns_best_match(monkeypatch):
    client = OpenAlexClient()
    payload = {"results": [
        {"id": "https://openalex.org/W1", "display_name": "Attention Is All You Need",
         "publication_year": 2017, "cited_by_count": 130000, "referenced_works": []},
        {"id": "https://openalex.org/W2", "display_name": "Some Less Cited Work",
         "publication_year": 2017, "cited_by_count": 12, "referenced_works": []},
    ]}
    monkeypatch.setattr(client, "_get", lambda path, params: payload)
    w = client.verify_foundational("Attention Is All You Need", 2017)
    assert w is not None
    assert w.year == 2017
    assert w.cited_by_count == 130000
    assert w.openalex_id == "W1"


def test_verify_foundational_none_on_empty(monkeypatch):
    client = OpenAlexClient()
    monkeypatch.setattr(client, "_get", lambda path, params: {"results": []})
    assert client.verify_foundational("Nonexistent Paper XYZ", None) is None


def test_verify_foundational_rejects_loose_title_match(monkeypatch):
    """A high-cited but title-dissimilar paper must NOT be accepted."""
    client = OpenAlexClient()
    payload = {"results": [
        {"id": "https://openalex.org/W9", "display_name": "Attention Economy in Social Media",
         "publication_year": 2025, "cited_by_count": 9999, "referenced_works": []},
    ]}
    monkeypatch.setattr(client, "_get", lambda path, params: payload)
    assert client.verify_foundational("Attention Is All You Need", 2017) is None
