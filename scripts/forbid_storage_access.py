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

# Files that legitimately construct Storage to WRITE entries.
# Per ADR-0001, RR is the only allowed READ path — but writers must still
# build Storage to append entries to shards. These files are not a debt;
# their presence is correct by design. The list is explicit (not a pattern)
# so that adding a new writer requires an architectural decision.
LEGITIMATE_WRITERS: frozenset[str] = frozenset({
    "src/dsm/__init__.py",
    "src/dsm/agent.py",
    "src/dsm/block_layer/manager.py",
    "src/dsm/cli.py",
    "src/dsm/cold_storage.py",
    "src/dsm/collective.py",
    "src/dsm/exchange.py",
    "src/dsm/identity/identity_guard.py",
    "src/dsm/identity/identity_manager.py",
    "src/dsm/identity/identity_registry.py",
    "src/dsm/identity/identity_replay.py",
    "src/dsm/lanes.py",
    "src/dsm/lifecycle.py",
    "src/dsm/orchestrator.py",
    "src/dsm/policy_adapter.py",
    "src/dsm/sovereignty.py",
    "src/dsm/verify.py",
})

# Known READER files that currently bypass RR — tracked debt under active
# migration (ADR-0001 Phase 7b). Each entry is a file that READS Storage
# directly and should instead route through RRQueryEngine or equivalent.
#
# Workflow:
#   - A file is added here ONLY during the initial lint introduction. No new
#     entries should be added during normal development.
#   - A file is REMOVED from this set when its direct Storage read access
#     has been replaced by an RR-backed path.
#   - If a file listed here no longer violates (has no direct Storage import),
#     the lint FAILS and asks you to remove the stale entry. This keeps the
#     set synchronized with reality.
#
# The goal is to drain this set to frozenset() via Phase 7b migrations and
# subsequent cleanup.
KNOWN_READER_VIOLATIONS: frozenset[str] = frozenset({
    "src/dsm/context/builder.py",
    "src/dsm/provenance/builder.py",
    "src/dsm/recall/search.py",
    "src/dsm/session/session_graph.py",
    "src/dsm/session/session_index.py",
})


def is_legitimate_writer(rel_path: str) -> bool:
    """Check if a repo-relative path is a documented legitimate Storage writer."""
    normalized = rel_path.replace("\\", "/")
    return normalized in LEGITIMATE_WRITERS


def is_known_reader_violation(rel_path: str) -> bool:
    """Check if a repo-relative path is a tracked reader-bypass debt."""
    normalized = rel_path.replace("\\", "/")
    return normalized in KNOWN_READER_VIOLATIONS

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

If this is a legitimate WRITER (module that appends entries to shards):
  Add the path to LEGITIMATE_WRITERS in scripts/forbid_storage_access.py
  and document the reason in the commit message.

If this is a READER (should fetch data via RR):
  Replace the direct Storage import with RRQueryEngine or equivalent. See
  src/dsm/rr/query/ for the available read API.

