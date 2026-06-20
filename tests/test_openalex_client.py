import json
from src.models import Paper
from src import openalex_client as oc


class FakeResp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
    def json(self):
        return self._payload


class FakeSession:
    """Records requested URLs and returns queued responses."""
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params or {}))
        return self._responses.pop(0)


def test_bare_id_strips_url():
    assert oc._bare_id("https://openalex.org/W123") == "W123"
    assert oc._bare_id("W456") == "W456"
    assert oc._bare_id("") == ""


def test_strip_arxiv_version():
    assert oc._strip_arxiv_version("2211.12792v2") == "2211.12792"
    assert oc._strip_arxiv_version("2211.12792") == "2211.12792"


def test_title_similarity_fraction_of_query_tokens():
    # all query tokens present in candidate -> 1.0
    assert oc._title_similarity("graph neural", "deep graph neural networks") == 1.0
    assert oc._title_similarity("", "anything") == 0.0


def test_parse_work_normalizes_ids():
    work = oc._parse_work({
        "id": "https://openalex.org/W1",
        "title": "T",
        "publication_year": 2022,
        "cited_by_count": 5,
        "referenced_works": ["https://openalex.org/W2", "https://openalex.org/W3"],
        "doi": "https://doi.org/10.48550/arxiv.2211.12792",
        "ids": {"arxiv": "2211.12792"},
    })
    assert work.openalex_id == "W1"
    assert work.referenced_works == ["W2", "W3"]
    assert work.year == 2022 and work.cited_by_count == 5
    assert work.arxiv_id == "2211.12792"


def test_resolve_work_via_doi():
    payload = {
        "id": "https://openalex.org/W4309955051",
        "title": "MECCH",
        "publication_year": 2022,
        "cited_by_count": 3,
        "referenced_works": ["https://openalex.org/W2"],
        "ids": {},
    }
    sess = FakeSession([FakeResp(200, payload)])
    client = oc.OpenAlexClient(session=sess)
    paper = Paper(arxiv_id="2211.12792v2", title="MECCH", abstract="")
    work = client.resolve_work(paper)
    assert work is not None and work.openalex_id == "W4309955051"
    # DOI route used, version stripped, select param present
    url, params = sess.calls[0]
    assert "/works/doi:10.48550/arXiv.2211.12792" in url
    assert params["select"] == oc.OA_SELECT
    assert params["mailto"]


def test_resolve_by_title_picks_best_by_similarity_and_year():
    results = {"results": [
        {"id": "https://openalex.org/Wbad", "title": "Totally unrelated work",
         "publication_year": 2018, "cited_by_count": 0, "referenced_works": [], "ids": {}},
        {"id": "https://openalex.org/Wgood", "title": "MECCH Metapath Context Convolution",
         "publication_year": 2022, "cited_by_count": 9,
         "referenced_works": ["https://openalex.org/W2"],
         "doi": "https://doi.org/10.48550/arxiv.2211.12792", "ids": {}},
    ]}
    # DOI route fails (404 -> None payload), then title route returns results
    sess = FakeSession([FakeResp(404, {}), FakeResp(200, results)])
    client = oc.OpenAlexClient(session=sess)
    paper = Paper(arxiv_id="2211.12792", title="MECCH Metapath Context Convolution", abstract="", year=2022)
    work = client.resolve_work(paper)
    assert work is not None and work.openalex_id == "Wgood"
    title_call = sess.calls[1]
    assert title_call[1]["select"] == oc.OA_SELECT
    assert title_call[1]["per_page"] == 5


def test_resolve_prefers_version_with_references_when_preprint_empty():
    # arXiv preprint record resolves but has EMPTY referenced_works (common in OpenAlex);
    # must fall back to title search and pick the published version that HAS references.
    preprint = {
        "id": "https://openalex.org/Wpre", "title": "MECCH",
        "publication_year": 2022, "cited_by_count": 0,
        "referenced_works": [], "ids": {},
    }
    published = {"results": [{
        "id": "https://openalex.org/Wpub", "title": "MECCH Metapath Context Convolution",
        "publication_year": 2023, "cited_by_count": 9,
        "referenced_works": ["https://openalex.org/W2", "https://openalex.org/W3"], "ids": {},
    }]}
    sess = FakeSession([FakeResp(200, preprint), FakeResp(200, published)])
    client = oc.OpenAlexClient(session=sess)
    paper = Paper(arxiv_id="2211.12792", title="MECCH Metapath Context Convolution", abstract="", year=2022)
    work = client.resolve_work(paper)
    assert work.openalex_id == "Wpub"
    assert work.referenced_works == ["W2", "W3"]


def test_resolve_by_title_sanitizes_comma_in_filter():
    # A comma in the title must NOT reach the OpenAlex filter (it would be parsed as a
    # filter separator -> HTTP 400). The filter value must be sanitized.
    results = {"results": [{
        "id": "https://openalex.org/W1",
        "title": "Tokens to Token ViT Training Vision Transformers",
        "publication_year": 2021, "cited_by_count": 5,
        "referenced_works": ["https://openalex.org/W2"], "ids": {},
    }]}
    sess = FakeSession([FakeResp(404, {}), FakeResp(200, results)])
    client = oc.OpenAlexClient(session=sess)
    paper = Paper(arxiv_id="2101.11986",
                  title="Tokens-to-Token ViT, Training Vision Transformers from Scratch",
                  abstract="", year=2021)
    work = client.resolve_work(paper)
    assert work is not None and work.openalex_id == "W1"
    title_filter = sess.calls[1][1]["filter"]
    assert "," not in title_filter and "|" not in title_filter


def test_fetch_works_by_ids_batches_and_parses():
    payload = {"results": [
        {"id": "https://openalex.org/W2", "title": "Ancestor", "publication_year": 2017,
         "cited_by_count": 100, "referenced_works": [], "ids": {}},
    ]}
    sess = FakeSession([FakeResp(200, payload)])
    client = oc.OpenAlexClient(session=sess)
    works = client.fetch_works_by_ids(["W2"])
    assert "W2" in works and works["W2"].cited_by_count == 100
    url, params = sess.calls[0]
    assert params["filter"] == "openalex:W2"
    assert params["per_page"] == 50


def test_enrich_papers_sets_fields():
    payload = {
        "id": "https://openalex.org/W1", "title": "P", "publication_year": 2023,
        "cited_by_count": 7, "referenced_works": ["https://openalex.org/W2"], "ids": {},
    }
    sess = FakeSession([FakeResp(200, payload)])
    client = oc.OpenAlexClient(session=sess)
    papers = [Paper(arxiv_id="2305.00001", title="P", abstract="", year=2023)]
    client.enrich_papers(papers)
    assert papers[0].openalex_id == "W1"
    assert papers[0].referenced_works == ["W2"]
    assert papers[0].oa_cited_by_count == 7 and papers[0].oa_year == 2023
