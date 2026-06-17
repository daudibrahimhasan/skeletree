"""Token estimation — the hero metric.

We use the well-worn chars/4 heuristic rather than a real tokenizer. Rationale:
the map's value prop is *relative* savings (map vs. full read), and chars/4
tracks Claude's actual tokenizer closely enough for that ratio while adding
zero dependencies. tiktoken is OpenAI's tokenizer, not Claude's, so depending
on it would be both heavy and wrong. We say "approximate" loudly and move on.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import ProjectMap

CHARS_PER_TOKEN = 4.0


def estimate_tokens(text: str) -> int:
    """Approximate token count for a string (chars/4, rounded)."""
    return round(len(text) / CHARS_PER_TOKEN)


@dataclass
class TokenSavings:
    """The before/after the README and CLI both lead with."""

    map_tokens: int  # cost of reading the generated map
    baseline_tokens: int  # cost of reading every mapped file in full
    file_count: int

    @property
    def saved_tokens(self) -> int:
        return max(0, self.baseline_tokens - self.map_tokens)

    @property
    def percent_smaller(self) -> int:
        if self.baseline_tokens <= 0:
            return 0
        return round(100 * self.saved_tokens / self.baseline_tokens)

    def headline(self) -> str:
        """One-line summary, e.g. 'map ≈ 5.1K tokens · full-read baseline ≈ 51K · ~90% smaller'."""
        return (
            f"map ≈ {_human(self.map_tokens)} tokens · "
            f"full-read baseline ≈ {_human(self.baseline_tokens)} · "
            f"~{self.percent_smaller}% smaller"
        )


def compute_savings(project: ProjectMap, rendered_map: str) -> TokenSavings:
    """Compare the rendered map's size against reading every file in full."""
    baseline = sum(estimate_tokens_from_chars(f.char_count) for f in project.files)
    return TokenSavings(
        map_tokens=estimate_tokens(rendered_map),
        baseline_tokens=baseline,
        file_count=len(project.files),
    )


def estimate_tokens_from_chars(char_count: int) -> int:
    return round(char_count / CHARS_PER_TOKEN)


def _human(n: int) -> str:
    """Compact human form: 512 -> '512', 5123 -> '5.1K', 1_200_000 -> '1.2M'."""
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        return f"{n / 1000:.1f}K"
    return f"{n / 1_000_000:.1f}M"
