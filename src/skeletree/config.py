"""Zero-config defaults, with optional overrides from pyproject.toml / .skeletree.toml.

skeletree runs with no config at all. A repo *may* add a ``[tool.skeletree]``
table to ``pyproject.toml`` (or a standalone ``.skeletree.toml``) to tweak
ignores, output path, format, or limits. Config is resolved once, at the repo
root, and threaded through the rest of the pipeline.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - 3.10 fallback
    import tomli as tomllib

# Directories that are virtually never worth mapping. The walker also honors
# .gitignore; these are the belt-and-suspenders defaults that apply even in
# repos without one (or for paths .gitignore happens to miss).
DEFAULT_IGNORE_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "venv",
        ".venv",
        "env",
        ".env",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        "dist",
        "build",
        ".next",
        ".nuxt",
        ".svelte-kit",
        "target",  # rust/java
        "out",
        ".idea",
        ".vscode",
        ".gradle",
        "vendor",  # go/php
        ".terraform",
        "coverage",
        ".cache",
        "__snapshots__",
    }
)

# Per-directory file count above which the directory collapses to a summary
# line in the tree (e.g. "migrations/ (142 files)"). Keeps generated/asset
# dirs from drowning the map.
DEFAULT_COLLAPSE_THRESHOLD = 40


@dataclass(frozen=True)
class Config:
    """Resolved configuration. Frozen so it can be passed around freely."""

    out: str = "PROJECT_MAP.md"
    fmt: str = "md"  # "md" | "json"
    max_files: int = 5000
    collapse_threshold: int = DEFAULT_COLLAPSE_THRESHOLD
    use_cache: bool = True
    extra_ignore_dirs: frozenset[str] = field(default_factory=frozenset)
    extra_ignore_globs: tuple[str, ...] = ()

    @property
    def ignore_dirs(self) -> frozenset[str]:
        return DEFAULT_IGNORE_DIRS | self.extra_ignore_dirs

    @classmethod
    def load(cls, root: Path) -> Config:
        """Read ``[tool.skeletree]`` from pyproject.toml or .skeletree.toml.

        Missing files, missing table, and malformed TOML all fall back to
        defaults silently-ish (a malformed file is reported but non-fatal).
        """
        data = _read_table(root)
        if not data:
            return cls()
        return cls(
            out=str(data.get("out", "PROJECT_MAP.md")),
            fmt=str(data.get("format", "md")),
            max_files=int(data.get("max_files", 5000)),
            collapse_threshold=int(
                data.get("collapse_threshold", DEFAULT_COLLAPSE_THRESHOLD)
            ),
            use_cache=bool(data.get("cache", True)),
            extra_ignore_dirs=frozenset(data.get("ignore_dirs", [])),
            extra_ignore_globs=tuple(data.get("ignore", [])),
        )

    def merged_with_cli(
        self,
        *,
        out: str | None = None,
        fmt: str | None = None,
        max_files: int | None = None,
        no_cache: bool = False,
    ) -> Config:
        """Layer explicit CLI flags on top of file config (CLI wins)."""
        changes: dict[str, Any] = {}
        if out is not None:
            changes["out"] = out
        if fmt is not None:
            changes["fmt"] = fmt
        if max_files is not None:
            changes["max_files"] = max_files
        if no_cache:
            changes["use_cache"] = False
        return replace(self, **changes)


def _read_table(root: Path) -> dict[str, Any]:
    standalone = root / ".skeletree.toml"
    if standalone.is_file():
        try:
            return tomllib.loads(standalone.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, OSError) as exc:
            print(f"skeletree: ignoring malformed {standalone.name}: {exc}", file=sys.stderr)
            return {}

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            parsed = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, OSError) as exc:
            print(f"skeletree: ignoring malformed pyproject.toml: {exc}", file=sys.stderr)
            return {}
        return parsed.get("tool", {}).get("skeletree", {}) or {}

    return {}
