"""Walker + tree-building tests."""

from __future__ import annotations

from pathlib import Path

from skeletree.config import Config
from skeletree.walker import build_tree, walk


def _make_repo(root: Path) -> None:
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("x = 1\n")
    (root / "README.md").write_text("# hi\n")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "lib.js").write_text("// noise\n")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("noise\n")
    (root / ".gitignore").write_text("ignored_dir/\n*.log\n")
    (root / "ignored_dir").mkdir()
    (root / "ignored_dir" / "junk.py").write_text("junk = 1\n")
    (root / "app.log").write_text("log\n")


def _rel(paths, root):
    return sorted(p.relative_to(root).as_posix() for p in paths)


def test_walk_respects_defaults_and_gitignore(tmp_path):
    _make_repo(tmp_path)
    found = _rel(walk(tmp_path, Config()), tmp_path)
    assert "src/app.py" in found
    assert "README.md" in found
    assert not any("node_modules" in p for p in found)
    assert not any(".git" in p for p in found)
    assert "ignored_dir/junk.py" not in found
    assert "app.log" not in found


def test_walk_is_deterministic(tmp_path):
    _make_repo(tmp_path)
    a = _rel(walk(tmp_path, Config()), tmp_path)
    b = _rel(walk(tmp_path, Config()), tmp_path)
    assert a == b


def test_extra_ignore_globs(tmp_path):
    (tmp_path / "keep.py").write_text("1\n")
    (tmp_path / "skip.gen.py").write_text("1\n")
    cfg = Config(extra_ignore_globs=("*.gen.py",))
    found = _rel(walk(tmp_path, cfg), tmp_path)
    assert "keep.py" in found
    assert "skip.gen.py" not in found


def test_build_tree_collapses_large_dirs():
    paths = [f"migrations/m{i}.py" for i in range(50)] + ["src/app.py"]
    tree = build_tree(paths, "repo", collapse_threshold=40)
    migrations = next(c for c in tree.children if c.name == "migrations")
    assert len(migrations.children) == 1
    assert migrations.children[0].collapsed_count == 50


def test_build_tree_orders_dirs_before_files():
    tree = build_tree(["z.py", "src/a.py"], "repo", collapse_threshold=40)
    assert tree.children[0].name == "src"  # dir first
    assert tree.children[0].is_dir
    assert tree.children[1].name == "z.py"
