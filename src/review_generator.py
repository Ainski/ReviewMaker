"""Review generator module — uses DeepSeek API to generate structured literature reviews in Chinese."""

import logging
import json
from typing import Optional

from openai import OpenAI

from src.models import Paper

logger = logging.getLogger(__name__)


def _build_paper_context(paper: Paper, index: int) -> str:
    """Build a structured text block for a single paper."""
    authors_str = ", ".join(a.name for a in paper.authors[:5])
    if len(paper.authors) > 5:
        authors_str += " 等"

    code_info = ""
    if paper.has_code and paper.code_urls:
        code_info = f"\n  代码: {', '.join(paper.code_urls[:3])}"

    return (
        f"论文 [{index}]:\n"
        f"  标题: {paper.title}\n"
        f"  作者: {authors_str}\n"
        f"  年份: {paper.year}\n"
        f"  ArXiv ID: {paper.arxiv_id}\n"
        f"  引用数: {paper.citation_count}\n"
        f"  摘要: {paper.abstract[:500]}{'...' if len(paper.abstract) > 500 else ''}\n"
        f"{code_info}"
    )


def _build_system_prompt() -> str:
    """Build the system prompt that defines the review generation task."""
    return """你是一个文献综述生成器。你的输出将直接作为学术论文发表。
严格遵循以下规则：

【核心规则】
1. 直接输出综述正文，不要有任何开场白、寒暄、解释性文字。
2. 禁止以下所有表述模式：
   - "好的，我将..." / "作为一名研究者，我将..." / "好的，以下..."
   - "根据您提供的..." / "基于以上论文..."
   - 任何总结性、回顾性、过渡性的非正文文字
3. 你的第一个输出字符必须是 "## 一、引言"
4. 仅使用提供的论文信息，不编造任何细节。
5. 文中引用使用 [1]、[2] 等格式。

【输出格式】
## 一、引言
[直接开始正文，2-3段概述领域背景、核心挑战、本文关注的焦点]

## 二、方法分类
[将论文按方法归类，每类用一个自然段描述]

## 三、论文详细分析
[逐篇分析：核心创新、数据集、关键结果]

## 四、对比分析
[横向比较各方法的优劣和适用场景]

## 五、未来展望
[指出研究空白和发展方向]"""


def _build_user_prompt(
    papers: list[Paper],
    topic: str,
    include_tables: bool = True,
) -> str:
    """Build the user prompt with all paper data."""
    paper_blocks = []
    for i, paper in enumerate(papers, start=1):
        paper_blocks.append(_build_paper_context(paper, i))

    papers_text = "\n\n".join(paper_blocks)

    table_instruction = ""
    if include_tables:
        table_instruction = """
在第三章中包含一个总结表格，列如下：
| 序号 | 论文 | 年份 | 主要创新 | 数据集 | 关键结果 | 代码 |
|------|------|------|----------|--------|----------|------|
"""

    return f"""主题：{topic}
论文数量：{len(papers)} 篇

{papers_text}

{table_instruction}

【严格执行】
- 直接从 "## 一、引言" 开始输出，在此之前不要输出任何文字。
- 在正文中对应位置标注引用编号 [1]-[{len(papers)}]。
- 不要输出参考文献列表。"""


def generate_review(
    papers: list[Paper],
    topic: str,
    api_key: str,
    model: str = "deepseek-chat",
    base_url: str = "https://api.deepseek.com",
) -> str:
    """
    Generate a structured literature review in Chinese using DeepSeek API.

    Args:
        papers: Ranked list of papers to review
        topic: Research topic
        api_key: DeepSeek API key
        model: DeepSeek model to use
        base_url: DeepSeek API base URL

    Returns:
        Markdown review text in Chinese with inline citations [1], [2], etc.
    """
    if not papers:
        return "没有论文可供综述。"

    logger.info(f"正在为 {len(papers)} 篇论文生成综述，主题: '{topic}'")

    client = OpenAI(api_key=api_key, base_url=base_url)

    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(papers, topic)

    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=8192,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        review_text = response.choices[0].message.content or ""
        logger.info(f"综述生成完成: {len(review_text)} 字符")
        return review_text

    except Exception as e:
        logger.error(f"DeepSeek API 错误: {e}")
        raise


