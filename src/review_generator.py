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

    code_info = "未找到公开代码"
    if paper.has_code and paper.code_urls:
        code_info = f"已找到公开代码: {', '.join(paper.code_urls[:3])}"

    datasets = "、".join(paper.datasets_used) if paper.datasets_used else "原文摘要未明确说明"
    key_innovation = paper.key_innovation or "原文摘要未明确说明"
    key_results = paper.key_results or "原文摘要未明确说明"
    method_category = paper.method_category or "未分类"

    return (
        f"论文 [{index}]:\n"
        f"  标题: {paper.title}\n"
        f"  作者: {authors_str}\n"
        f"  年份: {paper.year}\n"
        f"  ArXiv ID: {paper.arxiv_id}\n"
        f"  引用数: {paper.citation_count}\n"
        f"  摘要: {paper.abstract[:500]}{'...' if len(paper.abstract) > 500 else ''}\n"
        f"  方法类别: {method_category}\n"
        f"  结构化核心创新: {key_innovation}\n"
        f"  结构化数据集: {datasets}\n"
        f"  结构化关键结果: {key_results}\n"
        f"  代码状态: {code_info}"
    )


def _build_system_prompt() -> str:
    """Build the system prompt that defines the review generation task."""
    return """你是一个严谨的中文科研文献综述写作专家。你的输出将直接作为课程作业中的综述正文。
严格遵循以下规则：

【核心规则】
1. 直接输出综述正文，不要有任何开场白、寒暄、解释性文字。
2. 禁止以下所有表述模式：
   - "好的，我将..." / "作为一名研究者，我将..." / "好的，以下..."
   - "根据您提供的..." / "基于以上论文..."
   - 任何总结性、回顾性、过渡性的非正文文字
3. 你的第一个输出字符必须是 "## 一、研究背景与问题定义"
4. 仅使用提供的论文标题、摘要、年份、引用数、代码状态和已抽取字段，不编造数据集、指标、数值结果、实验结论或开源代码。
5. 如果摘要或结构化字段没有明确给出数据集、定量结果、消融实验、代码细节，必须写成"原文摘要未明确说明"，不能猜测。
6. 每个关键技术判断、论文归纳或代表性工作说明都要在句末标注 [1]、[2] 等引用。
7. 不要输出参考文献列表，参考文献由系统自动追加。
8. 代码信息必须严格依据每篇论文的"代码状态"字段：如果代码状态是"未找到公开代码"，正文和表格中都必须写"未找到公开代码"，禁止写 GitHub、Hugging Face、开源或随论文发布。

【输出格式】
## 一、研究背景与问题定义
[2-3段说明研究领域、核心问题、综述边界和用户关注重点]

## 二、技术发展脉络
[按年份和技术路线说明代表性方法如何演进，避免时间顺序错误]

## 三、方法体系分类
[按算法思想或系统目标进行分类，每一类解释核心机制、适用场景和局限]

## 四、代表性工作详解
[选择代表性论文逐篇分析：主要创新、使用数据集、关键结果、是否开源代码]

## 五、数据集与评价指标总结
[总结文献中明确出现的数据集、指标和实验设置；缺失处说明未明确]

## 六、横向对比分析
[比较各类方法在性能、效率、可复现性、代码可用性、适用场景上的差异]

## 七、算法演进与趋势
[结合年份和方法类别，归纳算法从早期方法到近期方法的演进路径]

## 八、开放问题与未来方向
[提出仍未解决的问题、可能改进方向和后续研究机会]

## 九、结论
[用1-2段总结综述发现，不新增未引用事实]"""


