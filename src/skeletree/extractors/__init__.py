"""Extractor registry: extension -> (language, extract callable).

Python goes through the zero-dep stdlib extractor; everything else routes to
tree-sitter. ``extract_file`` is the single entry point the core pipeline uses.
"""

from __future__ import annotations

from ..model import Symbol
from . import python_ast, treesitter

PYTHON_EXTENSIONS = frozenset({".py", ".pyi"})


def language_for(ext: str) -> str:
    """Return the language name for an extension, or 'unknown'."""
    ext = ext.lower()
    if ext in PYTHON_EXTENSIONS:
        return "python"
    return treesitter.language_for_extension(ext) or "unknown"


def supported_extensions() -> set[str]:
    return set(PYTHON_EXTENSIONS) | set(treesitter.EXTENSION_LANGUAGE)


def extract_file(ext: str, source: str) -> tuple[str, list[Symbol]]:
    """Extract symbols for a file by extension. Returns (language, symbols).

    Unknown or unsupported extensions yield ('unknown', []) so the file is
    still listed in the tree, just without a symbol breakdown.
    """
    language = language_for(ext)
    if language == "python":
        return language, python_ast.extract(source)
    if language != "unknown":
        return language, treesitter.extract(source, language)
    return "unknown", []
