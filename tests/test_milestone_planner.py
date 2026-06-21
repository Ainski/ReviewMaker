import json

from src.milestone_planner import plan_milestones


def _fake_llm(_prompt):
    body = json.dumps({
        "milestones": [{"paper_index": 1, "name": "Ada-KV", "branch": "A", "contrib": "自适应 KV 淘汰"}],
        "branches": [{"id": "A", "name_zh": "KV Cache 压缩与淘汰", "name_en": "COMPRESSION / EVICTION"}],
        "eras": [{"name_zh": "奠基", "name_en": "FOUNDATIONS", "y0": 2017, "y1": 2023}],
        "foundational": [{"name": "Attention Is All You Need", "year": 2017}],
    })
    # wrap in noise + code fence to exercise the {...} extraction
    return "前缀 ```json\n" + body + "\n``` 后缀"


def _paper():
    return type("P", (), {
        "title": "Ada-KV: Optimizing KV Cache Eviction", "first_author": "Feng",
        "year": 2024, "method_category": "系统优化类", "key_innovation": "自适应预算",
        "citation_count": 40, "abstract": "...", "has_code": True,
    })()


def test_plan_parses_json():
    plan = plan_milestones([_paper()], "KV Cache", _fake_llm)
    assert plan["branches"][0]["id"] == "A"
    assert plan["foundational"][0]["year"] == 2017
    assert plan["milestones"][0]["paper_index"] == 1


def test_plan_handles_bad_output():
    plan = plan_milestones([_paper()], "KV Cache", lambda p: "not json at all")
    assert plan == {"milestones": [], "branches": [], "eras": [], "foundational": []}
