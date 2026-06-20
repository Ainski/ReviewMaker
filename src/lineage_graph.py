"""Lineage graph builder — citation-grounded algorithm evolution DAG."""

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

import networkx as nx

from src.models import Paper
from src.openalex_client import OpenAlexWork

logger = logging.getLogger(__name__)


@dataclass
class LineageNode:
    key: str
    label: str
    title: str
    year: int
    family: str
    cited_by: int
    is_ancestor: bool
    paper_index: Optional[int] = None


@dataclass
class LineageEdge:
    src: str          # older (cited) node key
    dst: str          # newer (citing) node key
    relation: str = "承接"
    label: str = "引用/承接"


@dataclass
class LineageGraph:
    nodes: list = field(default_factory=list)
    edges: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def _first_word(title: str) -> str:
    parts = (title or "").split()
    return parts[0] if parts else "?"


def select_nodes(papers: list, ancestor_works: list) -> list:
    nodes: list = []
    paper_keys = set()
    for i, p in enumerate(papers, start=1):
        key = p.openalex_id or p.arxiv_id or f"_p{i}"
        if key in paper_keys:
            continue  # dedup: two papers resolved to the same OpenAlex work
        paper_keys.add(key)
        nodes.append(LineageNode(
            key=key,
            label=f"{p.first_author} {p.year or p.oa_year}",
            title=p.title,
            year=p.year or p.oa_year,
            family=p.method_category or "未分类",
            cited_by=p.oa_cited_by_count or p.citation_count,
            is_ancestor=False,
            paper_index=i,
        ))
    for w in ancestor_works:
        if not w.openalex_id or w.openalex_id in paper_keys:
            continue
        nodes.append(LineageNode(
            key=w.openalex_id,
            label=f"{_first_word(w.title)} {w.year}",
            title=w.title,
            year=w.year,
            family="奠基",
            cited_by=w.cited_by_count,
            is_ancestor=True,
        ))
    return nodes


def pick_ancestors(papers: list, client, min_share: int, max_ancestors: int) -> list:
    paper_oa_ids = {p.openalex_id for p in papers if p.openalex_id}
    counter: Counter = Counter()
    for p in papers:
        for ref in p.referenced_works:
            if ref and ref not in paper_oa_ids:
                counter[ref] += 1
    candidate_ids = [rid for rid, c in counter.items() if c >= min_share]
    if not candidate_ids:
        return []
    works = client.fetch_works_by_ids(candidate_ids)
    scored = []
    for rid in candidate_ids:
        w = works.get(rid)
        if w:
            scored.append((counter[rid], w.cited_by_count, w))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [w for _, _, w in scored[:max_ancestors]]


def _cap_nodes(nodes: list, max_nodes: int) -> list:
    papers = [n for n in nodes if not n.is_ancestor]
    ancestors = sorted((n for n in nodes if n.is_ancestor),
                       key=lambda n: n.cited_by, reverse=True)
    room = max(0, max_nodes - len(papers))
    return papers + ancestors[:room]


def build_edges(nodes: list, refs_by_key: dict) -> tuple:
    """Build A->B edges from real citations (B cites A), keeping only old->new."""
    node_by_key = {n.key: n for n in nodes}
    edges: list = []
    seen: set = set()
    dropped = 0
    for b in nodes:
        for ref in refs_by_key.get(b.key, []):
            if ref == b.key or ref not in node_by_key:
                continue
            a = node_by_key[ref]
            if not a.year or not b.year:
                continue  # unknown year (OpenAlex publication_year null): cannot place reliably
            if a.year <= b.year:
                pair = (a.key, b.key)
                if pair not in seen:
                    seen.add(pair)
                    edges.append(LineageEdge(src=a.key, dst=b.key))
            else:
                dropped += 1
    return edges, dropped


def to_dag_and_reduce(nodes: list, edges: list) -> tuple:
    """Build a DiGraph, break any cycles, transitively reduce; return (graph, reduced_edges)."""
    g = nx.DiGraph()
    for n in nodes:
        g.add_node(n.key)
    for e in edges:
        g.add_edge(e.src, e.dst)
    # Break any cycles (rare: equal-year mutual citation / preprint-version quirks)
    while not nx.is_directed_acyclic_graph(g):
        cycle = nx.find_cycle(g)
        g.remove_edge(cycle[-1][0], cycle[-1][1])
    reduced_graph = nx.transitive_reduction(g)
    kept = set(reduced_graph.edges())
    reduced_edges = [e for e in edges if (e.src, e.dst) in kept]
    return reduced_graph, reduced_edges


