"""Multi-language extraction via tree-sitter.

Uses ``tree-sitter-language-pack`` (prebuilt wheels — no compiler needed) and a
deliberately query-free traversal: tree-sitter's query *capture* API has
changed shape several times across versions, so instead we walk the syntax tree
directly and classify nodes by type using a per-language spec table. The only
API surface we depend on is rock-stable: ``.type``, ``.named_children``,
``.child_by_field_name``, and ``.text``.

The traversal sees *through* wrapper nodes (export statements, decorators) and
descends into class bodies for methods, but never into function bodies — so it
finds the public shape without ever reading an implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..model import Symbol

# Extension -> language-pack language name. This is skeletree's advertised v1
# language surface. Python is intentionally absent — python_ast handles it with
# zero dependencies and richer output.
EXTENSION_LANGUAGE: dict[str, str] = {
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".mts": "typescript",
    ".cts": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
}


@dataclass(frozen=True)
class LangSpec:
    """How to recognize declarations in one language's syntax tree."""

    # node type -> our Symbol.kind
    classes: dict[str, str] = field(default_factory=dict)
    functions: dict[str, str] = field(default_factory=dict)
    simple: dict[str, str] = field(default_factory=dict)  # const/type/enum etc.
    # wrapper nodes to look *through* without recording them
    transparent: frozenset[str] = frozenset()
    # field names to try when locating a return-type node
    return_fields: tuple[str, ...] = ("return_type", "result", "type")


_JSTS_COMMON = dict(
    classes={"class_declaration": "class", "abstract_class_declaration": "class"},
    functions={
        "function_declaration": "function",
        "generator_function_declaration": "function",
        "method_definition": "method",
        "function_signature": "function",
        "method_signature": "method",
        "public_field_definition": "field",
    },
    simple={
        "interface_declaration": "interface",
        "type_alias_declaration": "type",
        "enum_declaration": "enum",
    },
    transparent=frozenset(
        {"export_statement", "decorator", "ambient_declaration"}
    ),
)

SPECS: dict[str, LangSpec] = {
    "javascript": LangSpec(
        classes={"class_declaration": "class"},
        functions={
            "function_declaration": "function",
            "generator_function_declaration": "function",
            "method_definition": "method",
        },
        transparent=frozenset({"export_statement", "decorator"}),
    ),
    "typescript": LangSpec(**_JSTS_COMMON),
    "tsx": LangSpec(**_JSTS_COMMON),
    "go": LangSpec(
        functions={
            "function_declaration": "function",
            "method_declaration": "method",
        },
        simple={"type_declaration": "type", "const_declaration": "const"},
        return_fields=("result", "return_type"),
    ),
    "rust": LangSpec(
        classes={"impl_item": "impl", "trait_item": "trait"},
        functions={"function_item": "function"},
        simple={
            "struct_item": "struct",
            "enum_item": "enum",
            "const_item": "const",
            "static_item": "static",
            "type_item": "type",
        },
        transparent=frozenset({"mod_item", "declaration_list", "visibility_modifier"}),
    ),
    "java": LangSpec(
        classes={
            "class_declaration": "class",
            "interface_declaration": "interface",
            "enum_declaration": "enum",
            "record_declaration": "record",
        },
        functions={
            "method_declaration": "method",
            "constructor_declaration": "method",
        },
        transparent=frozenset({"class_body", "interface_body", "enum_body"}),
    ),
    "ruby": LangSpec(
        classes={"class": "class", "module": "module"},
        functions={"method": "method", "singleton_method": "method"},
    ),
    "c": LangSpec(
        functions={"function_definition": "function"},
        simple={"struct_specifier": "struct", "enum_specifier": "enum"},
        transparent=frozenset({"declaration", "linkage_specification"}),
    ),
    "cpp": LangSpec(
        classes={"class_specifier": "class", "struct_specifier": "struct"},
        functions={"function_definition": "function"},
        simple={"enum_specifier": "enum"},
        transparent=frozenset(
            {"declaration", "template_declaration", "linkage_specification", "field_declaration_list"}
        ),
    ),
}

# Body field names that hold class/struct members, per node type.
_BODY_FIELDS = ("body", "declaration_list")

# Node types representing a parameter list (used as a C/C++ fallback when the
# function node has no "parameters" field — the list is nested in a declarator).
_PARAM_TYPES = frozenset({"parameter_list", "parameters", "formal_parameters"})
# Body-ish nodes we never search into when hunting for a parameter list.
_BODY_TYPES = frozenset({"compound_statement", "block", "function_body"})


_parser_cache: dict[str, object] = {}
_AVAILABLE: bool | None = None


def is_available() -> bool:
    """Whether the tree-sitter stack imported. Cached; safe to call often."""
    global _AVAILABLE
    if _AVAILABLE is None:
        try:
            import tree_sitter  # noqa: F401
            import tree_sitter_language_pack  # noqa: F401

            _AVAILABLE = True
        except ImportError:
            _AVAILABLE = False
    return _AVAILABLE


def language_for_extension(ext: str) -> str | None:
    return EXTENSION_LANGUAGE.get(ext.lower())


def extract(source: str, language: str) -> list[Symbol]:
    """Extract symbols for one of the tree-sitter languages.

    Returns [] (rather than raising) for unknown languages, unavailable
    bindings, or unparseable input — the caller lists such files path-only.
    """
    spec = SPECS.get(language)
    if spec is None or not is_available():
        return []
    parser = _get_parser(language)
    if parser is None:
        return []
    try:
        tree = parser.parse(source.encode("utf-8"))
    except Exception:  # pragma: no cover - parser robustness backstop
        return []
    return _collect(tree.root_node, spec)


