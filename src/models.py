"""Shared data models for the Literature Review Agent Tool."""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class Author:
    """Paper author information."""
    name: str
    affiliation: Optional[str] = None


@dataclass
class Paper:
    """Represents a single academic paper with metadata."""

    # Core identifiers
    arxiv_id: str
    title: str
    abstract: str

    # Authors
    authors: list[Author] = field(default_factory=list)

    # Publication info
    year: int = 0
    published_date: Optional[str] = None
    journal: Optional[str] = None

    # Links
    arxiv_url: Optional[str] = None
    pdf_url: Optional[str] = None

    # Code availability
    has_code: bool = False
    code_urls: list[str] = field(default_factory=list)

    # Metrics
    citation_count: int = 0
    influential_citation_count: int = 0

    # Source
    source: str = "arxiv"  # "arxiv" or "semantic_scholar"

    # Ranking
    relevance_score: float = 0.0
    rank_score: float = 0.0

    # Method category (populated during review generation)
    method_category: Optional[str] = None

    # Key results summary (populated during review generation)
    key_innovation: Optional[str] = None
    datasets_used: list[str] = field(default_factory=list)
    key_results: Optional[str] = None

    # OpenAlex enrichment (populated by openalex_client)
    openalex_id: Optional[str] = None
    referenced_works: list[str] = field(default_factory=list)
    oa_cited_by_count: int = 0
    oa_year: int = 0

    def __post_init__(self):
        if not self.arxiv_url and self.arxiv_id:
            self.arxiv_url = f"https://arxiv.org/abs/{self.arxiv_id}"
        if not self.pdf_url and self.arxiv_id:
            self.pdf_url = f"https://arxiv.org/pdf/{self.arxiv_id}.pdf"

    @property
    def first_author(self) -> str:
        """Return the first author's last name for citation."""
        if self.authors:
            parts = self.authors[0].name.split()
            return parts[-1] if parts else self.authors[0].name
        return "Unknown"

    @property
    def citation_key(self) -> str:
        """Generate a BibTeX citation key."""
        first = self.first_author.lower().replace(" ", "_")
        return f"{first}{self.year}_{self.arxiv_id.split('/')[-1][:6]}"

    @property
    def short_title(self) -> str:
        """Truncated title for display."""
        return self.title[:80] + "..." if len(self.title) > 80 else self.title
