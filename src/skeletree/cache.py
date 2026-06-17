"""Incremental cache: only re-parse files that actually changed.

Keyed by repo-relative path; each entry stores ``(size, mtime)`` plus the
serialized ``FileEntry``. On a run, a file whose size and mtime both match its
cached entry is reused verbatim — no read, no parse. This is what makes
hook-driven regen on session start effectively free for unchanged repos.

The cache file (``.skeletree-cache.json``) lives at the repo root and is safe
to delete or .gitignore; a missing/corrupt cache just means a full re-parse.
"""

from __future__ import annotations

import json
from pathlib import Path

from .model import FileEntry

CACHE_FILENAME = ".skeletree-cache.json"
CACHE_VERSION = 1


class Cache:
    """Load-once, query-by-stat, write-once cache of FileEntry objects."""

    def __init__(self, root: Path, enabled: bool = True):
        self.path = root / CACHE_FILENAME
        self.enabled = enabled
        self._entries: dict[str, FileEntry] = {}
        self._fresh: dict[str, FileEntry] = {}  # what we'll persist next write

    def load(self) -> None:
        if not self.enabled or not self.path.is_file():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, dict) or data.get("version") != CACHE_VERSION:
            return
        for rel, entry in data.get("files", {}).items():
            try:
                self._entries[rel] = FileEntry.from_dict(entry)
            except (KeyError, TypeError):
                continue

    def get(self, rel: str, size: int, mtime: float) -> FileEntry | None:
        """Return the cached entry iff size and mtime both match."""
        if not self.enabled:
            return None
        cached = self._entries.get(rel)
        if cached is None:
            return None
        if cached.size != size or not _mtime_eq(cached.mtime, mtime):
            return None
        return cached

    def put(self, entry: FileEntry) -> None:
        """Record an entry to be persisted on ``save``."""
        self._fresh[entry.path] = entry

    def save(self) -> None:
        if not self.enabled:
            return
        payload = {
            "version": CACHE_VERSION,
            "files": {rel: e.to_dict() for rel, e in self._fresh.items()},
        }
        try:
            self.path.write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )
        except OSError:
            pass  # cache is best-effort; never fail a run over it


def _mtime_eq(a: float, b: float) -> bool:
    # Filesystems vary in mtime resolution; treat sub-millisecond as equal.
    return abs(a - b) < 1e-3
