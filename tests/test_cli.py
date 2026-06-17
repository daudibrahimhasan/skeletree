"""End-to-end CLI tests (map + init) via Typer's CliRunner."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from skeletree.cli import app

runner = CliRunner()


def _repo(root: Path) -> None:
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text(
        '"""App."""\n\n\ndef main(argv: list[str]) -> int:\n    return 0\n'
    )


def test_map_writes_project_map(tmp_path):
    _repo(tmp_path)
    result = runner.invoke(app, [str(tmp_path)])
    assert result.exit_code == 0, result.output
    out_file = tmp_path / "PROJECT_MAP.md"
    assert out_file.is_file()
    text = out_file.read_text(encoding="utf-8")
    assert "# 🌳" in text
    assert "main(argv: list[str]) -> int" in text
    assert "smaller" in text  # headline embedded


def test_map_json_format(tmp_path):
    _repo(tmp_path)
    result = runner.invoke(app, [str(tmp_path), "--format", "json", "-o", "map.json"])
    assert result.exit_code == 0, result.output
    import json

    data = json.loads((tmp_path / "map.json").read_text(encoding="utf-8"))
    assert data["files"][0]["path"] == "src/app.py"
    assert "savings" in data


def test_map_stdout(tmp_path):
    _repo(tmp_path)
    result = runner.invoke(app, [str(tmp_path), "-o", "-"])
    assert result.exit_code == 0, result.output
    assert "## Tree" in result.stdout
    assert not (tmp_path / "PROJECT_MAP.md").exists()


def test_bad_format_errors(tmp_path):
    _repo(tmp_path)
    result = runner.invoke(app, [str(tmp_path), "--format", "xml"])
    assert result.exit_code == 2


def test_missing_directory_errors():
    result = runner.invoke(app, ["does/not/exist"])
    assert result.exit_code == 2


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "skeletree" in result.stdout


def test_init_creates_claude_md(tmp_path):
    result = runner.invoke(app, ["init", str(tmp_path)])
    assert result.exit_code == 0, result.output
    claude = tmp_path / "CLAUDE.md"
    assert claude.is_file()
    assert "PROJECT_MAP.md" in claude.read_text(encoding="utf-8")
    assert "SessionStart" in result.output  # hook snippet printed


def test_init_is_idempotent(tmp_path):
    runner.invoke(app, ["init", str(tmp_path)])
    runner.invoke(app, ["init", str(tmp_path)])
    text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert text.count("PROJECT_MAP.md") == 1


def test_init_appends_to_existing_claude_md(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# Existing\n\nSome notes.\n")
    runner.invoke(app, ["init", str(tmp_path)])
    text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Some notes." in text
    assert "PROJECT_MAP.md" in text
