"""Tests for evolution_diagram module."""

import os
import tempfile

from src.models import Paper, Author
from src.evolution_diagram import (
    generate_evolution_diagram,
    generate_category_distribution_chart,
)


def test_generate_evolution_diagram():
    """Test that evolution diagram is created."""
    papers = [
        Paper(
            arxiv_id=f"id{i}",
            title=f"Paper {i}: An AI Method",
            abstract="...",
            authors=[Author(name=f"Author {i}")],
            year=2020 + i,
            citation_count=100 * i + 50,
            method_category="Transformer" if i % 2 == 0 else "GNN",
        )
        for i in range(6)
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, "evolution.png")
        result = generate_evolution_diagram(papers, "Test Topic", output_path=output_path)

        assert result == output_path
        assert os.path.exists(output_path)
        assert os.path.getsize(output_path) > 0


def test_generate_evolution_diagram_empty():
    """Test that empty papers produce no output."""
    result = generate_evolution_diagram([], "Test Topic")
    assert result == ""


def test_generate_category_distribution():
    """Test category distribution chart generation."""
    papers = [
        Paper(
            arxiv_id=f"id{i}",
            title=f"Paper {i}",
            abstract="...",
            authors=[Author(name=f"Author {i}")],
            year=2020 + i,
            method_category="Transformer" if i % 2 == 0 else "GNN",
        )
        for i in range(4)
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, "distribution.png")
        result = generate_category_distribution_chart(papers, output_path=output_path)

        assert result == output_path
        assert os.path.exists(output_path)
        assert os.path.getsize(output_path) > 0


def test_evolution_diagram_uncategorized():
    """Test diagram with uncategorized papers."""
    papers = [
        Paper(
            arxiv_id=f"id{i}",
            title=f"Paper {i}",
            abstract="...",
            authors=[Author(name=f"Author {i}")],
            year=2022 + i,
            method_category=None,  # No category
        )
        for i in range(3)
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, "evolution_uncat.png")
        result = generate_evolution_diagram(papers, "Topic", output_path=output_path)

        assert os.path.exists(output_path)
        assert os.path.getsize(output_path) > 0
