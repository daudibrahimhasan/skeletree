"""Core data model shared by extractors, cache, and renderers.

Everything skeletree knows about a repo is one ``ProjectMap``: a list of
``FileEntry`` (each carrying its extracted ``Symbol`` list) plus the directory
tree. The model is deliberately plain — it serializes straight to/from JSON so
the cache and the ``--format json`` output share the same shapes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Symbol:
    """A single top-level (or nested) declaration: signature, never a body.

    ``children`` holds nested declarations — methods of a class, mostly. Keeping
    them nested (rather than flat with a parent pointer) is what lets the
    renderer indent without a second pass.
    """

    kind: str  # "class" | "function" | "method" | "const" | "interface" | ...
    name: str
    signature: str = ""  # e.g. "(self, x: int) -> str"; "" when N/A
    decorators: list[str] = field(default_factory=list)
    doc: str = ""  # first line of the docstring, if any
    lineno: int = 0
    children: list[Symbol] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"kind": self.kind, "name": self.name}
        if self.signature:
            d["signature"] = self.signature
        if self.decorators:
            d["decorators"] = self.decorators
        if self.doc:
            d["doc"] = self.doc
        if self.lineno:
            d["lineno"] = self.lineno
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Symbol:
        return cls(
            kind=d["kind"],
            name=d["name"],
            signature=d.get("signature", ""),
            decorators=list(d.get("decorators", [])),
            doc=d.get("doc", ""),
            lineno=d.get("lineno", 0),
            children=[cls.from_dict(c) for c in d.get("children", [])],
        )


@dataclass
class FileEntry:
    """One parsed file: its symbols plus the stat used for cache invalidation.

    ``char_count`` is the file's full source length — the renderer never emits
    it, but the token estimator needs it to compute the full-read baseline.
    """

    path: str  # repo-relative, forward slashes
    language: str  # "python", "javascript", ... or "unknown"
    symbols: list[Symbol] = field(default_factory=list)
    size: int = 0  # bytes on disk (cache key)
    mtime: float = 0.0  # cache key
    char_count: int = 0  # source length, for the token baseline
    error: str = ""  # set when parsing failed; file still listed path-only

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "path": self.path,
            "language": self.language,
            "size": self.size,
            "mtime": self.mtime,
            "char_count": self.char_count,
            "symbols": [s.to_dict() for s in self.symbols],
        }
        if self.error:
            d["error"] = self.error
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FileEntry:
        return cls(
            path=d["path"],
            language=d["language"],
            symbols=[Symbol.from_dict(s) for s in d.get("symbols", [])],
            size=d.get("size", 0),
            mtime=d.get("mtime", 0.0),
            char_count=d.get("char_count", 0),
            error=d.get("error", ""),
        )


@dataclass
class DirNode:
    """A node in the rendered directory tree.

    A node is either a directory (``children`` populated) or a collapsed
    summary (``collapsed_count`` set) — e.g. ``migrations/ (142 files)``.
    """

    name: str
    is_dir: bool = True
    children: list[DirNode] = field(default_factory=list)
    collapsed_count: int = 0  # >0 means "N files hidden", render as summary


@dataclass
class ProjectMap:
    """The whole product: root name, tree, and every file entry."""

    root_name: str
    files: list[FileEntry] = field(default_factory=list)
    tree: DirNode | None = None
    truncated: int = 0  # how many files were dropped by --max-files

    def to_dict(self) -> dict[str, Any]:
        return {
            "root_name": self.root_name,
            "truncated": self.truncated,
            "files": [f.to_dict() for f in self.files],
        }
