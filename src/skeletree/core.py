"""The pipeline: walk -> extract (cached) -> build tree -> ProjectMap.

``build_map`` is the one function the CLI and tests call. It returns the map
plus a small ``BuildStats`` (parsed vs. cache-hit counts, total chars, and
per-extension token breakdown) so callers — and the cache test — can see what
actually got re-parsed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from . import deps as _deps
from .cache import Cache
from .config import Config
from .extractors import extract_file
from .model import FileEntry, ProjectMap
from .walker import build_tree, walk


@dataclass
class BuildStats:
    total_files: int = 0
    parsed: int = 0  # actually read + extracted this run
    cached: int = 0  # served from cache, untouched
    truncated: int = 0  # dropped by max_files
    total_chars: int = 0  # sum of all source char counts
    by_ext: dict[str, int] = field(default_factory=dict)  # ext -> token count


def build_map(root: Path, config: Config) -> tuple[ProjectMap, BuildStats]:
    root = root.resolve()
    cache = Cache(root, enabled=config.use_cache)
    cache.load()

    stats = BuildStats()
    files: list[FileEntry] = []

    for path in walk(root, config):
        if len(files) >= config.max_files:
            stats.truncated += 1
            continue
        entry = _entry_for(path, root, cache, stats)
        if entry is not None:
            files.append(entry)
            # Accumulate per-extension token stats for the CLI summary.
            stats.total_chars += entry.char_count
            ext = os.path.splitext(entry.path)[1].lower() or "(no ext)"
            stats.by_ext[ext] = stats.by_ext.get(ext, 0) + (entry.char_count // 4)

    stats.total_files = len(files)
    cache.save()

    project = ProjectMap(root_name=root.name, files=files, truncated=stats.truncated)
    project.tree = build_tree(
        [f.path for f in files], root.name, config.collapse_threshold
    )
    project.deps = _deps.detect(root)
    project.description = _deps.detect_description(root)
    return project, stats


def _entry_for(
    path: Path, root: Path, cache: Cache, stats: BuildStats
) -> FileEntry | None:
    rel = path.relative_to(root).as_posix()
    try:
        st = path.stat()
    except OSError:
        return None
    size, mtime = st.st_size, st.st_mtime

    cached = cache.get(rel, size, mtime)
    if cached is not None:
        stats.cached += 1
        cache.put(cached)  # carry forward so it survives the next save
        return cached

    entry = _parse(path, rel, size, mtime)
    if entry is None:
        return None
    stats.parsed += 1
    cache.put(entry)
    return entry


def _parse(path: Path, rel: str, size: int, mtime: float) -> FileEntry | None:
    try:
        source = path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeDecodeError):
        # Binary or unreadable: still surface it in the tree, path-only.
        return FileEntry(
            path=rel,
            language="unknown",
            size=size,
            mtime=mtime,
            char_count=0,
        )

    language, symbols = extract_file(path.suffix, source)
    return FileEntry(
        path=rel,
        language=language,
        symbols=symbols,
        size=size,
        mtime=mtime,
        char_count=len(source),
    )
