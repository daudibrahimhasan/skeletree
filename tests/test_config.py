"""Config loading and CLI merge precedence."""

from __future__ import annotations

from skeletree.config import DEFAULT_IGNORE_DIRS, Config


def test_defaults(tmp_path):
    cfg = Config.load(tmp_path)
    assert cfg.out == "PROJECT_MAP.md"
    assert cfg.fmt == "md"
    assert cfg.use_cache is True
    assert ".git" in cfg.ignore_dirs


def test_loads_from_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.skeletree]\n"
        'out = "MAP.md"\n'
        'format = "json"\n'
        "max_files = 10\n"
        'ignore_dirs = ["fixtures"]\n'
    )
    cfg = Config.load(tmp_path)
    assert cfg.out == "MAP.md"
    assert cfg.fmt == "json"
    assert cfg.max_files == 10
    assert "fixtures" in cfg.ignore_dirs
    assert "node_modules" in cfg.ignore_dirs  # defaults still present


def test_standalone_toml_takes_priority(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[tool.skeletree]\nout = "from_pyproject.md"\n')
    (tmp_path / ".skeletree.toml").write_text('out = "from_standalone.md"\n')
    assert Config.load(tmp_path).out == "from_standalone.md"


def test_malformed_toml_falls_back(tmp_path, capsys):
    (tmp_path / ".skeletree.toml").write_text("this is = = not toml")
    cfg = Config.load(tmp_path)
    assert cfg.out == "PROJECT_MAP.md"  # defaults


def test_cli_overrides_win():
    cfg = Config(out="file.md", fmt="md")
    merged = cfg.merged_with_cli(fmt="json", no_cache=True)
    assert merged.fmt == "json"
    assert merged.use_cache is False
    assert merged.out == "file.md"  # untouched


def test_default_ignore_dirs_includes_common_noise():
    for d in ("node_modules", "venv", ".venv", "dist", "build", "target", "__pycache__"):
        assert d in DEFAULT_IGNORE_DIRS