def extract_paper_details(
    papers: list[Paper],
    api_key: str,
    model: str = "deepseek-chat",
    base_url: str = "https://api.deepseek.com",
) -> list[Paper]:
    """
    Use DeepSeek to extract structured details from each paper's abstract:
    - key_innovation
    - datasets_used
    - key_results
    - method_category

    Args:
        papers: Papers to analyze
        api_key: DeepSeek API key
        model: DeepSeek model to use
        base_url: DeepSeek API base URL

    Returns:
        Updated list of Paper objects
    """
    logger.info(f"正在提取 {len(papers)} 篇论文的结构化信息...")

    client = OpenAI(api_key=api_key, base_url=base_url)

    paper_list = []
    for i, p in enumerate(papers, start=1):
        paper_list.append(
            f"[{i}] 标题: {p.title}\n"
            f"    年份: {p.year}\n"
            f"    摘要: {p.abstract[:400]}"
        )

    papers_text = "\n\n".join(paper_list)

    prompt = f"""请为以下每篇论文提取以下信息：
- key_innovation: 主要算法或方法创新点（一句话，中文）
- datasets_used: 摘要中提到的数据集名称列表
- key_results: 关键定量结果或发现（一句话，中文）
- method_category: 方法类别标签，如 "Transformer类"、"图神经网络类"、"强化学习类"、"扩散模型类"、"注意力机制类" 等

仅返回 JSON 数组，不要包含其他内容：
[
  {{
    "index": 1,
    "key_innovation": "...",
    "datasets_used": ["数据集1", "数据集2"],
    "key_results": "...",
    "method_category": "..."
  }},
  ...
]

论文列表：
{papers_text}"""

    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = response.choices[0].message.content or ""

        start = response_text.find("[")
        end = response_text.rfind("]") + 1
        if start >= 0 and end > start:
            json_str = response_text[start:end]
            details_list = json.loads(json_str)

            for detail in details_list:
                idx = detail.get("index", 0) - 1
                if 0 <= idx < len(papers):
                    papers[idx].key_innovation = detail.get("key_innovation")
                    papers[idx].datasets_used = detail.get("datasets_used", [])
                    papers[idx].key_results = detail.get("key_results")
                    papers[idx].method_category = detail.get("method_category")

            logger.info(f"成功提取 {len(details_list)} 篇论文的详情")
        else:
            logger.warning("无法从 DeepSeek 响应中解析 JSON")

    except Exception as e:
        logger.error(f"提取论文详情时出错: {e}")

    return papers


def generate_lineage_narrative(graph, llm_call) -> str:
    """Write a grounded '算法演进脉络' body from REAL edges. Returns '' if no edges.

    llm_call(prompt)->str. Caller injects the LLM (DeepSeek) call.
    """
    if not getattr(graph, "edges", None):
        return ""
    node_by_key = {n.key: n for n in graph.nodes}
    edge_lines = []
    for e in graph.edges:
        a, b = node_by_key.get(e.src), node_by_key.get(e.dst)
        if not a or not b:
            continue
        ai = f"[{a.paper_index}]" if a.paper_index else ""
        bi = f"[{b.paper_index}]" if b.paper_index else ""
        edge_lines.append(f"{a.label}{ai} --{e.relation}({e.label})--> {b.label}{bi}")
    prompt = (
        "以下是基于真实引用关系得到的算法演进边（早→晚）。请写 1-2 段中文，"
        "概述该领域的主要演进脉络。**只能描述下列边中存在的关系，不得新增未列出的演进关系**。"
        "如论文有编号 [n] 请沿用。直接输出正文，不要标题、不要寒暄：\n\n"
        + "\n".join(edge_lines)
    )
    try:
        text = (llm_call(prompt) or "").strip()
        return text
    except Exception as e:
        logger.warning(f"脉络生成失败: {e}")
        return ""


def insert_lineage_section(review_text: str, narrative_body: str) -> str:
    """Insert '## 五、算法演进脉络' before '五、未来展望' (renumbered to 六).

    Falls back to appending the section if the marker is absent.
    No-op when narrative_body is empty.
    """
    if not narrative_body:
        return review_text
    section = f"## 五、算法演进脉络\n{narrative_body}\n\n"
    marker = "## 五、未来展望"
    if marker in review_text:
        return review_text.replace(marker, section + "## 六、未来展望", 1)
    # Fallback: append before references if present, else at end.
    ref_marker = "## 参考文献"
    if ref_marker in review_text:
        return review_text.replace(ref_marker, section + ref_marker, 1)
    return review_text.rstrip() + "\n\n" + section
