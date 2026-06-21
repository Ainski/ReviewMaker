"""Review generator module — uses DeepSeek API to generate structured literature reviews in Chinese."""

import logging
import json
import re
from typing import Optional

from openai import OpenAI

from src.models import Paper

logger = logging.getLogger(__name__)


COMMON_BENCHMARKS = [
    "MMLU", "GSM8K", "HumanEval", "MBPP", "MATH", "BBH", "HellaSwag",
    "ARC", "WinoGrande", "TruthfulQA", "LongBench", "NeedleBench", "L-Eval",
    "MT-Bench", "Chatbot Arena", "HELM", "AlpacaEval", "ShareGPT", "LMSYS",
    "WikiText", "C4", "The Pile", "RedPajama", "SlimPajama", "BookCorpus",
    "ImageNet", "CIFAR-10", "CIFAR-100", "COCO", "MS COCO", "ADE20K",
    "Cityscapes", "KITTI", "SQuAD", "GLUE", "SuperGLUE", "XNLI", "CoNLL",
    "SST-2", "MNIST", "Fashion-MNIST", "LibriSpeech", "Common Voice",
    "SPEC", "MLPerf", "TPC-H", "TPC-DS", "CloudSuite", "TailBench",
    "A100", "H100", "V100", "L40S", "ShareGPT traces", "production traces",
]


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        item = str(item or "").strip()
        if not item:
            continue
        key = item.lower()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


# Common words the context regex grabs after a trigger ("benchmarks demonstrate
# that ...", "experiments on the ...") that are NOT dataset names.
_RULE_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "on", "in", "to", "for", "with", "we",
    "demonstrate", "demonstrates", "demonstrating", "show", "shows", "shown",
    "achieve", "achieves", "achieved", "improve", "improves", "improved",
    "outperform", "outperforms", "reduce", "reduces", "results", "result",
    "experiments", "experiment", "evaluation", "evaluations", "benchmark",
    "benchmarks", "dataset", "datasets", "task", "tasks", "method", "methods",
    "model", "models", "approach", "baseline", "baselines", "multiple",
    "several", "various", "many", "standard", "common", "diverse", "extensive",
    "comprehensive", "large", "small", "new", "novel", "real", "all", "both",
    "these", "those", "such", "including", "that", "this", "our", "their",
    "effectiveness", "performance", "accuracy", "consistent", "significant",
}


def _looks_like_junk(token: str) -> bool:
    """A context-regex candidate is junk if it is a known common word, or an
    all-lowercase word with no digit. Real dataset/benchmark names carry an
    uppercase letter (MMLU, FooBench) or a digit (C4, CIFAR-10)."""
    low = token.lower()
    if low in _RULE_STOPWORDS:
        return True
    if token.islower() and not any(c.isdigit() for c in token):
        return True
    return False


def extract_datasets_from_evidence(text: str) -> list[str]:
    """Rule-based fallback for datasets, benchmarks, workloads and traces."""
    if not text:
        return []

    found: list[str] = []
    for name in COMMON_BENCHMARKS:
        # Word-boundary match so "SPEC" doesn't fire on "specific", "ARC" on
        # "research"/"hierarchical", "MATH" on "mathematical", etc.
        if re.search(r"\b" + re.escape(name) + r"\b", text, flags=re.IGNORECASE):
            found.append(name)

    context_patterns = [
        r"(?:dataset|datasets|benchmark|benchmarks|workload|workloads|trace|traces|evaluation on|evaluated on|experiments on)\s+(?:including|include|such as|:)?\s*([A-Z][A-Za-z0-9_\-+/]*(?:\s*,\s*[A-Z][A-Za-z0-9_\-+/]*){0,8})",
        r"(?:数据集|基准|评测集|工作负载|负载|轨迹|trace|benchmark)[：: ]+([A-Za-z0-9_\-+/]+(?:[、,，]\s*[A-Za-z0-9_\-+/]+){0,8})",
    ]
    for pattern in context_patterns:
        for match in re.findall(pattern, text, flags=re.IGNORECASE):
            parts = re.split(r"[,，、;/]|\band\b", match)
            for part in parts:
                part = part.strip(" .()[]{}")
                if len(part) >= 2 and re.search(r"[A-Za-z0-9]", part) and not _looks_like_junk(part):
                    found.append(part)

    return _dedupe_keep_order(found)[:12]


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
        f"  结构化数据集/Benchmark/Workload: {datasets}\n"
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
| 序号 | 论文 | 年份 | 方法类别 | 主要创新 | 数据集/Benchmark/Workload | 关键结果 | 代码 |
|------|------|------|----------|----------|--------|----------|------|
表格内容必须优先使用每篇论文的结构化核心创新、结构化数据集/Benchmark/Workload、结构化关键结果和代码状态字段。
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


def _build_revision_paper_context(paper: dict, index: int) -> str:
    """Build a compact paper context from frontend/job result paper dicts."""
    code_status = "未找到公开代码"
    if paper.get("has_code") and paper.get("code_urls"):
        code_status = f"已找到公开代码: {', '.join(paper.get('code_urls', [])[:1])}"
    datasets = paper.get("datasets_used") or []
    if isinstance(datasets, list):
        datasets = "、".join(datasets) if datasets else "原文摘要未明确说明"

    return (
        f"论文 [{index}]:\n"
        f"  标题: {paper.get('title', '')}\n"
        f"  年份: {paper.get('year', '')}\n"
        f"  发表期刊/会议: {paper.get('venue', '') or '未获取'}\n"
        f"  引用数: {paper.get('citations', 0)}\n"
        f"  方法类别: {paper.get('method_category', '未分类')}\n"
        f"  结构化核心创新: {paper.get('key_innovation', '') or '原文摘要未明确说明'}\n"
        f"  结构化数据集/Benchmark/Workload: {datasets}\n"
        f"  结构化关键结果: {paper.get('key_results', '') or '原文摘要未明确说明'}\n"
        f"  代码状态: {code_status}"
    )


