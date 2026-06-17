"""Incremental cache behavior: unchanged files aren't re-parsed."""

from __future__ import annotations

import os
import time
from pathlib import Path

from skeletree.config import Config
from skeletree.core import build_map


def _repo(root: Path, n: int = 3) -> None:
    for i in range(n):
        (root / f"mod{i}.py").write_text(f"def f{i}(): ...\n")


def test_second_run_uses_cache(tmp_path):
    _repo(tmp_path)
    _, first = build_map(tmp_path, Config())
    assert first.parsed == 3
    assert first.cached == 0

    _, second = build_map(tmp_path, Config())
    assert second.parsed == 0
    assert second.cached == 3


def test_touching_one_file_reparses_only_it(tmp_path):
    _repo(tmp_path)
    build_map(tmp_path, Config())

    changed = tmp_path / "mod1.py"
    # Bump mtime well past resolution and change size.
    time.sleep(0.02)
    changed.write_text("def f1(x, y, z): ...\n")
    future = time.time() + 5
    os.utime(changed, (future, future))

    _, stats = build_map(tmp_path, Config())
    assert stats.parsed == 1
    assert stats.cached == 2


def test_no_cache_reparses_everything(tmp_path):
    _repo(tmp_path)
    build_map(tmp_path, Config())
    _, stats = build_map(tmp_path, Config(use_cache=False))
    assert stats.parsed == 3
    assert stats.cached == 0


def test_cache_file_written(tmp_path):
    _repo(tmp_path)
    build_map(tmp_path, Config())
    assert (tmp_path / ".skeletree-cache.json").is_file()
