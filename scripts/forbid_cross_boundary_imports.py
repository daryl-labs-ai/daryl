#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
forbid_cross_boundary_imports.py — ADR-HEXASHARD-0001 enforcement lint

HexaShard is an independent runtime temporarily co-located in this repository.
Co-location must not become accidental coupling, because the cost of extracting
HexaShard later is set almost entirely by whether this invariant held.

Forbidden in both directions:

    hexashard, hexashard_adapter   -X->   dsm, prl
    dsm, prl                       -X->   hexashard, hexashard_adapter

Detection: AST parsing of production code under src/. Comments, docstrings and
string mentions are ignored — only real imports count.

Deliberate differences from scripts/forbid_storage_access.py, which this follows
in shape:

  - No whitelist and no tracked-debt list. This is a hard boundary, not a
    migration. An exception is a repository-architecture decision, so it belongs
    in a new ADR, not in a list at the top of a lint.

  - `if TYPE_CHECKING:` imports are NOT exempt. A type-only import still means
    the package cannot be moved to its own repository without carrying the other
    one along, which is exactly the coupling this guard exists to prevent.

Limitations (documented, not bugs):
  - Dynamic imports (importlib.import_module("dsm...")) are NOT detected. Must
    be caught by code review.
  - Only production trees under src/ are scanned. Tests may legitimately import
    both sides in order to assert things about them — including this guard's own
    test.

Exit codes:
  - 0: no violation
  - 1: one or more violations
  - 2: internal error

Usage:
  python scripts/forbid_cross_boundary_imports.py
  python scripts/forbid_cross_boundary_imports.py --root /path/to/repo
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# The boundary
# ---------------------------------------------------------------------------

#: The two sides. Each maps a source tree to the top-level packages it may not
#: import. Both directions are listed explicitly rather than derived, so the
#: rule reads the same way it is stated in the ADR.
BOUNDARY: dict[str, frozenset[str]] = {
    "src/hexashard": frozenset({"dsm", "prl"}),
    "src/hexashard_adapter": frozenset({"dsm", "prl"}),
    "src/dsm": frozenset({"hexashard", "hexashard_adapter"}),
    "src/prl": frozenset({"hexashard", "hexashard_adapter"}),
}

ADR = "ADR-HEXASHARD-0001"

FAIL_EPILOGUE = f"""\
HexaShard is an independent runtime temporarily co-located in DARYL, and DSM/PRL
must not depend on it either. See docs/architecture/{ADR}-repository-boundary.md.

A production import across this boundary is not a code-review comment — it is one
of the documented triggers to re-open the repository-boundary decision. Per
{ADR}, the import does not get merged first:

  1. Decide whether the dependency is genuinely required.
  2. If it is, re-evaluate whether HexaShard should move to
     daryl-labs-ai/daryl-hexashard before the coupling lands.
  3. Record the outcome in a new ADR that supersedes or amends {ADR}.

There is deliberately no allowlist and no per-line escape hatch. Adding one
would let a convenience import decide the repository architecture silently,
which is the exact failure this guard exists to prevent.
"""


@dataclass(frozen=True)
class Violation:
    file: str
    line: int
    col: int
    source: str
    importer: str
    imported: str


def format_violation(v: Violation) -> str:
    return (
        f"[FORBID_CROSS_BOUNDARY] {v.file}:{v.line}:{v.col}\n"
        f"  -> {v.source}\n"
        f"  reason: {v.importer} must not import {v.imported}\n"
    )


# ---------------------------------------------------------------------------
# AST visitor
# ---------------------------------------------------------------------------

class _ImportVisitor(ast.NodeVisitor):
    """Collect imports of forbidden top-level packages.

    TYPE_CHECKING blocks are intentionally *not* skipped — see module docstring.
    """

    def __init__(self, file_path: str, side: str, forbidden: frozenset[str],
                 source_lines: list[str]) -> None:
        self.file_path = file_path
        self.side = side
        self.forbidden = forbidden
        self.source_lines = source_lines
        self.violations: list[Violation] = []

    def _src(self, lineno: int) -> str:
        if 1 <= lineno <= len(self.source_lines):
            return self.source_lines[lineno - 1].strip()
        return ""

    def _flag(self, node: ast.AST, imported: str) -> None:
        self.violations.append(Violation(
            file=self.file_path,
            line=getattr(node, "lineno", 0),
            col=getattr(node, "col_offset", 0),
            source=self._src(getattr(node, "lineno", 0)),
            importer=self.side,
            imported=imported,
        ))

    @staticmethod
    def _root(dotted: str) -> str:
        return dotted.split(".", 1)[0]

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            root = self._root(alias.name)
            if root in self.forbidden:
                self._flag(node, root)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        # Relative imports stay inside their own package by construction and
        # cannot reach across the boundary.
        if node.level == 0:
            module = node.module or ""
            root = self._root(module)
            if root in self.forbidden:
                self._flag(node, root)
        self.generic_visit(node)


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------

EXCLUDED_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__",
                 ".tox", ".pytest_cache", "dist", "build", ".mypy_cache"}


def side_for(rel_path: str) -> tuple[str, frozenset[str]] | None:
    """Which side of the boundary a repo-relative path sits on, if any."""
    normalized = rel_path.replace("\\", "/")
    for prefix, forbidden in BOUNDARY.items():
        if normalized == prefix or normalized.startswith(prefix + "/"):
            return prefix, forbidden
    return None


def scan_file(path: Path, repo_root: Path) -> list[Violation]:
    rel = path.relative_to(repo_root).as_posix()
    side = side_for(rel)
    if side is None:
        return []
    prefix, forbidden = side
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise RuntimeError(f"Cannot read {rel}: {e}") from e
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as e:
        print(f"[WARN] {rel}: syntax error, skipping ({e})", file=sys.stderr)
        return []
    visitor = _ImportVisitor(rel, prefix, forbidden, source.splitlines())
    visitor.visit(tree)
    return visitor.violations


def iter_python_files(repo_root: Path):
    src = repo_root / "src"
    if not src.is_dir():
        return
    for path in src.rglob("*.py"):
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        yield path


def scan(repo_root: Path) -> list[Violation]:
    violations: list[Violation] = []
    for path in iter_python_files(repo_root):
        violations.extend(scan_file(path, repo_root))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"{ADR} enforcement lint")
    parser.add_argument(
        "--root", type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root (default: parent of scripts/)",
    )
    args = parser.parse_args(argv)

    repo_root = args.root.resolve()
    if not repo_root.is_dir():
        print(f"ERROR: --root {repo_root} is not a directory", file=sys.stderr)
        return 2

    scanned = sum(1 for _ in iter_python_files(repo_root))
    try:
        violations = scan(repo_root)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    if not violations:
        sides = ", ".join(sorted(BOUNDARY))
        print(f"OK: {scanned} files scanned under src/, no cross-boundary "
              f"imports ({sides}).")
        return 0

    print(f"FAIL: {len(violations)} cross-boundary import(s):\n", file=sys.stderr)
    for v in violations:
        print(format_violation(v), file=sys.stderr)
    print(FAIL_EPILOGUE, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
