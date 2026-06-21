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
