"""Multi-language tree-sitter extractor tests.

Skipped automatically if tree-sitter-language-pack isn't installed, so the core
suite still runs in a minimal environment.
"""

from __future__ import annotations

import pytest

from skeletree.extractors import treesitter

pytestmark = pytest.mark.skipif(
    not treesitter.is_available(), reason="tree-sitter-language-pack not installed"
)


def _flat_names(symbols):
    out = []
    for s in symbols:
        out.append(s.name)
        out.extend(c.name for c in s.children)
    return out


def test_javascript_functions_and_classes():
    src = """
export function greet(name) { return `hi ${name}`; }
class Widget {
  render() {}
  static make() {}
}
"""
    syms = treesitter.extract(src, "javascript")
    names = _flat_names(syms)
    assert "greet" in names
    assert "Widget" in names
    assert "render" in names


def test_typescript_interface_and_typed_function():
    src = """
export interface User { id: number; name: string; }
export function load(id: number): User { return null as any; }
"""
    syms = treesitter.extract(src, "typescript")
    by_kind = {s.kind: s for s in syms}
    assert "interface" in by_kind
    fn = next(s for s in syms if s.name == "load")
    assert "number" in fn.signature
    assert "User" in fn.signature  # return type captured


def test_go_funcs_methods_and_types():
    src = """
package main

type Server struct { Port int }

func New() *Server { return &Server{} }

func (s *Server) Start(port int) error { return nil }
"""
    syms = treesitter.extract(src, "go")
    names = [s.name for s in syms]
    assert "New" in names
    assert "Start" in names
    assert "Server" in names


def test_rust_struct_and_impl():
    src = """
pub struct Point { x: i32, y: i32 }

impl Point {
    pub fn new(x: i32, y: i32) -> Point { Point { x, y } }
}

pub fn area() -> i32 { 0 }
"""
    syms = treesitter.extract(src, "rust")
    names = _flat_names(syms)
    assert "Point" in names
    assert "new" in names
    assert "area" in names


def test_java_class_methods():
    src = """
public class Calculator {
    public int add(int a, int b) { return a + b; }
    private void reset() {}
}
"""
    syms = treesitter.extract(src, "java")
    cls = next(s for s in syms if s.name == "Calculator")
    method_names = [c.name for c in cls.children]
    assert "add" in method_names
    assert "reset" in method_names


def test_ruby_class_and_methods():
    src = """
class Greeter
  def initialize(name)
    @name = name
  end

  def greet
    "hi"
  end
end
"""
    syms = treesitter.extract(src, "ruby")
    cls = next(s for s in syms if s.name == "Greeter")
    method_names = [c.name for c in cls.children]
    assert "greet" in method_names


def test_no_function_bodies_leak():
    src = "function f() { const secret = 'hunter2'; return secret; }"
    syms = treesitter.extract(src, "javascript")
    assert all("hunter2" not in s.signature for s in syms)


def test_unparseable_returns_empty():
    # Garbage still shouldn't raise.
    assert isinstance(treesitter.extract("@@@##$$", "go"), list)
