"""Tests for rule-based dataset extraction — word-boundary correctness (no substring false positives)."""

from src.review_generator import extract_datasets_from_evidence


def test_no_substring_false_positives():
    # Contains 'mathematical', 'research', 'hierarchical', 'specific' — must NOT
    # be mis-read as MATH / ARC / SPEC via substring matching.
    text = ("We propose an instance-specific directional stimulus prompting method "
            "for mathematical reasoning research on hierarchical preference optimization.")
    got = extract_datasets_from_evidence(text)
    assert "MATH" not in got
    assert "ARC" not in got
    assert "SPEC" not in got
    assert got == []


def test_still_matches_real_standalone_benchmarks():
    text = "We evaluate on MATH and ARC, and also report SPEC numbers."
    got = extract_datasets_from_evidence(text)
    assert "MATH" in got
    assert "ARC" in got
    assert "SPEC" in got


def test_matches_benchmarks_with_special_chars():
    text = "Experiments use CIFAR-10 and A100 GPUs on the TPC-H workload."
    got = extract_datasets_from_evidence(text)
    assert "CIFAR-10" in got
    assert "A100" in got
    assert "TPC-H" in got


def test_context_regex_drops_verbs_and_articles():
    # "...benchmarks demonstrate that..." must not yield "demonstrate"/"the";
    # real datasets still survive via the whitelist.
    got = extract_datasets_from_evidence(
        "Experiments on the MATH and GSM8K benchmarks demonstrate that our method improves accuracy.")
    low = [x.lower() for x in got]
    assert "demonstrate" not in low
    assert "the" not in low
    assert "MATH" in got and "GSM8K" in got


def test_context_regex_drops_common_words():
    got1 = extract_datasets_from_evidence(
        "Extensive experiments on multiple datasets demonstrate the effectiveness.")
    got2 = extract_datasets_from_evidence(
        "Results on standard benchmarks show consistent gains.")
    junk = {"multiple", "demonstrate", "show", "the", "standard", "results", "effectiveness"}
    assert all(x.lower() not in junk for x in got1 + got2), (got1, got2)


def test_context_regex_keeps_capitalized_novel_name():
    got = extract_datasets_from_evidence("We evaluated on FooBench and report numbers.")
    assert "FooBench" in got


def test_lowercase_workload_whitelist_entry_not_dropped():
    # 'production traces' is an all-lowercase whitelist entry — must survive.
    got = extract_datasets_from_evidence("We replay production traces from the cluster.")
    assert "production traces" in got