def _get_parser(language: str):
    """Build a *standard* tree_sitter.Parser for the language.

    We deliberately use ``tree_sitter.Parser(get_language(...))`` rather than
    language-pack's ``get_parser()``: the latter can return a bundled parser
    whose Node API differs (``kind`` vs ``type``, no ``.text``). The standard
    binding's API is what this module's traversal targets, and it's stable.
    """
    if language not in _parser_cache:
        try:
            from tree_sitter import Parser
            from tree_sitter_language_pack import get_language

            lang = get_language(language)
            try:
                parser = Parser(lang)
            except TypeError:  # pragma: no cover - older binding
                parser = Parser()
                parser.language = lang
            _parser_cache[language] = parser
        except Exception:  # pragma: no cover - missing grammar/binding
            _parser_cache[language] = None
    return _parser_cache[language]


def _collect(node, spec: LangSpec) -> list[Symbol]:
    """Walk a node's named children, classifying declarations.

    Descends through ``transparent`` wrappers and into class bodies, but never
    into function bodies (we simply don't recurse on function nodes).
    """
    out: list[Symbol] = []
    for child in node.named_children:
        ntype = child.type
        if ntype in spec.classes:
            out.append(_make_container(child, spec, spec.classes[ntype]))
        elif ntype in spec.functions:
            out.append(_make_function(child, spec, spec.functions[ntype]))
        elif ntype in spec.simple:
            out.extend(_make_simple(child, spec.simple[ntype]))
        elif ntype in spec.transparent:
            out.extend(_collect(child, spec))
    return out


def _make_container(node, spec: LangSpec, kind: str) -> Symbol:
    name = _name_of(node)
    body = _body_of(node)
    children = _collect(body, spec) if body is not None else []
    return Symbol(
        kind=kind,
        name=name or "<anonymous>",
        signature=_heritage(node),
        lineno=node.start_point[0] + 1,
        children=children,
    )


def _make_function(node, spec: LangSpec, kind: str) -> Symbol:
    name = _name_of(node)
    params = node.child_by_field_name("parameters")
    if params is None:  # C/C++: the list lives inside the declarator subtree
        params = _find_descendant(node, _PARAM_TYPES, stop=_BODY_TYPES)
    sig = _squash(_text(params)) if params is not None else "()"
    ret = None
    for fname in spec.return_fields:
        ret = node.child_by_field_name(fname)
        if ret is not None:
            break
    if ret is not None:
        ret_text = _squash(_text(ret)).lstrip(":-> ").strip()
        if ret_text:
            sig += f" -> {ret_text}"
    return Symbol(
        kind=kind,
        name=name or "<anonymous>",
        signature=sig,
        lineno=node.start_point[0] + 1,
    )


def _make_simple(node, kind: str) -> list[Symbol]:
    """One declaration node may carry several names (Go ``const (...)`` blocks,
    ``type`` specs). Emit a symbol per name; fall back to the node's own name."""
    name = _name_of(node)
    if name:
        return [Symbol(kind=kind, name=name, lineno=node.start_point[0] + 1)]
    # Dig into *_spec children (Go type/const/var declarations).
    out: list[Symbol] = []
    for child in node.named_children:
        if child.type.endswith("_spec"):
            spec_name = _name_of(child)
            if spec_name:
                out.append(Symbol(kind=kind, name=spec_name, lineno=child.start_point[0] + 1))
    return out


def _name_of(node) -> str:
    named = node.child_by_field_name("name")
    if named is not None:
        return _text(named)
    declarator = node.child_by_field_name("declarator")
    if declarator is not None:
        # C/C++: dig for the identifier inside the (function_)declarator.
        ident = _find_identifier(declarator)
        if ident:
            return ident
    # Last resort: first identifier-ish named child.
    for child in node.named_children:
        if "identifier" in child.type:
            return _text(child)
    return ""


def _find_identifier(node) -> str:
    if "identifier" in node.type:
        return _text(node)
    for child in node.named_children:
        found = _find_identifier(child)
        if found:
            return found
    return ""


def _find_descendant(node, types: frozenset[str], *, stop: frozenset[str]):
    """First descendant whose type is in ``types``, not descending into ``stop``."""
    for child in node.named_children:
        if child.type in types:
            return child
        if child.type in stop:
            continue
        found = _find_descendant(child, types, stop=stop)
        if found is not None:
            return found
    return None


def _body_of(node):
    for fname in _BODY_FIELDS:
        body = node.child_by_field_name(fname)
        if body is not None:
            return body
    # Fallback: a child whose type ends in "body" or "declaration_list".
    for child in node.named_children:
        if child.type.endswith("body") or child.type == "declaration_list":
            return child
    return None


def _heritage(node) -> str:
    """Best-effort superclass / generics text for a container, compacted."""
    for fname in ("superclass", "type_parameters", "bases", "trait"):
        n = node.child_by_field_name(fname)
        if n is not None:
            return _squash(_text(n))
    return ""


def _text(node) -> str:
    try:
        return node.text.decode("utf-8", errors="replace")
    except (AttributeError, UnicodeError):  # pragma: no cover
        return ""


def _squash(text: str) -> str:
    """Collapse whitespace/newlines in a signature to a single clean line."""
    return " ".join(text.split())
