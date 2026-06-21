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

随着大语言模型取得突破性进展，其推理效率面临严峻挑战。KV Cache 技术应运而生，用以缓存历史键值、避免重复计算，但显存占用随序列长度线性增长，成为长上下文推理的关键瓶颈，亟需系统性优化。注意力机制本身的二次复杂度，进一步放大了长序列场景下的计算与访存开销。

如何在不牺牲生成质量的前提下压缩缓存规模、提升解码吞吐，并兼顾不同硬件平台的部署约束，成为该领域必须回答的核心问题。

## 六、横向对比分析

量化类方法对硬件友好、压缩比高；驱逐类在长上下文场景更有优势；系统类则需要软硬件协同设计。三类方法在性能效率、可复现性与适用场景上各有取舍，难以用单一方案通吃所有负载。

整体来看，缓存压缩与系统级优化是当前工程落地最广的两条路线，而量化与驱逐的结合正成为新的研究热点。

## 七、算法演进脉络

从 Transformer 的自注意力奠基，到 FlashAttention 的 IO-aware 重写，再到 KV Cache 时代的驱逐、压缩与量化分支，方法沿着"更省显存、更高吞吐"的主轴持续演进。近两年呈现多分支融合与在线自适应的趋势。

## 九、结论

本综述梳理了 KV Cache 与 Flash Attention 的关键技术。未来的突破将更依赖多种优化技术的深度融合、对任务动态特性的在线感知。
"""
