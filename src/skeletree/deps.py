"""Dependency and description detection from project manifests.

Reads the most common package manifests (pyproject.toml, package.json,
Cargo.toml, go.mod, requirements.txt) and returns compact dep name lists
— no version pins, to stay token-cheap.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]

from .model import LibraryDeps


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def detect(root: Path) -> list[LibraryDeps]:
    """Return all dependency sets found in the repo root."""
    results: list[LibraryDeps] = []
    _try_pyproject(root, results)
    if not any(d.ecosystem == "python" for d in results):
        _try_requirements(root, results)
    _try_package_json(root, results)
    _try_cargo(root, results)
    _try_gomod(root, results)
    return results


def detect_description(root: Path) -> str:
    """Return a one-line project description, or '' if none found."""
    if tomllib is not None:
        desc = _desc_from_pyproject(root) or _desc_from_cargo(root)
        if desc:
            return desc

    desc = _desc_from_package_json(root)
    if desc:
        return desc

    return _desc_from_readme(root)


# ---------------------------------------------------------------------------
# Version-spec stripper
# ---------------------------------------------------------------------------

_VER_RE = re.compile(r"[><=!~\[;@\s].*")


def _pkg_name(spec: str) -> str:
    return _VER_RE.sub("", spec).strip().lower()


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------

def _try_pyproject(root: Path, out: list[LibraryDeps]) -> None:
    if tomllib is None:
        return
    path = root / "pyproject.toml"
    if not path.is_file():
        return
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return

    runtime: list[str] = []
    dev: list[str] = []

    # PEP 621
    project = data.get("project", {})
    for spec in project.get("dependencies", []):
        name = _pkg_name(spec)
        if name:
            runtime.append(name)
    for extras in project.get("optional-dependencies", {}).values():
        for spec in extras:
            name = _pkg_name(spec)
            if name and name not in runtime and name not in dev:
                dev.append(name)

    # Poetry
    poetry = data.get("tool", {}).get("poetry", {})
    for name in poetry.get("dependencies", {}):
        if name.lower() == "python":
            continue
        n = name.lower()
        if n not in runtime:
            runtime.append(n)
    for name in poetry.get("dev-dependencies", {}):
        n = name.lower()
        if n not in dev:
            dev.append(n)
    for group in poetry.get("group", {}).values():
        for name in group.get("dependencies", {}):
            n = name.lower()
            if n not in dev:
                dev.append(n)

    if runtime or dev:
        out.append(LibraryDeps(ecosystem="python", runtime=runtime, dev=dev))


def _try_requirements(root: Path, out: list[LibraryDeps]) -> None:
    runtime: list[str] = []
    for fname in ("requirements.txt", "requirements/base.txt", "requirements/prod.txt"):
        p = root / fname
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.split("#")[0].strip()
            if not line or line.startswith("-"):
                continue
            name = _pkg_name(line)
            if name and name not in runtime:
                runtime.append(name)

    dev: list[str] = []
    for fname in ("requirements-dev.txt", "requirements/dev.txt", "dev-requirements.txt"):
        p = root / fname
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.split("#")[0].strip()
            if not line or line.startswith("-"):
                continue
            name = _pkg_name(line)
            if name and name not in dev:
                dev.append(name)

    if runtime or dev:
        out.append(LibraryDeps(ecosystem="python", runtime=runtime, dev=dev))


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

def _try_package_json(root: Path, out: list[LibraryDeps]) -> None:
    path = root / "package.json"
    if not path.is_file():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    runtime = list(data.get("dependencies", {}).keys())
    dev = list(data.get("devDependencies", {}).keys())
    if runtime or dev:
        out.append(LibraryDeps(ecosystem="node", runtime=runtime, dev=dev))


# ---------------------------------------------------------------------------
# Rust
# ---------------------------------------------------------------------------

def _try_cargo(root: Path, out: list[LibraryDeps]) -> None:
    if tomllib is None:
        return
    path = root / "Cargo.toml"
    if not path.is_file():
        return
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    runtime = list(data.get("dependencies", {}).keys())
    dev = list(data.get("dev-dependencies", {}).keys())
    if runtime or dev:
        out.append(LibraryDeps(ecosystem="rust", runtime=runtime, dev=dev))


# ---------------------------------------------------------------------------
# Go
# ---------------------------------------------------------------------------

_GO_REQ_RE = re.compile(r"^\s+([\w.\-/]+)\sv[\w.\-+]+")


def _try_gomod(root: Path, out: list[LibraryDeps]) -> None:
    path = root / "go.mod"
    if not path.is_file():
        return
    runtime: list[str] = []
    in_require = False
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if stripped.startswith("require ("):
            in_require = True
            continue
        if in_require:
            if stripped == ")":
                in_require = False
                continue
            m = _GO_REQ_RE.match(line)
            if m:
                parts = m.group(1).split("/")
                name = "/".join(parts[-2:]) if len(parts) >= 2 else parts[-1]
                if name not in runtime:
                    runtime.append(name)
        elif stripped.startswith("require "):
            rest = stripped[len("require "):].strip()
            m = re.match(r"([\w.\-/]+)\sv", rest)
            if m:
                parts = m.group(1).split("/")
                name = "/".join(parts[-2:]) if len(parts) >= 2 else parts[-1]
                if name not in runtime:
                    runtime.append(name)
    if runtime:
        out.append(LibraryDeps(ecosystem="go", runtime=runtime))


# ---------------------------------------------------------------------------
# Description helpers
# ---------------------------------------------------------------------------

def _desc_from_pyproject(root: Path) -> str:
    if tomllib is None:
        return ""
    path = root / "pyproject.toml"
    if not path.is_file():
        return ""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    desc = data.get("project", {}).get("description", "")
    if not desc:
        desc = data.get("tool", {}).get("poetry", {}).get("description", "")
    return str(desc).strip() if desc else ""


def _desc_from_cargo(root: Path) -> str:
    if tomllib is None:
        return ""
    path = root / "Cargo.toml"
    if not path.is_file():
        return ""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    desc = data.get("package", {}).get("description", "")
    return str(desc).strip() if desc else ""


def _desc_from_package_json(root: Path) -> str:
    path = root / "package.json"
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    desc = data.get("description", "")
    return str(desc).strip() if desc else ""


def _desc_from_readme(root: Path) -> str:
    for fname in ("README.md", "README.rst", "README.txt", "README"):
        p = root / fname
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line in text.splitlines():
            s = line.strip()
            if not s or s.startswith("#") or s.startswith("=") or s.startswith("-"):
                continue
            if s.startswith("[![") or s.startswith("<") or s.startswith("!"):
                continue
            return s[:120] + ("..." if len(s) > 120 else "")
    return ""
