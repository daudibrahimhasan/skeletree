"""Markdown renderer — compact, token-efficient map.

Three sections: Tree (noisy dirs collapsed), Deps (library names only),
and Symbols (signatures, methods nested under class). Designed to give
an AI agent maximum information per token: no decorative preamble, no
backticks around every symbol name, no per-file language labels.
"""

from __future__ import annotations

from ..model import DirNode, FileEntry, ProjectMap, Symbol

_DOC_MAX = 80
_CALLABLE = frozenset({"function", "method"})
_CLASSLIKE = frozenset(
    {"class", "struct", "interface", "enum", "trait", "impl", "module", "record", "type"}
)


def render(project: ProjectMap, headline: str) -> str:
    lines: list[str] = []

    # Header: project name + optional description + metric
    lines.append(f"# {project.root_name}")
    if project.description:
        lines.append(f"> {project.description}")
    if headline:
        lines.append(f"> skeletree · {headline}")
    if project.truncated:
        lines.append(f"> ⚠ {project.truncated} files omitted (max-files limit)")
    lines.append("")

    # Deps section
    if project.deps:
        lines.append("## Deps")
        for d in project.deps:
            parts = []
            if d.runtime:
                parts.append(f"{d.ecosystem}: {', '.join(d.runtime)}")
            if d.dev:
                parts.append(f"dev: {', '.join(d.dev)}")
            lines.append(" | ".join(parts))
        lines.append("")

    # Tree section
    lines.append("## Tree")
    lines.append("```")
    lines.extend(_tree_lines(project.tree) if project.tree else [])
    lines.append("```")
    lines.append("")

    # Symbols section
    files_with_symbols = [f for f in project.files if f.symbols]
    if files_with_symbols:
        lines.append("## Symbols")
        lines.append("")
        for entry in files_with_symbols:
            lines.extend(_file_section(entry))

    # Footer
    lines.append("---")
    lines.append(
        "*Built with [skeletree](https://github.com/daudibrahimhasan/skeletree) "
        "by [@daudibrahimhasan](https://github.com/daudibrahimhasan) · "
        "daudibrahimhasan@gmail.com*"
    )

    return "\n".join(lines).rstrip() + "\n"


# --- tree ------------------------------------------------------------------


def _tree_lines(root: DirNode) -> list[str]:
    lines = [f"{root.name}/"]
    _walk_tree(root, 1, lines)
    return lines


def _walk_tree(node: DirNode, depth: int, lines: list[str]) -> None:
    indent = "  " * depth
    for child in node.children:
        if child.is_dir:
            collapsed = _collapsed_child(child)
            if collapsed is not None:
                lines.append(f"{indent}{child.name}/ ({collapsed} files)")
            else:
                lines.append(f"{indent}{child.name}/")
                _walk_tree(child, depth + 1, lines)
        elif not child.collapsed_count:
            lines.append(f"{indent}{child.name}")


def _collapsed_child(node: DirNode) -> int | None:
    if len(node.children) == 1 and node.children[0].collapsed_count:
        return node.children[0].collapsed_count
    return None


# --- symbols ---------------------------------------------------------------


def _file_section(entry: FileEntry) -> list[str]:
    lines = [entry.path]
    for sym in entry.symbols:
        _render_symbol(sym, 0, lines)
    lines.append("")
    return lines


def _render_symbol(sym: Symbol, depth: int, lines: list[str]) -> None:
    indent = "  " * depth
    lines.append(f"{indent}- {_symbol_text(sym)}")
    for child in sym.children:
        _render_symbol(child, depth + 1, lines)


def _symbol_text(sym: Symbol) -> str:
    deco = "".join(f"@{d} " for d in sym.decorators)
    body = _declaration(sym)
    text = f"{deco}{body}"
    if sym.doc:
        text += f" — {_clip(sym.doc)}"
    return text


def _declaration(sym: Symbol) -> str:
    sig = sym.signature
    if sym.kind in _CALLABLE:
        prefix = ""
        if sig.startswith("async "):
            prefix, sig = "async ", sig[len("async "):]
        return f"{prefix}{sym.name}{sig}"
    if sym.kind in _CLASSLIKE:
        return f"{sym.kind} {sym.name}{sig}"
    return f"{sym.kind} {sym.name}{sig}"


def _clip(text: str) -> str:
    text = text.strip()
    if len(text) <= _DOC_MAX:
        return text
    return text[:_DOC_MAX - 1].rstrip() + "…"
