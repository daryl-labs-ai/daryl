#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
forbid_storage_access.py — ADR-0001 enforcement lint

Enforces that `dsm.core.storage.Storage` is imported ONLY from whitelisted
locations. Outside the whitelist, the Read Relay (RR) is the only allowed
read path per ADR-0001.

Whitelist:
  - src/dsm/core/
  - src/dsm/rr/
  - tests/
  - benchmarks/
  - demo/
  - scripts/

Detection: AST parsing of every .py file outside the whitelist.
Flags:
  - `from dsm.core.storage import Storage` (any alias)
  - `from dsm.core import storage` (indirect access path)
  - `import dsm.core.storage [as alias]`

Limitations (documented, not bugs):
  - Dynamic imports (importlib.import_module("dsm.core.storage")) are NOT
    detected. Must be caught by code review.
  - Receiving a Storage instance via function parameter is NOT flagged —
    the lint forbids *importing*, not *using*.

Exit codes:
  - 0: no violation
  - 1: one or more violations
  - 2: internal error

Usage:
  python scripts/forbid_storage_access.py
  python scripts/forbid_storage_access.py --root /path/to/repo
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

WHITELIST_PREFIXES = (
    "src/dsm/core/",
    "src/dsm/rr/",
    "tests/",
    "benchmarks/",
    "demo/",
    "scripts/",
)

# Files grandfathered from the rule. Each entry is a repo-relative path that
# CURRENTLY imports dsm.core.storage.Storage directly. Every migration in
# Phase 7b must REMOVE a line from this list when it eliminates the direct
# import from the corresponding file.
#
# A file listed here that no longer violates is ALSO a failure — the list
# must stay in sync with reality.
#
# Intentionally empty for now. Will be populated with the violations
# discovered by running the lint on main.
KNOWN_VIOLATIONS: frozenset[str] = frozenset()

FORBIDDEN_MODULE = "dsm.core.storage"
FORBIDDEN_SYMBOL = "Storage"
PARENT_MODULE = "dsm.core"


# ---------------------------------------------------------------------------
# Violation reporting
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Violation:
    file: str
    line: int
    col: int
    source: str
    reason: str


def format_violation(v: Violation) -> str:
    return (
        f"[FORBID_STORAGE_ACCESS] {v.file}:{v.line}:{v.col}\n"
        f"  -> {v.source}\n"
        f"  reason: {v.reason}\n"
    )


FAIL_EPILOGUE = """\
RR (Read Relay) is the ONLY allowed read path per ADR-0001.
Allowed locations for direct Storage access:
  - src/dsm/core/
  - src/dsm/rr/
  - tests/
  - benchmarks/
  - demo/
  - scripts/

Fix: use RRQueryEngine (src/dsm/rr/query/) instead of direct Storage access.
If this file has a legitimate reason to bypass RR, add its path prefix to
WHITELIST_PREFIXES in scripts/forbid_storage_access.py AND document the
reason in the commit message. No per-line escape hatches are supported.
"""


# ---------------------------------------------------------------------------
# AST visitor
# ---------------------------------------------------------------------------

class _ImportVisitor(ast.NodeVisitor):
    def __init__(self, file_path: str, source_lines: list[str]):
        self.file_path = file_path
        self.source_lines = source_lines
        self.violations: list[Violation] = []

    def _src(self, lineno: int) -> str:
        if 1 <= lineno <= len(self.source_lines):
            return self.source_lines[lineno - 1].strip()
        return ""

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        if module == FORBIDDEN_MODULE:
            for alias in node.names:
                if alias.name == FORBIDDEN_SYMBOL:
                    self.violations.append(Violation(
                        file=self.file_path,
                        line=node.lineno,
                        col=node.col_offset,
                        source=self._src(node.lineno),
                        reason=f"direct import of {FORBIDDEN_MODULE}.{FORBIDDEN_SYMBOL}",
                    ))
        elif module == PARENT_MODULE:
            for alias in node.names:
                if alias.name == "storage":
                    self.violations.append(Violation(
                        file=self.file_path,
                        line=node.lineno,
                        col=node.col_offset,
                        source=self._src(node.lineno),
                        reason=f"indirect access via `from {PARENT_MODULE} import storage`",
                    ))
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name == FORBIDDEN_MODULE:
                self.violations.append(Violation(
                    file=self.file_path,
                    line=node.lineno,
                    col=node.col_offset,
                    source=self._src(node.lineno),
                    reason=f"import of {FORBIDDEN_MODULE} module",
                ))
        self.generic_visit(node)


# ---------------------------------------------------------------------------
# Core scanning
# ---------------------------------------------------------------------------

def is_whitelisted(rel_path: str) -> bool:
    normalized = rel_path.replace("\\", "/")
    return any(normalized.startswith(prefix) for prefix in WHITELIST_PREFIXES)


def is_known_violation(rel_path: str) -> bool:
    normalized = rel_path.replace("\\", "/")
    return normalized in KNOWN_VIOLATIONS


def scan_file(path: Path, repo_root: Path) -> list[Violation]:
    rel = path.relative_to(repo_root).as_posix()
    if is_whitelisted(rel):
        return []
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise RuntimeError(f"Cannot read {rel}: {e}") from e
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as e:
        print(f"[WARN] {rel}: syntax error, skipping ({e})", file=sys.stderr)
        return []
    visitor = _ImportVisitor(rel, source.splitlines())
    visitor.visit(tree)
    return visitor.violations


def iter_python_files(repo_root: Path):
    EXCLUDED_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__",
                     ".tox", ".pytest_cache", "dist", "build", ".mypy_cache"}
    for path in repo_root.rglob("*.py"):
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        yield path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ADR-0001 enforcement lint")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root (default: parent of scripts/)",
    )
    args = parser.parse_args(argv)

    repo_root = args.root.resolve()
    if not repo_root.is_dir():
        print(f"ERROR: --root {repo_root} is not a directory", file=sys.stderr)
        return 2

    active_violations: list[Violation] = []
    stale_known: list[str] = []
    files_with_violations: set[str] = set()
    scanned = 0

    try:
        for path in iter_python_files(repo_root):
            scanned += 1
            violations = scan_file(path, repo_root)
            if not violations:
                continue
            rel = path.relative_to(repo_root).as_posix()
            files_with_violations.add(rel)
            if is_known_violation(rel):
                continue
            active_violations.extend(violations)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    for known in KNOWN_VIOLATIONS:
        if known not in files_with_violations:
            stale_known.append(known)

    if not active_violations and not stale_known:
        print(f"OK: {scanned} files scanned, no violations "
              f"(grandfathered: {len(KNOWN_VIOLATIONS)}).")
        return 0

    if active_violations:
        print(f"FAIL: {len(active_violations)} violation(s) "
              f"in non-grandfathered files:\n", file=sys.stderr)
        for v in active_violations:
            print(format_violation(v), file=sys.stderr)
        print(FAIL_EPILOGUE, file=sys.stderr)

    if stale_known:
        print(f"FAIL: {len(stale_known)} file(s) listed in KNOWN_VIOLATIONS "
              f"but no longer violate — remove them from the list:",
              file=sys.stderr)
        for f in sorted(stale_known):
            print(f"  - {f}", file=sys.stderr)
        print("", file=sys.stderr)

    return 1


if __name__ == "__main__":
    sys.exit(main())