def _build_user_prompt(
    papers: list[Paper],
    topic: str,
    include_tables: bool = True,
    raw_request: str = "",
    focus_keywords: Optional[list[str]] = None,
) -> str:
    """Build the user prompt with all paper data."""
    paper_blocks = []
    for i, paper in enumerate(papers, start=1):
        paper_blocks.append(_build_paper_context(paper, i))

    papers_text = "\n\n".join(paper_blocks)

    focus_text = "、".join(focus_keywords or [])

    table_instruction = ""
    if include_tables:
        table_instruction = """
请在第四章或第六章中包含一个代表性工作对比表，列如下：
| 序号 | 论文 | 年份 | 方法类别 | 主要创新 | 数据集 | 关键结果 | 代码 |
|------|------|------|----------|----------|--------|----------|------|
表格内容必须优先使用每篇论文的结构化核心创新、结构化数据集、结构化关键结果和代码状态字段。
"""

    return f"""主题：{topic}
用户原始需求：{raw_request or topic}
重点关注：{focus_text or "未额外指定"}
论文数量：{len(papers)} 篇

{papers_text}

{table_instruction}

【严格执行】
- 直接从 "## 一、研究背景与问题定义" 开始输出，在此之前不要输出任何文字。
- 在正文中对应位置标注引用编号 [1]-[{len(papers)}]。
- 不确定的信息必须写明"原文摘要未明确说明"，禁止用常识补全。
- 代码列必须与"代码状态"字段完全一致；没有代码 URL 时不要写开源。
- 用户原始需求中的重点关注内容应优先体现在分类、对比和未来方向中。
- 不要输出参考文献列表。"""


def generate_review(
    papers: list[Paper],
    topic: str,
    api_key: str,
    model: str = "deepseek-chat",
    base_url: str = "https://api.deepseek.com",
    raw_request: str = "",
    focus_keywords: Optional[list[str]] = None,
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
    user_prompt = _build_user_prompt(
        papers,
        topic,
        raw_request=raw_request,
        focus_keywords=focus_keywords,
    )

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
    rag_data: Optional[dict[str, dict]] = None,
) -> list[Paper]:
    """
    Use DeepSeek to extract structured details from abstracts and optional RAG evidence:
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

    rag_data = rag_data or {}

    paper_list = []
    for i, p in enumerate(papers, start=1):
        rag_context = (rag_data.get(p.arxiv_id, {}) or {}).get("context", "")
        evidence = ""
        if rag_context:
            evidence = (
                "\n"
                f"    全文证据片段: {rag_context[:1800]}"
            )
        paper_list.append(
            f"[{i}] 标题: {p.title}\n"
            f"    年份: {p.year}\n"
            f"    摘要: {p.abstract[:600]}"
            f"{evidence}"
        )

    papers_text = "\n\n".join(paper_list)

    evidence_label = "摘要和全文证据片段" if rag_data else "标题和摘要"

    prompt = f"""请基于每篇论文的{evidence_label}提取以下结构化信息。
要求非常严格：只能提取证据中明确出现的信息，不要用常识补全。

- key_innovation: 主要算法或方法创新点（一句话，中文）
- datasets_used: 证据中明确提到的数据集、benchmark 或任务集合名称列表；没有明确名称则返回 []
- key_results: 证据中明确提到的关键定量结果、效率提升、性能指标或主要发现；没有明确结果则写 "证据未明确说明"
- method_category: 方法类别标签，如 "Transformer类"、"图神经网络类"、"强化学习类"、"扩散模型类"、"注意力机制类"、"系统优化类" 等
- evidence_source: 信息主要来自 "摘要"、"全文片段" 或 "摘要+全文片段"
- confidence: 0 到 1 的置信度，全文片段中有明确数据集/结果时置信度应更高

仅返回 JSON 数组，不要包含其他内容：
[
  {{
    "index": 1,
    "key_innovation": "...",
    "datasets_used": ["数据集1", "数据集2"],
    "key_results": "...",
    "method_category": "...",
    "evidence_source": "...",
    "confidence": 0.8
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
                    papers[idx].evidence_source = detail.get("evidence_source")
                    try:
                        papers[idx].detail_confidence = float(detail.get("confidence") or 0.0)
                    except (TypeError, ValueError):
                        papers[idx].detail_confidence = 0.0

            logger.info(f"成功提取 {len(details_list)} 篇论文的详情")
        else:
            logger.warning("无法从 DeepSeek 响应中解析 JSON")

    except Exception as e:
        logger.error(f"提取论文详情时出错: {e}")

    return papers
