"""Query planning for literature review requests.

Turns a user's natural-language request into a structured review topic,
search queries, and focus keywords. Uses the configured LLM when available
and falls back to deterministic rules so the pipeline remains usable.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from openai import OpenAI

logger = logging.getLogger(__name__)


@dataclass
class QueryPlan:
    """Structured search plan derived from a user request."""

    raw_request: str
    topic: str
    chinese_topic: str = ""
    search_queries: list[str] = field(default_factory=list)
    focus_keywords: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source: str = "rules"

    def normalized_queries(self, max_queries: int = 6) -> list[str]:
        """Return de-duplicated non-empty queries, always including topic."""
        candidates = [self.topic, *self.search_queries, *self.focus_keywords]
        seen = set()
        queries = []
        for q in candidates:
            cleaned = " ".join(str(q or "").split()).strip()
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            queries.append(cleaned)
            if len(queries) >= max_queries:
                break
        return queries or [self.raw_request]


def _extract_json_object(text: str) -> Optional[dict]:
    """Extract a JSON object from model output."""
    start = text.find("{")
    end = text.rfind("}") + 1
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError:
        return None


def _split_focus_keywords(text: str) -> list[str]:
    """Extract likely focus keywords from Chinese/English request text."""
    focus = []
    patterns = [
        r"(?:重点关注|重点分析|关注|尤其关注|包括)\s*([^。；;]+)",
        r"(?:focus on|including|especially)\s+([^.;]+)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.I):
            chunk = match.group(1)
            parts = re.split(r"[,，、/和与及]| and ", chunk)
            for part in parts:
                item = part.strip(" .。；;，,")
                if 2 <= len(item) <= 60:
                    focus.append(item)
    return _dedupe(focus)[:8]


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        cleaned = " ".join(str(item or "").split()).strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


def _rule_extract_topic(raw_request: str) -> str:
    normalized = " ".join(raw_request.split())
    patterns = [
        r"(?:关于|围绕|针对|研究)\s*[\"“]?(.{2,100}?)[\"”]?\s*(?:的)?(?:文献综述|综述|论文综述|研究综述)",
        r"(?:写|生成|做|制作|完成)\s*(?:一篇|一个)?\s*(?:关于|围绕|针对)\s*[\"“]?(.{2,100}?)[\"”]?\s*(?:的)?(?:文献综述|综述|论文综述|研究综述)?",
        r"(?:主题|方向|topic)\s*(?:是|为|:|：)\s*[\"“]?(.{2,100}?)[\"”]?(?:。|，|,|；|;|$)",
    ]
    topic = ""
    for pattern in patterns:
        match = re.search(pattern, normalized, re.I)
        if match:
            topic = match.group(1).strip()
            break
    if not topic:
        topic = re.sub(
            r"^(请|帮我|我想|我需要|麻烦你|能否|可以)?\s*(写|生成|做|制作|完成)?\s*(一篇|一个)?\s*",
            "",
            normalized,
        )
        topic = re.sub(r"(请帮我|帮我)?(查找|检索|搜索|生成|整理|输出).{0,50}$", "", topic)
    topic = re.sub(r"^(关于|围绕|针对|研究)\s*", "", topic)
    topic = re.sub(r"\s*(的)?(文献综述|综述|论文综述|研究综述)$", "", topic)
    topic = topic.strip(" 。；;，,")
    if topic.endswith("中") and re.search(r"中的?(文献综述|综述|论文综述|研究综述)", normalized):
        topic = f"{topic}的应用"
    return topic or raw_request.strip()


def _keyword_query_expansion(topic: str, focus_keywords: list[str]) -> list[str]:
    """Generate deterministic English-ish search queries from topic/focus."""
    queries = [topic]

    cjk_map = {
        "大模型": "large language models",
        "语言模型": "language models",
        "推理": "inference",
        "优化": "optimization",
        "注意力": "attention",
        "机制": "mechanism",
        "图神经网络": "graph neural networks",
        "药物发现": "drug discovery",
        "扩散模型": "diffusion models",
        "图像生成": "image generation",
        "联邦学习": "federated learning",
        "隐私": "privacy",
        "推荐系统": "recommender systems",
    }
    translated_parts = [eng for zh, eng in cjk_map.items() if zh in topic]
    if translated_parts:
        queries.append(" ".join(translated_parts))
        queries.append(" ".join([*translated_parts, *focus_keywords[:3]]))

    if focus_keywords:
        queries.append(" ".join([topic, *focus_keywords[:3]]))
        for kw in focus_keywords[:4]:
            queries.append(f"{topic} {kw}")

    words = re.findall(r"[A-Za-z][A-Za-z0-9\-]+", topic)
    if len(words) >= 2:
        queries.append(" ".join(words))
        if focus_keywords:
            queries.append(" ".join([*words, *focus_keywords[:2]]))

    return _dedupe(queries)[:6]


def _fallback_plan(raw_request: str, warning: str | None = None) -> QueryPlan:
    topic = _rule_extract_topic(raw_request)
    focus_keywords = _split_focus_keywords(raw_request)
    warnings = []
    if warning:
        warnings.append(warning)
    return QueryPlan(
        raw_request=raw_request,
        topic=topic,
        chinese_topic=topic,
        search_queries=_keyword_query_expansion(topic, focus_keywords),
        focus_keywords=focus_keywords,
        warnings=warnings,
        source="rules",
    )


def plan_review_query(
    raw_request: str,
    api_key: str = "",
    model: str = "deepseek-chat",
    base_url: str = "https://api.deepseek.com",
) -> QueryPlan:
    """Build a query plan. Prefer LLM JSON, fall back to rules."""
    raw_request = (raw_request or "").strip()
    if not raw_request:
        return QueryPlan(raw_request="", topic="", warnings=["需求为空"])

    if not api_key:
        return _fallback_plan(raw_request, "未配置大模型 API，已使用规则解析需求。")

    prompt = f"""你是科研文献检索规划器。请从用户需求中提取文献综述任务，并返回严格 JSON。

