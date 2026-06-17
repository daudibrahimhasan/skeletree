"""Python (stdlib ast) extractor tests."""

from __future__ import annotations

from skeletree.extractors import python_ast


def _names(symbols):
    return [s.name for s in symbols]


def test_extracts_functions_with_signatures():
    src = "def add(a: int, b: int = 1) -> int:\n    return a + b\n"
    (sym,) = python_ast.extract(src)
    assert sym.kind == "function"
    assert sym.name == "add"
    assert sym.signature == "(a: int, b: int=1) -> int"


def test_async_function_marked_in_signature():
    src = "async def fetch(url: str) -> bytes:\n    ...\n"
    (sym,) = python_ast.extract(src)
    assert sym.signature.startswith("async ")


def test_class_with_methods_and_bases():
    src = (
        "class Server(Base, mixin=True):\n"
        '    """An HTTP server."""\n'
        "    def start(self, port: int) -> None: ...\n"
        "    async def stop(self): ...\n"
    )
    (cls,) = python_ast.extract(src)
    assert cls.kind == "class"
    assert cls.name == "Server"
    assert "Base" in cls.signature and "mixin=True" in cls.signature
    assert cls.doc == "An HTTP server."
    assert _names(cls.children) == ["start", "stop"]
    assert cls.children[1].signature.startswith("async ")


def test_decorators_captured():
    src = "import functools\n@functools.cache\ndef f(): ...\n"
    (sym,) = python_ast.extract(src)
    assert sym.decorators == ["functools.cache"]


def test_upper_case_constants_only():
    src = "MAX = 10\nlowercase = 5\nVERSION: str = '1.0'\n"
    consts = python_ast.extract(src)
    names = _names(consts)
    assert "MAX" in names
    assert "VERSION" in names
    assert "lowercase" not in names


def test_long_default_collapsed():
    src = "def f(x=some_factory(1, 2, 3, 4, 5, 6, 7, 8, 9)): ...\n"
    (sym,) = python_ast.extract(src)
    assert "=…" in sym.signature
    assert "some_factory" not in sym.signature


def test_varargs_and_kwargs():
    src = "def f(a, /, b, *args, c=1, **kw): ...\n"
    (sym,) = python_ast.extract(src)
    assert sym.signature == "(a, /, b, *args, c=1, **kw)"


def test_syntax_error_returns_empty():
    assert python_ast.extract("def (:::\n") == []


def test_no_bodies_leak():
    src = "def secret():\n    password = 'hunter2'\n    return password\n"
    (sym,) = python_ast.extract(src)
    assert "hunter2" not in sym.signature
    assert not sym.children
