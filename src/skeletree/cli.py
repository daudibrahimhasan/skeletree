"""skeletree CLI.

``skeletree`` (no subcommand) generates the map — that's the 90% path.
``skeletree init`` wires the map into Claude Code. Built on Typer.
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from typer.core import TyperGroup

from . import __version__
from .config import Config
from .core import build_map
from .render import json_out, markdown
from .tokens import compute_savings

_DEFAULT_COMMAND = "map"


class DefaultCommandGroup(TyperGroup):
    """Run the ``map`` command when no subcommand is given.

    Lets ``skeletree``, ``skeletree path``, and ``skeletree --format json`` all
    map a repo, while ``skeletree init`` still dispatches to the init command.
    Any leading token that isn't a known command (a path, or a map option) is
    routed to ``map``; ``--help`` alone still shows the group help.
    """

    def parse_args(self, ctx, args):
        if not args:
            args = [_DEFAULT_COMMAND]
        elif args[0] not in self.commands and args[0] not in ("--help", "-h"):
            args = [_DEFAULT_COMMAND, *args]
        return super().parse_args(ctx, args)


app = typer.Typer(
    cls=DefaultCommandGroup,
    add_completion=False,
    no_args_is_help=False,
    help="Generate a compact, token-cheap project map (tree + signatures, no bodies).",
)


def _force_utf8() -> None:
    """Ensure stdout/stderr can emit the map's Unicode on any platform.

    Windows consoles default to cp1252, which chokes on the tree glyph and the
    '≈'/'·' in the headline. Reconfiguring to UTF-8 is harmless elsewhere.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):  # pragma: no cover - replaced stream
                pass


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"skeletree {__version__}")
        raise typer.Exit()


@app.command("map")
def map_command(
    path: Path = typer.Argument(
        Path("."), help="Repo root to map.", show_default=False
    ),
    out: str = typer.Option(
        None, "--out", "-o", help="Output file. Use '-' for stdout. [default: PROJECT_MAP.md]"
    ),
    fmt: str = typer.Option(
        None, "--format", "-f", help="Output format: md | json. [default: md]"
    ),
    max_files: int | None = typer.Option(
        None, "--max-files", help="Cap files scanned. [default: 5000]"
    ),
    no_cache: bool = typer.Option(
        False, "--no-cache", help="Ignore the incremental cache; re-parse everything."
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress the summary line (for hooks/CI)."
    ),
    _version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True, help="Show version."
    ),
) -> None:
    """Generate the project map (this is the default — runs with no subcommand)."""
    _force_utf8()
    _run_map(path, out=out, fmt=fmt, max_files=max_files, no_cache=no_cache, quiet=quiet)


def _run_map(
    path: Path,
    *,
    out: str | None,
    fmt: str | None,
    max_files: int | None,
    no_cache: bool,
    quiet: bool,
) -> None:
    root = path.resolve()
    if not root.is_dir():
        typer.secho(f"skeletree: not a directory: {path}", fg="red", err=True)
        raise typer.Exit(2)

    config = Config.load(root).merged_with_cli(
        out=out, fmt=fmt, max_files=max_files, no_cache=no_cache
    )
    if config.fmt not in ("md", "json"):
        typer.secho(f"skeletree: unknown format '{config.fmt}'", fg="red", err=True)
        raise typer.Exit(2)

    project, stats = build_map(root, config)

    if config.fmt == "json":
        # Two-pass: render to measure, then embed the measured savings.
        first = json_out.render(project, compute_savings(project, ""))
        savings = compute_savings(project, first)
        output = json_out.render(project, savings)
    else:
        first = markdown.render(project, headline="")
        savings = compute_savings(project, first)
        output = markdown.render(project, savings.headline())

    _emit(output, config.out, root)

    if not quiet:
        target = "stdout" if config.out == "-" else config.out
        typer.secho(savings.headline(), fg="green", bold=True, err=True)
        typer.echo(
            f"  {stats.total_files} files "
            f"({stats.parsed} parsed, {stats.cached} cached) → {target}",
            err=True,
        )


def _emit(output: str, out: str, root: Path) -> None:
    if out == "-":
        # Bypass any narrow console codec by writing UTF-8 bytes directly.
        buffer = getattr(sys.stdout, "buffer", None)
        if buffer is not None:
            buffer.write(output.encode("utf-8"))
        else:  # pragma: no cover - exotic stdout
            sys.stdout.write(output)
        return
    dest = Path(out)
    if not dest.is_absolute():
        dest = root / dest
    try:
        dest.write_text(output, encoding="utf-8")
    except OSError as exc:
        typer.secho(f"skeletree: cannot write {dest}: {exc}", fg="red", err=True)
        raise typer.Exit(1) from exc


_CLAUDE_POINTER = "Project map: see `PROJECT_MAP.md` — regenerate with `skeletree`."

_HOOK_SNIPPET = """\
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          { "type": "command", "command": "skeletree --quiet" }
        ]
      }
    ]
  }
}"""


@app.command()
def init(
    path: Path = typer.Argument(Path("."), help="Repo root.", show_default=False),
) -> None:
    """Wire the map into Claude Code: add a CLAUDE.md pointer, print a hook snippet."""
    _force_utf8()
    root = path.resolve()
    claude_md = root / "CLAUDE.md"

    if claude_md.is_file():
        existing = claude_md.read_text(encoding="utf-8")
        if "PROJECT_MAP.md" in existing:
            typer.echo("✓ CLAUDE.md already references PROJECT_MAP.md (no change).")
        else:
            sep = "" if existing.endswith("\n") else "\n"
            claude_md.write_text(existing + sep + _CLAUDE_POINTER + "\n", encoding="utf-8")
            typer.echo("✓ Appended project-map pointer to CLAUDE.md.")
    else:
        claude_md.write_text(f"# {root.name}\n\n{_CLAUDE_POINTER}\n", encoding="utf-8")
        typer.echo("✓ Created CLAUDE.md with a project-map pointer.")

    typer.echo("")
    typer.echo("To regenerate the map automatically each session, add this to")
    typer.echo("your Claude Code settings.json (opt-in — not written for you):")
    typer.echo("")
    typer.echo(_HOOK_SNIPPET)


if __name__ == "__main__":  # pragma: no cover
    app()
