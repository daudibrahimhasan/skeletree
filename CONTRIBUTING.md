# Contributing to skeletree

Thanks for helping! skeletree aims to be small, fast, and dependency-light. PRs that keep it that way are the easiest to merge.

## Dev setup

```bash
git clone https://github.com/daudibrahimhasan/skeletree.git
cd skeletree
python -m venv .venv && . .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
ruff check src tests
```

## Project shape

Run `skeletree -o -` on the repo for the current map — it's the fastest way to learn the layout. The short version:

- `walker.py` — finds files (gitignore + defaults), builds the tree.
- `extractors/` — `python_ast.py` (stdlib) and `treesitter.py` (everything else).
- `render/` — `markdown.py` (default) and `json_out.py`.
- `tokens.py` — the savings metric. `cache.py` — incremental re-parsing.
- `core.py` — ties it together. `cli.py` — the Typer entry point.

## Adding a language

Most languages are a single entry in `SPECS` in `extractors/treesitter.py`:

1. Add the file extension(s) to `EXTENSION_LANGUAGE`.
2. Add a `LangSpec` mapping the grammar's node types to symbol kinds. The
   quickest way to discover node types is to parse a snippet and print the tree
   (see the traversal in `treesitter.py` — `kind`/`type`, `named_children`).
3. Add a fixture-style test in `tests/test_treesitter.py` asserting the symbols
   you expect.

Keep the spec minimal — surface the high-signal declarations (classes,
functions, types, exports), not every node.

## Guidelines

- **No bodies, ever.** The whole point is signatures only. Tests assert this.
- **Stay cheap.** New runtime dependencies need a strong justification.
- **Deterministic output.** The walk is sorted; keep it that way so maps and the
  cache stay reproducible.
- Format/lint with `ruff`, and add tests for new behavior.

## Good first issues

- Add a language (Kotlin, Swift, C#, PHP, Scala, Zig…).
- Improve signature fidelity for C/C++ (the trickiest grammar).
- A `--diff` mode that maps only files changed since a git ref.
