"""Tests for paper_fetcher module."""

import pytest
from unittest.mock import MagicMock, patch

from src.models import Paper, Author
from src.paper_fetcher import search_arxiv, fetch_papers, _arxiv_result_to_paper


def test_paper_model():
    """Test Paper dataclass properties."""
    paper = Paper(
        arxiv_id="2106.09685",
        title="Attention Is All You Need",
        abstract="The dominant sequence transduction models...",
        authors=[Author(name="Ashish Vaswani"), Author(name="Noam Shazeer")],
        year=2017,
        citation_count=50000,
    )

    assert paper.first_author == "Vaswani"
    assert "Ashish" not in paper.first_author
    assert paper.arxiv_url == "https://arxiv.org/abs/2106.09685"
    assert paper.pdf_url == "https://arxiv.org/pdf/2106.09685.pdf"
    assert len(paper.short_title) <= 83  # 80 + "..."


def test_paper_citation_key():
    """Test citation key generation."""
    paper = Paper(
        arxiv_id="1706.03762",
        title="Attention Is All You Need",
        abstract="...",
        authors=[Author(name="Ashish Vaswani")],
        year=2017,
    )
    assert "vaswani" in paper.citation_key.lower()
    assert "2017" in paper.citation_key


def test_paper_code_urls():
    """Test paper with code URLs."""
    paper = Paper(
        arxiv_id="1706.03762",
        title="Test Paper",
        abstract="...",
        authors=[],
        year=2020,
        has_code=True,
        code_urls=["https://github.com/user/repo"],
    )
    assert paper.has_code is True
    assert len(paper.code_urls) == 1


@patch("src.paper_fetcher.arxiv.Client")
def test_search_arxiv_mocked(mock_client):
    """Test arXiv search with mocked client."""
    # Create a mock paper result
    mock_result = MagicMock()
    mock_result.entry_id = "http://arxiv.org/abs/2106.09685v1"
    mock_result.title = "Test Paper Title"
    mock_result.summary = "This is a test abstract."
    mock_result.authors = [MagicMock(name="John Doe")]
    mock_result.authors[0].name = "John Doe"
    mock_result.published.year = 2024
    mock_result.published.strftime.return_value = "2024-01-15"
    mock_result.pdf_url = "https://arxiv.org/pdf/2106.09685.pdf"

    mock_client_instance = mock_client.return_value
    mock_client_instance.results.return_value = [mock_result]

    papers = search_arxiv("test topic", max_results=5)

    assert len(papers) > 0


def test_fetch_papers_no_results():
    """Test fetch_papers handles empty results gracefully."""
    with patch("src.paper_fetcher.search_arxiv", return_value=[]):
        with patch("src.paper_fetcher.search_semantic_scholar", return_value=[]):
            papers = fetch_papers(
                "xyznonexistenttopic123456",
                max_results=5,
                include_ss=False,
            )
            assert papers == []


def test_rank_score_calculation():
    """Test that ranking produces meaningful scores."""
    from src.paper_ranker import rank_papers

    papers = [
        Paper(
            arxiv_id=f"id{i}",
            title=f"Paper about AI topic {i}",
            abstract=f"This paper discusses artificial intelligence and machine learning topic {i}",
            authors=[Author(name=f"Author {i}")],
            year=2024 - i,
            citation_count=100 * (5 - i),
            has_code=(i % 2 == 0),
        )
        for i in range(5)
    ]

    ranked = rank_papers(papers, "artificial intelligence machine learning")
    assert len(ranked) == 5
    # Papers with code should generally rank higher
    assert ranked[0].has_code or ranked[1].has_code
    # All papers should have a rank score
    assert all(p.rank_score > 0 for p in ranked)

    # First paper should have highest score
    assert ranked[0].rank_score >= ranked[-1].rank_score
