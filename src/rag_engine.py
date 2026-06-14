"""RAG Engine — PDF full-text download, extraction, chunking, embedding, and retrieval."""

import logging
import os
import re
import hashlib
import tempfile
from dataclasses import dataclass, field
from typing import Optional

import requests
import fitz  # PyMuPDF

from src.models import Paper

logger = logging.getLogger(__name__)

# ---- Text Chunk Data Model ----

@dataclass
class TextChunk:
    """A chunk of text from a paper with metadata."""
    paper_arxiv_id: str
    chunk_index: int
    text: str
    section_title: str = ""
    page_number: int = 0
    char_start: int = 0
    char_end: int = 0


# ---- PDF Download ----

def download_pdf(paper: Paper, cache_dir: Optional[str] = None) -> Optional[str]:
    """
    Download the PDF for a paper from arXiv.

    Args:
        paper: Paper with arxiv_id
        cache_dir: Directory to cache PDFs (uses temp dir if None)

    Returns:
        Path to downloaded PDF, or None if download failed
    """
    if paper.arxiv_id.startswith("ss_"):
        logger.debug(f"Semantic Scholar paper, no arXiv PDF: {paper.arxiv_id}")
        return None

    if cache_dir is None:
        cache_dir = os.path.join(tempfile.gettempdir(), "paper_rag_cache")
    os.makedirs(cache_dir, exist_ok=True)

    # Use a hash-based filename for caching
    pdf_path = os.path.join(cache_dir, f"{paper.arxiv_id}.pdf")

    if os.path.exists(pdf_path):
        logger.debug(f"PDF cached: {pdf_path}")
        return pdf_path

    pdf_url = f"https://arxiv.org/pdf/{paper.arxiv_id}.pdf"
    try:
        logger.debug(f"Downloading PDF: {pdf_url}")
        resp = requests.get(pdf_url, timeout=30, stream=True)
        resp.raise_for_status()

        with open(pdf_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        logger.info(f"PDF downloaded: {pdf_path} ({os.path.getsize(pdf_path)} bytes)")
        return pdf_path
    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to download PDF for {paper.arxiv_id}: {e}")
        return None


# ---- Text Extraction ----

def _clean_text(text: str) -> str:
    """Clean extracted text: remove excessive whitespace, fix line breaks."""
    # Replace multiple newlines with double newline (paragraph break)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Fix hyphenation at line breaks (common in PDF extraction)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    # Remove single newlines within paragraphs
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    # Collapse multiple spaces
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def extract_text_from_pdf(pdf_path: str) -> tuple[str, list[dict]]:
    """
    Extract full text and images from a PDF.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        (full_text, images_info) where images_info is [{page, bbox, image_bytes}, ...]
    """
    doc = fitz.open(pdf_path)
    full_text_parts = []
    images_info = []

    for page_num, page in enumerate(doc):
        # Extract text
        text = page.get_text("text")
        if text.strip():
            full_text_parts.append(text)

        # Extract images
        image_list = page.get_images(full=True)
        for img_index, img in enumerate(image_list):
            xref = img[0]
            try:
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                # Only keep reasonably sized images (skip tiny icons/logos)
                if len(image_bytes) > 5000:
                    images_info.append({
                        "page": page_num + 1,
                        "xref": xref,
                        "image_bytes": image_bytes,
                        "ext": base_image["ext"],
                        "width": base_image["width"],
                        "height": base_image["height"],
                        "size_bytes": len(image_bytes),
                    })
            except Exception:
                continue

    doc.close()
    full_text = "\n\n".join(full_text_parts)
    full_text = _clean_text(full_text)
    return full_text, images_info


# ---- Text Chunking ----

def chunk_text(
    text: str,
    paper_arxiv_id: str,
    chunk_size: int = 800,
    chunk_overlap: int = 150,
) -> list[TextChunk]:
    """
    Split paper text into overlapping chunks for RAG retrieval.
    Respects section boundaries from Markdown-style headers (## Section).

    Args:
        text: Full paper text
        paper_arxiv_id: arXiv ID for metadata
        chunk_size: Target chunk size in characters
        chunk_overlap: Overlap between consecutive chunks

    Returns:
        List of TextChunk objects
    """
    # Try to split by sections first
    sections = re.split(r"(#{1,3}\s+.+?(?:\n|$))", text)

    chunks = []
    chunk_idx = 0
    current_section = ""

    i = 0
    while i < len(sections):
        part = sections[i]

        # Check if this is a section header
        if re.match(r"^#{1,3}\s+", part):
            current_section = part.strip().lstrip("#").strip()
            i += 1
            if i < len(sections):
                section_text = sections[i]
            else:
                break
        else:
            section_text = part

        # Chunk this section
        if len(section_text.strip()) < 50:
            i += 1
            continue

        start = 0
        while start < len(section_text):
            end = min(start + chunk_size, len(section_text))
            # Try to break at sentence boundary
            if end < len(section_text):
                boundary = max(
                    section_text.rfind(". ", start, end),
                    section_text.rfind("。", start, end),
                    section_text.rfind("\n", start, end),
                )
                if boundary > start + chunk_size // 2:
                    end = boundary + 1

            chunk_text_val = section_text[start:end].strip()
            if len(chunk_text_val) > 50:
                chunks.append(TextChunk(
                    paper_arxiv_id=paper_arxiv_id,
                    chunk_index=chunk_idx,
                    text=chunk_text_val,
                    section_title=current_section,
                    char_start=start,
                    char_end=end,
                ))
                chunk_idx += 1

            start = end - chunk_overlap if end - chunk_overlap > start else end

        i += 1

    # If no sections found, do simple fixed-size chunking
    if not chunks:
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunk_text_val = text[start:end].strip()
            if len(chunk_text_val) > 50:
                chunks.append(TextChunk(
                    paper_arxiv_id=paper_arxiv_id,
                    chunk_index=chunk_idx,
                    text=chunk_text_val,
                    char_start=start,
                    char_end=end,
                ))
                chunk_idx += 1
            start = end - chunk_overlap

    logger.debug(f"Chunked into {len(chunks)} chunks for {paper_arxiv_id}")
    return chunks


# ---- Retrieval (Keyword-based, no external embedding dependency) ----

def _keyword_score(chunk: TextChunk, query_keywords: set[str]) -> float:
    """Simple keyword overlap score between a chunk and query keywords."""
    chunk_lower = chunk.text.lower()
    if not query_keywords:
        return 0.0
    matches = sum(1 for kw in query_keywords if kw in chunk_lower)
    return matches / len(query_keywords)


def retrieve_relevant_chunks(
    chunks: list[TextChunk],
    query: str,
    top_k: int = 5,
    min_score: float = 0.05,
) -> list[TextChunk]:
    """
    Retrieve the most relevant chunks for a query using keyword overlap.

    Args:
        chunks: All text chunks from the paper
        query: Search query (e.g., topic or section name)
        top_k: Number of chunks to return
        min_score: Minimum relevance score

    Returns:
        Top-k relevant TextChunk objects, sorted by relevance
    """
    query_keywords = set(re.findall(r"[a-zA-Z0-9]+", query.lower()))
    query_keywords = {w for w in query_keywords if len(w) > 2}

    scored = [(chunk, _keyword_score(chunk, query_keywords)) for chunk in chunks]
    scored = [(c, s) for c, s in scored if s >= min_score]
    scored.sort(key=lambda x: x[1], reverse=True)

    top_chunks = [c for c, _ in scored[:top_k]]

    # Sort by chunk_index to maintain reading order
    top_chunks.sort(key=lambda c: c.chunk_index)
    return top_chunks


# ---- RAG Context Builder ----

def build_rag_context(
    paper: Paper,
    query: str,
    pdf_cache_dir: Optional[str] = None,
    max_chunks: int = 5,
) -> tuple[str, list[dict]]:
    """
    Full RAG pipeline for a single paper:
    1. Download PDF
    2. Extract text + images
    3. Chunk text
    4. Retrieve relevant chunks
    5. Build augmented context

    Args:
        paper: Paper object
        query: Topic/query for retrieval
        pdf_cache_dir: Cache directory for PDFs
        max_chunks: Max chunks to include in context

    Returns:
        (rag_context_text, images_info_list)
    """
    pdf_path = download_pdf(paper, cache_dir=pdf_cache_dir)
    if pdf_path is None:
        return "", []

    full_text, images_info = extract_text_from_pdf(pdf_path)
    if not full_text:
        logger.warning(f"No text extracted from {paper.arxiv_id}")
        return "", images_info

    chunks = chunk_text(full_text, paper.arxiv_id)
    if not chunks:
        return "", images_info

    relevant = retrieve_relevant_chunks(chunks, query, top_k=max_chunks)

    # Build context with section awareness
    context_parts = []
    current_section = None
    for chunk in relevant:
        if chunk.section_title and chunk.section_title != current_section:
            context_parts.append(f"\n### {chunk.section_title}")
            current_section = chunk.section_title
        context_parts.append(chunk.text)

    context_text = "\n\n".join(context_parts)
    logger.info(
        f"RAG context for {paper.arxiv_id}: {len(relevant)} chunks, "
        f"{len(context_text)} chars, {len(images_info)} images extracted"
    )

    return context_text, images_info


def batch_rag_enrich(
    papers: list[Paper],
    topic: str,
    pdf_cache_dir: Optional[str] = None,
    max_chunks_per_paper: int = 5,
) -> dict[str, dict]:
    """
    Run RAG enrichment for all papers in batch.

    Args:
        papers: List of papers to enrich
        topic: Research topic for retrieval
        pdf_cache_dir: Cache directory for PDFs
        max_chunks_per_paper: Max chunks per paper

    Returns:
        Dict mapping arxiv_id -> {"context": str, "images": list[dict]}
    """
    results = {}
    for i, paper in enumerate(papers):
        logger.info(f"RAG enriching [{i+1}/{len(papers)}]: {paper.short_title[:50]}")
        context, images = build_rag_context(
            paper, topic, pdf_cache_dir=pdf_cache_dir, max_chunks=max_chunks_per_paper
        )
        results[paper.arxiv_id] = {"context": context, "images": images}
    return results
