"""Renderer tests for Markdown and JSON."""

from __future__ import annotations

import json

from skeletree.model import DirNode, FileEntry, ProjectMap, Symbol
from skeletree.render import json_out, markdown
from skeletree.tokens import compute_savings


def _project():
    cls = Symbol(
        kind="class",
        name="Server",
        doc="HTTP server.",
        children=[
            Symbol(kind="method", name="start", signature="(self, port: int) -> None"),
            Symbol(kind="method", name="run", signature="async (self) -> None"),
        ],
    )
    fn = Symbol(kind="function", name="make", signature="(c: Config) -> Server")
    const = Symbol(kind="const", name="VERSION", signature=": str")
    entry = FileEntry(
        path="src/api.py",
        language="python",
        symbols=[cls, fn, const],
        char_count=8000,
    )
    project = ProjectMap(root_name="demo", files=[entry])
    project.tree = DirNode(
        name="demo",
        children=[
            DirNode(
                name="src",
                children=[DirNode(name="api.py", is_dir=False)],
            )
        ],
    )
    return project


def test_markdown_has_headline_tree_and_symbols():
    project = _project()
    out = markdown.render(project, "map ≈ 2K · ~90% smaller")
    assert "map ≈ 2K · ~90% smaller" in out
    assert "## Tree" in out
    assert "src/" in out
    assert "api.py" in out
    assert "## Symbols" in out
    assert "class Server" in out
    assert "HTTP server." in out


def test_markdown_async_method_rendered():
    out = markdown.render(_project(), "h")
    assert "async run(self)" in out


def test_markdown_callable_has_no_kind_word():
    out = markdown.render(_project(), "h")
    # functions read as name(sig), not "function make(...)"
    assert "make(c: Config) -> Server" in out
    assert "function make" not in out


def test_markdown_const_tagged():
    out = markdown.render(_project(), "h")
    assert "const VERSION: str" in out


def test_markdown_no_bodies():
    out = markdown.render(_project(), "h")
    assert "return" not in out


def test_collapsed_dir_rendered_as_summary():
    project = ProjectMap(root_name="demo", files=[])
    project.tree = DirNode(
        name="demo",
        children=[
            DirNode(
                name="migrations",
                children=[DirNode(name="", is_dir=False, collapsed_count=142)],
            )
        ],
    )
    out = markdown.render(project, "h")
    assert "migrations/ (142 files)" in out


def test_json_round_trips_and_has_savings():
    project = _project()
    savings = compute_savings(project, markdown.render(project, ""))
    out = json_out.render(project, savings)
    data = json.loads(out)
    assert data["root_name"] == "demo"
    assert data["savings"]["percent_smaller"] > 0
    assert data["files"][0]["path"] == "src/api.py"
    assert data["files"][0]["symbols"][0]["name"] == "Server"
