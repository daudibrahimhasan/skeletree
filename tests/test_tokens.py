"""Token estimation and savings math."""

from __future__ import annotations

from skeletree.model import FileEntry, ProjectMap
from skeletree.tokens import compute_savings, estimate_tokens


def test_estimate_is_chars_over_four():
    assert estimate_tokens("a" * 400) == 100


def test_savings_headline_and_percent():
    project = ProjectMap(
        root_name="x",
        files=[FileEntry(path="a.py", language="python", char_count=40_000)],
    )
    rendered = "x" * 4_000  # ~1000 tokens
    savings = compute_savings(project, rendered)
    assert savings.baseline_tokens == 10_000
    assert savings.map_tokens == 1_000
    assert savings.percent_smaller == 90
    assert "90% smaller" in savings.headline()


def test_human_formatting_in_headline():
    project = ProjectMap(
        root_name="x",
        files=[FileEntry(path="a", language="python", char_count=40_000)],
    )
    savings = compute_savings(project, "x" * 4_000_000)
    head = savings.headline()
    assert "1.0M" in head  # 1,000,000 map tokens


def test_no_negative_savings():
    project = ProjectMap(root_name="x", files=[])
    savings = compute_savings(project, "x" * 4000)
    assert savings.saved_tokens == 0
    assert savings.percent_smaller == 0
