"""Filesystem walk: fast, .gitignore-aware, with noisy dirs collapsed.

``walk()`` yields the files worth parsing. ``build_tree()`` turns the same set
of relative paths into the ``DirNode`` tree the renderer draws, collapsing any
directory with more direct children than ``collapse_threshold`` into a single
``foo/ (N files)`` summary line.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from .config import Config
from .model import DirNode

try:
    import pathspec
except ImportError:  # pragma: no cover - pathspec is a hard dep, but degrade
    pathspec = None  # type: ignore[assignment]


def _load_gitignore(root: Path) -> pathspec.PathSpec | None:
    """Compile the repo's root .gitignore into a matcher, if present.

    We honor the top-level .gitignore only — nested .gitignore files are rare
    in the dirs that matter for a map and walking them all would cost more than
    it saves. The built-in DEFAULT_IGNORE_DIRS cover the common nested cases.
    """
    if pathspec is None:
        return None
    gi = root / ".gitignore"
    if not gi.is_file():
        return None
    try:
        lines = gi.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return None
    return pathspec.PathSpec.from_lines("gitignore", lines)


def _rel_posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def walk(root: Path, config: Config) -> Iterator[Path]:
    """Yield files under ``root`` worth mapping, in stable sorted order.

    Skips: ignored dirs (defaults + config), .gitignore matches, dotfiles at
    any level, symlinks (loop safety), and binary-ish/oversized files. Order is
    deterministic so the map — and its cache — are reproducible.
    """
    spec = _load_gitignore(root)
    ignore_dirs = config.ignore_dirs
    glob_spec = (
        pathspec.PathSpec.from_lines("gitignore", config.extra_ignore_globs)
        if (pathspec is not None and config.extra_ignore_globs)
        else None
    )

    def _ignored(rel: str, is_dir: bool) -> bool:
        candidate = rel + "/" if is_dir else rel
        if spec is not None and (spec.match_file(rel) or spec.match_file(candidate)):
            return True
        if glob_spec is not None and (
            glob_spec.match_file(rel) or glob_spec.match_file(candidate)
        ):
            return True
        return False

    def _recurse(directory: Path) -> Iterator[Path]:
        try:
            entries = sorted(os.scandir(directory), key=lambda e: e.name)
        except (OSError, PermissionError):
            return
        for entry in entries:
            name = entry.name
            if name.startswith("."):
                continue  # dotfiles/dirs: .git already covered, skip the rest
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
                is_file = entry.is_file(follow_symlinks=False)
            except OSError:
                continue
            path = Path(entry.path)
            rel = _rel_posix(path, root)
            if is_dir:
                if name in ignore_dirs or _ignored(rel, True):
                    continue
                yield from _recurse(path)
            elif is_file:
                if _ignored(rel, False):
                    continue
                if _is_skippable_file(entry):
                    continue
                yield path

    yield from _recurse(root)


# Files larger than this are almost always data/minified blobs, not source we
# can usefully signature. Skip to keep the walk fast and the map clean.
_MAX_FILE_BYTES = 2_000_000


def _is_skippable_file(entry: os.DirEntry) -> bool:
    try:
        if entry.stat(follow_symlinks=False).st_size > _MAX_FILE_BYTES:
            return True
    except OSError:
        return True
    return False


def build_tree(rel_paths: list[str], root_name: str, collapse_threshold: int) -> DirNode:
    """Build the renderable directory tree from a flat list of relative paths.

    A directory whose *direct file children* exceed ``collapse_threshold`` is
    rendered as a single summary node instead of listing each file.
    """
    root = DirNode(name=root_name, is_dir=True)

    for rel in rel_paths:
        parts = rel.split("/")
        node = root
        for part in parts[:-1]:
            child = _find_dir(node, part)
            if child is None:
                child = DirNode(name=part, is_dir=True)
                node.children.append(child)
            node = child
        node.children.append(DirNode(name=parts[-1], is_dir=False))

    _sort_tree(root)
    _collapse(root, collapse_threshold)
    return root


def _find_dir(node: DirNode, name: str) -> DirNode | None:
    for child in node.children:
        if child.is_dir and child.name == name:
            return child
    return None


def _sort_tree(node: DirNode) -> None:
    # Directories first, then files, each alphabetical — the conventional,
    # scannable ordering.
    node.children.sort(key=lambda c: (not c.is_dir, c.name.lower()))
    for child in node.children:
        if child.is_dir:
            _sort_tree(child)


def _collapse(node: DirNode, threshold: int) -> None:
    direct_files = [c for c in node.children if not c.is_dir]
    has_subdirs = any(c.is_dir for c in node.children)
    if len(direct_files) > threshold and not has_subdirs:
        # Pure leaf dir full of files (migrations, fixtures, assets): summarize.
        count = len(direct_files)
        node.children = [DirNode(name="", is_dir=False, collapsed_count=count)]
        return
    for child in node.children:
        if child.is_dir:
            _collapse(child, threshold)