def compute_metrics(topic: str, nodes: list, reduced_edges: list,
                    dropped: int, resolve_rate: str, reduced_graph) -> dict:
    label_by_key = {n.key: n.label for n in nodes}
    try:
        chain = nx.dag_longest_path(reduced_graph) if reduced_graph.number_of_nodes() else []
    except Exception:
        chain = []
    return {
        "topic": topic,
        "num_paper_nodes": sum(1 for n in nodes if not n.is_ancestor),
        "num_ancestor_nodes": sum(1 for n in nodes if n.is_ancestor),
        "num_real_edges": len(reduced_edges),
        "dropped_time_violations": dropped,
        "is_dag": nx.is_directed_acyclic_graph(reduced_graph),
        "longest_chain_len": len(chain),
        "longest_chain": [label_by_key.get(k, k) for k in chain],
        "openalex_resolve_rate": resolve_rate,
    }


def _innovation_by_key(nodes: list, papers: list) -> dict:
    inno: dict = {}
    for p in papers:
        key = p.openalex_id or p.arxiv_id
        if p.key_innovation:
            inno[key] = p.key_innovation
    for n in nodes:
        inno.setdefault(n.key, n.title)
    return inno


def label_edges(edges: list, nodes: list, papers: list, llm_call) -> list:
    """Label each real edge with a relationship. llm_call(prompt)->raw JSON text."""
    if not edges:
        return edges
    node_by_key = {n.key: n for n in nodes}
    inno = _innovation_by_key(nodes, papers)
    lines = []
    for i, e in enumerate(edges, start=1):
        a, b = node_by_key[e.src], node_by_key[e.dst]
        lines.append(
            f'{i}. 早="{a.title}" ({a.year}; {inno.get(a.key, "")[:40]}) '
            f'| 晚="{b.title}" ({b.year}; {inno.get(b.key, "")[:40]}) | 事实: 晚引用了早'
        )
    prompt = (
        "下面每行是一条真实引用关系（晚的论文引用了早的论文）。请判断晚的论文在早的论文基础上"
        "的发展类型，只能描述给定事实，不得编造。relation 从 [改进,扩展,受启发,应用,对比,承接] 选一个，"
        "label 为 12 字以内中文短语。仅返回 JSON 数组：\n"
        '[{"index":1,"relation":"改进","label":"改进注意力机制"}]\n\n'
        + "\n".join(lines)
    )
    try:
        raw = llm_call(prompt)
        start, end = raw.find("["), raw.rfind("]") + 1
        items = json.loads(raw[start:end]) if 0 <= start < end else []
        for item in items:
            idx = int(item.get("index", 0)) - 1
            if 0 <= idx < len(edges):
                rel = item.get("relation")
                lbl = item.get("label")
                if rel:
                    edges[idx].relation = rel
                if lbl:
                    edges[idx].label = lbl
    except Exception as e:
        logger.warning(f"LLM edge labeling failed, using defaults: {e}")
    return edges


def _default_llm_call(api_key, model, base_url):
    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url=base_url)

    def call(prompt: str) -> str:
        resp = client.chat.completions.create(
            model=model, max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content or ""
    return call


def build_lineage(papers: list, topic: str, *, client=None, llm_call=None,
                  api_key: Optional[str] = None, model: str = "deepseek-chat",
                  base_url: str = "https://api.deepseek.com") -> LineageGraph:
    from src.openalex_client import OpenAlexClient
    from config import config

    client = client or OpenAlexClient()
    client.enrich_papers(papers)
    resolved = sum(1 for p in papers if p.openalex_id)
    resolve_rate = f"{resolved}/{len(papers)}"

    ancestors = pick_ancestors(papers, client,
                               config.lineage_min_ancestor_share,
                               config.lineage_max_ancestors)
    nodes = _cap_nodes(select_nodes(papers, ancestors), config.lineage_max_nodes)
    node_keys = {n.key for n in nodes}

    refs_by_key: dict = {}

    def _add_refs(key, refs):
        if key not in node_keys:
            return
        bucket = refs_by_key.setdefault(key, [])
        for r in refs:
            if r not in bucket:
                bucket.append(r)

    for i, p in enumerate(papers, start=1):
        _add_refs(p.openalex_id or p.arxiv_id or f"_p{i}", p.referenced_works)
    for w in ancestors:
        _add_refs(w.openalex_id, w.referenced_works)

    edges, dropped = build_edges(nodes, refs_by_key)
    reduced_graph, reduced_edges = to_dag_and_reduce(nodes, edges)

    if llm_call is None and api_key:
        llm_call = _default_llm_call(api_key, model, base_url)
    if llm_call is not None:
        reduced_edges = label_edges(reduced_edges, nodes, papers, llm_call)

    metrics = compute_metrics(topic, nodes, reduced_edges, dropped, resolve_rate, reduced_graph)
    return LineageGraph(nodes=nodes, edges=reduced_edges, metrics=metrics)