No per-line escape hatches (# noqa: forbid-storage) are supported. Every
exception must be an explicit entry in LEGITIMATE_WRITERS (permanent) or
KNOWN_READER_VIOLATIONS (tracked debt, drains to empty via Phase 7b).
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

        # Relative imports: we can't fully resolve without the file's package
        # context, but we can flag the patterns that semantically equal an
        # import of dsm.core.storage.Storage regardless of how many `..` dots
        # are used. The key insight: for any relative import, the tail of
        # `module` after the implicit package prefix is what matters.
        if node.level > 0:
            # Case 1: from ..core.storage import Storage  (module == "core.storage")
            # Case 2: from ...parent.core.storage import Storage (module == "parent.core.storage")
            # We match any module path that ENDS in "core.storage".
            if module == "core.storage" or module.endswith(".core.storage"):
                for alias in node.names:
                    if alias.name == FORBIDDEN_SYMBOL:
                        self.violations.append(Violation(
                            file=self.file_path,
                            line=node.lineno,
                            col=node.col_offset,
                            source=self._src(node.lineno),
                            reason=f"relative import of {FORBIDDEN_MODULE}.{FORBIDDEN_SYMBOL} "
                                   f"(level={node.level}, module='{module}')",
                        ))

            # Case 3: from ..core import storage  (sub-module)
            # Case 4: from ..core import Storage  (re-exported class, bypass via core/__init__.py)
            elif module == "core" or module.endswith(".core"):
                for alias in node.names:
                    if alias.name == "storage":
                        self.violations.append(Violation(
                            file=self.file_path,
                            line=node.lineno,
                            col=node.col_offset,
                            source=self._src(node.lineno),
                            reason=f"relative indirect access: `from {module} import storage` "
                                   f"(level={node.level})",
                        ))
                    elif alias.name == FORBIDDEN_SYMBOL:
                        # Re-exported class bypass — core/__init__.py exports Storage
                        self.violations.append(Violation(
                            file=self.file_path,
                            line=node.lineno,
                            col=node.col_offset,
                            source=self._src(node.lineno),
                            reason=f"relative re-export bypass: `from {module} import Storage` "
                                   f"(level={node.level})",
                        ))

            self.generic_visit(node)
            return

        # Absolute imports (unchanged behavior)
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
                elif alias.name == FORBIDDEN_SYMBOL:
                    # Absolute re-export bypass
                    self.violations.append(Violation(
                        file=self.file_path,
                        line=node.lineno,
                        col=node.col_offset,
                        source=self._src(node.lineno),
                        reason=f"absolute re-export bypass: `from {PARENT_MODULE} import Storage`",
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
    stale_writers: list[str] = []
    stale_readers: list[str] = []
    files_with_violations: set[str] = set()
    all_scanned_rel: set[str] = set()
    scanned = 0

    try:
        for path in iter_python_files(repo_root):
            scanned += 1
            rel_this = path.relative_to(repo_root).as_posix()
            all_scanned_rel.add(rel_this)
            violations = scan_file(path, repo_root)
            if not violations:
                continue
            files_with_violations.add(rel_this)
            if is_legitimate_writer(rel_this):
                continue  # documented writer, OK
            if is_known_reader_violation(rel_this):
                continue  # tracked debt, OK for now
            active_violations.extend(violations)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    # Detect stale entries in either list (file EXISTS in the scan but no
    # longer violates). A file that isn't in the scanned tree at all is
    # out-of-scope, not stale — this matters for unit tests that run the
    # lint on minimal tmp_path repos, and for linting from a subdirectory.
    for w in LEGITIMATE_WRITERS:
        if w in all_scanned_rel and w not in files_with_violations:
            stale_writers.append(w)
    for r in KNOWN_READER_VIOLATIONS:
        if r in all_scanned_rel and r not in files_with_violations:
            stale_readers.append(r)

    if not active_violations and not stale_writers and not stale_readers:
        print(f"OK: {scanned} files scanned, no unauthorized violations "
              f"(legitimate writers: {len(LEGITIMATE_WRITERS)}, "
              f"tracked reader debt: {len(KNOWN_READER_VIOLATIONS)}).")
        return 0

    if active_violations:
        print(f"FAIL: {len(active_violations)} violation(s) "
              f"in non-grandfathered files:\n", file=sys.stderr)
        for v in active_violations:
            print(format_violation(v), file=sys.stderr)
        print(FAIL_EPILOGUE, file=sys.stderr)

    if stale_writers:
        print(f"FAIL: {len(stale_writers)} file(s) listed in LEGITIMATE_WRITERS "
              f"but no longer import Storage — remove from the list:",
              file=sys.stderr)
        for f in sorted(stale_writers):
            print(f"  - {f}", file=sys.stderr)
        print("", file=sys.stderr)

    if stale_readers:
        print(f"FAIL: {len(stale_readers)} file(s) listed in KNOWN_READER_VIOLATIONS "
              f"but no longer import Storage — migration complete, remove from the list:",
              file=sys.stderr)
        for f in sorted(stale_readers):
            print(f"  - {f}", file=sys.stderr)
        print("", file=sys.stderr)

    return 1


if __name__ == "__main__":
    sys.exit(main())