def revise_review(
    current_review: str,
    papers: list[dict],
    user_instruction: str,
    api_key: str,
    model: str = "deepseek-chat",
    base_url: str = "https://api.deepseek.com",
) -> str:
    """
    Revise an existing review according to a user's natural-language feedback.

    Returns only the revised review body, without the reference list.
    """
    if not current_review.strip():
        return current_review
    if not user_instruction.strip():
        return current_review

    paper_context = "\n\n".join(
        _build_revision_paper_context(paper, i)
        for i, paper in enumerate(papers, start=1)
    )

    system_prompt = """你是严谨的中文科研文献综述编辑。请根据用户反馈修改已有综述正文。
规则：
1. 只输出修订后的综述正文，不要解释修改过程。
2. 不要输出参考文献列表，系统会自动追加。
3. 必须保留正文中的 [1]、[2] 等引用格式，并且引用编号只能对应提供的论文。
4. 不能编造论文没有提供的数据集、结果、代码或实验结论。
5. 如果用户要求侧重模型差异、算法演进、应用场景、实验对比等，应调整章节结构和叙述重点。
6. 段落应保持学术综述风格，避免口语化。"""

    user_prompt = f"""用户修改意见：
{user_instruction}

当前综述正文：
{current_review}

可用论文信息：
{paper_context}

请基于以上内容输出完整修订版综述正文。不要输出参考文献。"""

    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        max_tokens=8192,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content or current_review


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
        evidence_text = f"{p.title}\n{p.abstract}\n{rag_context}"
        p._dataset_candidates = extract_datasets_from_evidence(evidence_text)  # temporary runtime hint
        dataset_hint = "、".join(p._dataset_candidates) if p._dataset_candidates else "未通过规则识别到"

        paper_list.append(
            f"[{i}] 标题: {p.title}\n"
            f"    年份: {p.year}\n"
            f"    摘要: {p.abstract[:600]}"
            f"\n    规则识别到的候选数据集/Benchmark/Workload: {dataset_hint}"
            f"{evidence}"
        )

    papers_text = "\n\n".join(paper_list)

    evidence_label = "摘要和全文证据片段" if rag_data else "标题和摘要"

    prompt = f"""请基于每篇论文的{evidence_label}提取以下结构化信息。
要求非常严格：只能提取证据中明确出现的信息，不要用常识补全。
所有输出字段必须使用中文表达；论文名、方法名、数据集名、Benchmark 名、指标名、英文缩写和数值可以保留原文。

- key_innovation: 主要算法或方法创新点（一句话，中文）
- datasets_used: 证据中明确提到的数据集、Benchmark、Workload、Trace、评测任务或硬件/系统负载名称列表；例如 MMLU、LongBench、ShareGPT traces、MLPerf、SPEC、A100/H100 workloads。没有明确名称则返回 []
- key_results: 该论文声称达成的效果、收益或核心结论，用中文一句话概括。按优先级：① 若摘要有明确定量结果（数值/倍率/百分比/指标），直接用（可保留原文数字）；② 若无定量数字，则用摘要中作者声称的改进/优势/目标作为定性结果，例如方法旨在提升/降低/改善 X，就写「（声称）提升/降低/改善 X」——**即使该效果与 key_innovation 部分重叠，也必须在此独立写出，绝不能因为已写进创新就留空**；③ 综述/Survey/Review 类则概括其主要结论或综述范围（如「系统综述了X类方法并指出Y关键挑战」）。⚠️ 几乎每篇论文摘要都至少陈述了一个目标或声称的效果，因此本字段**极少**应为"证据未明确说明"；仅当摘要连一个目标、收益、结论或贡献都没有提到时，才允许写"证据未明确说明"
- method_category: 方法类别标签，如 "Transformer类"、"图神经网络类"、"强化学习类"、"扩散模型类"、"注意力机制类"、"系统优化类" 等
- evidence_source: 信息主要来自 "摘要"、"全文片段" 或 "摘要+全文片段"
- confidence: 0 到 1 的置信度，全文片段中有明确数据集/结果时置信度应更高

仅返回 JSON 数组，不要包含其他内容：
[
  {{
    "index": 1,
    "key_innovation": "...",
    "datasets_used": ["数据集1", "数据集2"],
    "key_results": "该方法在某指标上取得约 3.00 倍加速，同时降低内存开销。",
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
                    model_datasets = detail.get("datasets_used", [])
                    if not isinstance(model_datasets, list):
                        model_datasets = [str(model_datasets)] if model_datasets else []
                    rule_datasets = getattr(papers[idx], "_dataset_candidates", [])
                    papers[idx].datasets_used = _dedupe_keep_order(model_datasets + rule_datasets)
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

    for paper in papers:
        if hasattr(paper, "_dataset_candidates"):
            delattr(paper, "_dataset_candidates")

    return papers
