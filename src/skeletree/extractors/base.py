"""Extractor protocol and the shared result type.

An extractor takes a file's source text and returns the symbols it can see —
signatures only, never bodies. Each extractor declares the languages it
handles; the registry (``__init__.py``) maps file extensions to one.
"""

from __future__ import annotations

from typing import Protocol

from ..model import Symbol


class Extractor(Protocol):
    """Anything that can turn source into a list of top-level symbols."""

    language: str

    def extract(self, source: str) -> list[Symbol]:
        """Return top-level symbols (with nested children). Must not raise on
        ordinary syntax errors — return what it can, or [] if nothing."""
        ...