要求：
1. topic 使用英文检索表达，适合 arXiv / Semantic Scholar 搜索。
2. chinese_topic 使用中文综述标题表达。
3. search_queries 给 3-6 个英文检索 query，覆盖主主题和重点方向。
4. focus_keywords 提取用户强调的技术点、数据集、方法名。
5. 不要输出 JSON 以外的文字。

JSON schema:
{{
  "topic": "...",
  "chinese_topic": "...",
  "search_queries": ["...", "..."],
  "focus_keywords": ["...", "..."],
  "exclude_keywords": []
}}

用户需求：
{raw_request}"""

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}],
        )
        parsed = _extract_json_object(response.choices[0].message.content or "")
        if not parsed:
            return _fallback_plan(raw_request, "大模型需求解析未返回有效 JSON，已使用规则解析。")

        topic = str(parsed.get("topic") or "").strip() or _rule_extract_topic(raw_request)
        focus = _dedupe([str(x) for x in parsed.get("focus_keywords", []) if x])
        queries = _dedupe([str(x) for x in parsed.get("search_queries", []) if x])
        queries = _dedupe([topic, *queries, *_keyword_query_expansion(topic, focus)])
        return QueryPlan(
            raw_request=raw_request,
            topic=topic,
            chinese_topic=str(parsed.get("chinese_topic") or topic).strip(),
            search_queries=queries[:6],
            focus_keywords=focus[:8],
            exclude_keywords=_dedupe([str(x) for x in parsed.get("exclude_keywords", []) if x])[:8],
            source="llm",
        )
    except Exception as exc:
        logger.warning("LLM query planning failed: %s", exc)
        return _fallback_plan(raw_request, f"大模型需求解析失败，已使用规则解析：{exc}")
