"""Zero-dependency Python extractor built on the stdlib ``ast``.

Covers the cases that matter for a map: classes (with bases), top-level and
nested ``def``/``async def`` with full argument signatures and return
annotations, decorators, module/class/function docstring first lines, and
top-level constants (UPPER_CASE or annotated assignments). Method bodies are
never read — only the signature line.
"""

from __future__ import annotations

import ast

from ..model import Symbol

language = "python"


def extract(source: str) -> list[Symbol]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    return _body_symbols(tree.body, top_level=True)


def _body_symbols(body: list[ast.stmt], *, top_level: bool) -> list[Symbol]:
    symbols: list[Symbol] = []
    for node in body:
        if isinstance(node, ast.ClassDef):
            symbols.append(_class_symbol(node))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(_func_symbol(node, kind="function"))
        elif top_level and isinstance(node, (ast.Assign, ast.AnnAssign)):
            const = _const_symbol(node)
            if const is not None:
                symbols.append(const)
    return symbols


def _class_symbol(node: ast.ClassDef) -> Symbol:
    bases = [_expr(b) for b in node.bases]
    bases += [f"{kw.arg}={_expr(kw.value)}" for kw in node.keywords if kw.arg]
    signature = f"({', '.join(bases)})" if bases else ""
    methods: list[Symbol] = []
    for child in node.body:
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            methods.append(_func_symbol(child, kind="method"))
        elif isinstance(child, ast.ClassDef):
            methods.append(_class_symbol(child))
    return Symbol(
        kind="class",
        name=node.name,
        signature=signature,
        decorators=[_expr(d) for d in node.decorator_list],
        doc=_docstring(node),
        lineno=node.lineno,
        children=methods,
    )


def _func_symbol(node: ast.FunctionDef | ast.AsyncFunctionDef, *, kind: str) -> Symbol:
    sig = _format_args(node.args)
    if node.returns is not None:
        sig += f" -> {_expr(node.returns)}"
    prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
    return Symbol(
        kind=kind,
        name=node.name,
        signature=prefix + sig,
        decorators=[_expr(d) for d in node.decorator_list],
        doc=_docstring(node),
        lineno=node.lineno,
    )


def _const_symbol(node: ast.Assign | ast.AnnAssign) -> Symbol | None:
    if isinstance(node, ast.AnnAssign):
        if not isinstance(node.target, ast.Name):
            return None
        name = node.target.id
        ann = _expr(node.annotation)
        return Symbol(kind="const", name=name, signature=f": {ann}", lineno=node.lineno)

    # Plain assignment: only surface UPPER_CASE names (module constants);
    # lowercase module-level assignments are usually wiring, not API.
    targets = [t for t in node.targets if isinstance(t, ast.Name)]
    names = [t.id for t in targets if t.id.isupper() and not t.id.startswith("_")]
    if not names:
        return None
    return Symbol(kind="const", name=", ".join(names), lineno=node.lineno)


def _format_args(args: ast.arguments) -> str:
    parts: list[str] = []
    posonly = list(args.posonlyargs)
    regular = list(args.args)
    defaults = list(args.defaults)
    # defaults align to the tail of posonly+regular
    all_pos = posonly + regular
    offset = len(all_pos) - len(defaults)

    for i, arg in enumerate(all_pos):
        piece = _arg(arg)
        if i >= offset:
            piece += f"={_default(defaults[i - offset])}"
        parts.append(piece)
        if posonly and i == len(posonly) - 1:
            parts.append("/")

    if args.vararg:
        parts.append("*" + _arg(args.vararg))
    elif args.kwonlyargs:
        parts.append("*")

    for arg, default in zip(args.kwonlyargs, args.kw_defaults, strict=True):
        piece = _arg(arg)
        if default is not None:
            piece += f"={_default(default)}"
        parts.append(piece)

    if args.kwarg:
        parts.append("**" + _arg(args.kwarg))

    return "(" + ", ".join(parts) + ")"


_DEFAULT_MAX = 24


def _default(node: ast.AST) -> str:
    """Render a default value, collapsing long/complex ones to '…'.

    Keeps the signal of simple defaults (``True``, ``None``, ``40``, ``"md"``)
    while not letting things like ``typer.Option(..., help="…")`` blow up the
    signature line.
    """
    rendered = _expr(node)
    if len(rendered) > _DEFAULT_MAX:
        return "…"
    return rendered


def _arg(arg: ast.arg) -> str:
    if arg.annotation is not None:
        return f"{arg.arg}: {_expr(arg.annotation)}"
    return arg.arg


def _docstring(node: ast.AST) -> str:
    try:
        doc = ast.get_docstring(node, clean=True)  # type: ignore[arg-type]
    except TypeError:
        return ""
    if not doc:
        return ""
    return doc.strip().splitlines()[0].strip()


def _expr(node: ast.AST | None) -> str:
    """Render an expression back to compact source for signatures/decorators."""
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except (AttributeError, ValueError):  # pragma: no cover - very old/edge
        return "..."
