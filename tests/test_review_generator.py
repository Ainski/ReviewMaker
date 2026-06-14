"""Tests for review_generator module."""

import pytest
from unittest.mock import MagicMock, patch

from src.models import Paper, Author
from src.review_generator import _build_paper_context, _build_system_prompt


def test_build_paper_context():
    """Test building paper context for prompt (Chinese format)."""
    paper = Paper(
        arxiv_id="2106.09685",
        title="Test Paper: A Novel Approach",
        abstract="This paper proposes a new method...",
        authors=[Author(name="John Smith"), Author(name="Jane Doe")],
        year=2024,
        citation_count=42,
        has_code=True,
        code_urls=["https://github.com/test/repo"],
    )

    context = _build_paper_context(paper, 1)
    assert "论文 [1]" in context  # 论文 [1]
    assert "Test Paper: A Novel Approach" in context
    assert "John Smith, Jane Doe" in context
    assert "2024" in context
    assert "代码:" in context  # 代码:
    assert "github.com" in context


def test_build_paper_context_many_authors():
    """Test that author list is truncated at 5 (Chinese format)."""
    paper = Paper(
        arxiv_id="test",
        title="Test",
        abstract="...",
        authors=[Author(name=f"Author {i}") for i in range(10)],
        year=2024,
    )
    context = _build_paper_context(paper, 1)
    assert "等" in context  # 等


def test_build_system_prompt():
    """Test system prompt generation (Chinese version)."""
    prompt = _build_system_prompt()
    assert "文献综述" in prompt  # 文献综述
    assert "[1]" in prompt
    assert "引言" in prompt  # 引言
    assert "对比分析" in prompt  # 对比分析


def test_generate_review_error_handling():
    """Test that API errors are propagated."""
    from src.review_generator import generate_review

    papers = [Paper(
        arxiv_id="test",
        title="Test",
        abstract="Test",
        authors=[],
        year=2024,
    )]

    with patch("src.review_generator.OpenAI") as mock_openai:
        mock_openai.return_value.chat.completions.create.side_effect = Exception("API Error")
        with pytest.raises(Exception):
            generate_review(papers, "test topic", api_key="fake-key")
