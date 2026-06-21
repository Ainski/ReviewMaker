"""Shared fixtures for poster tests."""
from src.figure1_models import Milestone, Branch, Era, MilestoneGraph, FOUND


def _m(name, year, branch, contrib, code=True):
    return Milestone(name=name, authors=f"{name} et al", year=year, branch=branch,
                     contrib=contrib, paper_index=None, full_title=f"{name}: a paper",
                     venue="arXiv", cited_by=10, has_code=code, abstract="abs")


def sample_graph():
    branches = [
        Branch(id="A", name_zh="KV Cache 压缩与淘汰", name_en="COMPRESSION / EVICTION"),
        Branch(id="B", name_zh="系统 / IO-aware 引擎", name_en="SYSTEM / IO-AWARE"),
        Branch(id="C", name_zh="量化 / 紧凑存储", name_en="QUANTIZATION / STORAGE"),
    ]
    eras = [Era(name_zh="基础奠基时代", name_en="FOUNDATIONS", y0=2017, y1=2023),
            Era(name_zh="KV Cache 优化爆发", name_en="KV-CACHE BOOM", y0=2024, y1=2026)]
    milestones = [
        _m("Transformer", 2017, FOUND, "提出自注意力"),
        _m("FlashAttention", 2022, FOUND, "IO-aware 精确注意力"),
        _m("Ada-KV", 2024, "A", "自适应预算淘汰", code=True),
        _m("ReST-KV", 2026, "A", "鲁棒淘汰", code=False),
        _m("FlashInfer", 2025, "B", "高效注意力引擎", code=True),
        _m("VecInfer", 2025, "C", "低比特量化", code=True),
    ]
    return MilestoneGraph(topic="大模型推理中 Transformer 注意力机制优化",
                          milestones=milestones, branches=branches, eras=eras,
                          enough=True, metrics={"num_milestones": 6, "num_branches": 3})


SAMPLE_REVIEW = """# 文献综述

## 一、研究背景与问题定义

随着大语言模型取得突破性进展，其推理效率面临挑战。KV Cache 技术应运而生，但显存占用随序列长度线性增长，成为关键瓶颈，需要系统性优化。

## 六、横向对比分析

量化类方法对硬件友好；驱逐类在长上下文更有优势；系统类需要软硬件协同。

## 九、结论

本综述梳理了 KV Cache 与 Flash Attention 的关键技术。未来的突破将更依赖多种优化技术的深度融合、对任务动态特性的在线感知。
"""
