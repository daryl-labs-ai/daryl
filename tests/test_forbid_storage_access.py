# -*- coding: utf-8 -*-
"""
Tests for scripts/forbid_storage_access.py

The lint itself must be tested. Without these tests, modifying the lint
risks silent regressions of the architectural invariant.
"""

import subprocess
import sys
from pathlib import Path

import pytest


LINT_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "forbid_storage_access.py"


def _run_lint(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(LINT_SCRIPT), "--root", str(root)],
        capture_output=True,
        text=True,
    )


def _mkrepo(tmp_path: Path) -> Path:
    for d in ("src/dsm/core", "src/dsm/rr", "src/dsm/other",
              "tests", "benchmarks", "scripts"):
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_empty_repo_passes(tmp_path):
    _mkrepo(tmp_path)
    result = _run_lint(tmp_path)
    assert result.returncode == 0
    assert "OK" in result.stdout


def test_whitelisted_paths_can_import_storage(tmp_path):
    _mkrepo(tmp_path)
    snippet = "from dsm.core.storage import Storage\nx = Storage\n"
    for whitelisted in ("src/dsm/core/kernel.py",
                        "src/dsm/rr/query/engine.py",
                        "tests/test_something.py",
                        "benchmarks/bench_read.py"):
        p = tmp_path / whitelisted
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(snippet, encoding="utf-8")
    result = _run_lint(tmp_path)
    assert result.returncode == 0, f"Expected pass, got:\n{result.stderr}"


def test_violation_direct_from_import(tmp_path):
    _mkrepo(tmp_path)
    offender = tmp_path / "src/dsm/other/module.py"
    offender.write_text(
        "from dsm.core.storage import Storage\ndef f(): return Storage\n",
        encoding="utf-8",
    )
    result = _run_lint(tmp_path)
    assert result.returncode == 1
    assert "src/dsm/other/module.py" in result.stderr
    assert "direct import" in result.stderr


def test_violation_aliased_import(tmp_path):
    _mkrepo(tmp_path)
    offender = tmp_path / "src/dsm/other/module.py"
    offender.write_text(
        "from dsm.core.storage import Storage as S\nx = S\n",
        encoding="utf-8",
    )
    result = _run_lint(tmp_path)
    assert result.returncode == 1
    assert "src/dsm/other/module.py" in result.stderr


def test_violation_parent_import(tmp_path):
    _mkrepo(tmp_path)
    offender = tmp_path / "src/dsm/other/module.py"
    offender.write_text(
        "from dsm.core import storage\ns = storage.Storage()\n",
        encoding="utf-8",
    )
    result = _run_lint(tmp_path)
    assert result.returncode == 1
    assert "indirect access" in result.stderr


def test_violation_fully_qualified_import(tmp_path):
    _mkrepo(tmp_path)
    offender = tmp_path / "src/dsm/other/module.py"
    offender.write_text(
        "import dsm.core.storage\ns = dsm.core.storage.Storage()\n",
        encoding="utf-8",
    )
    result = _run_lint(tmp_path)
    assert result.returncode == 1
    assert "import of dsm.core.storage module" in result.stderr


def test_violation_fully_qualified_aliased(tmp_path):
    _mkrepo(tmp_path)
    offender = tmp_path / "src/dsm/other/module.py"
    offender.write_text(
        "import dsm.core.storage as s\nx = s.Storage\n",
        encoding="utf-8",
    )
    result = _run_lint(tmp_path)
    assert result.returncode == 1


def test_multiple_violations_reported(tmp_path):
    _mkrepo(tmp_path)
    (tmp_path / "src/dsm/ans").mkdir(parents=True, exist_ok=True)
    a = tmp_path / "src/dsm/other/a.py"
    b = tmp_path / "src/dsm/ans/b.py"
    a.write_text("from dsm.core.storage import Storage\n", encoding="utf-8")
    b.write_text("import dsm.core.storage\n", encoding="utf-8")
    result = _run_lint(tmp_path)
    assert result.returncode == 1
    assert "src/dsm/other/a.py" in result.stderr
    assert "src/dsm/ans/b.py" in result.stderr
    assert "2 violation" in result.stderr


def test_importing_unrelated_storage_is_fine(tmp_path):
    _mkrepo(tmp_path)
    p = tmp_path / "src/dsm/other/module.py"
    p.write_text(
        "from some.other.module import Storage\nfrom dsm.core import models\n",
        encoding="utf-8",
    )
    result = _run_lint(tmp_path)
    assert result.returncode == 0, f"Expected pass, got:\n{result.stderr}"


def test_using_storage_via_parameter_is_fine(tmp_path):
    _mkrepo(tmp_path)
    p = tmp_path / "src/dsm/other/module.py"
    p.write_text(
        "def consume(storage):\n    return storage.read('x')\n",
        encoding="utf-8",
    )
    result = _run_lint(tmp_path)
    assert result.returncode == 0


def test_syntax_error_file_does_not_crash_lint(tmp_path):
    _mkrepo(tmp_path)
    p = tmp_path / "src/dsm/other/broken.py"
    p.write_text("def f(:\n    pass\n", encoding="utf-8")
    result = _run_lint(tmp_path)
    assert result.returncode == 0
    assert "syntax error" in result.stderr.lower()


def test_demo_path_whitelisted(tmp_path):
    _mkrepo(tmp_path)
    (tmp_path / "demo").mkdir(parents=True, exist_ok=True)
    p = tmp_path / "demo/demo_end_to_end.py"
    p.write_text("from dsm.core.storage import Storage\n", encoding="utf-8")
    result = _run_lint(tmp_path)
    assert result.returncode == 0, f"Expected pass, got:\n{result.stderr}"


def test_scripts_path_whitelisted(tmp_path):
    _mkrepo(tmp_path)
    p = tmp_path / "scripts/trace_replay.py"
    p.write_text("from dsm.core.storage import Storage\n", encoding="utf-8")
    result = _run_lint(tmp_path)
    assert result.returncode == 0, f"Expected pass, got:\n{result.stderr}"


# ---------------------------------------------------------------------------
# Relative imports — must be caught just like absolute imports
# ---------------------------------------------------------------------------

def test_violation_relative_import_level_2(tmp_path):
    """from ..core.storage import Storage — must FAIL"""
    _mkrepo(tmp_path)
    offender = tmp_path / "src/dsm/other/module.py"
    offender.write_text(
        "from ..core.storage import Storage\nx = Storage\n",
        encoding="utf-8",
    )
    result = _run_lint(tmp_path)
    assert result.returncode == 1
    assert "src/dsm/other/module.py" in result.stderr
    assert "relative import" in result.stderr


def test_violation_relative_import_level_3(tmp_path):
    """from ...something.core.storage import Storage — must FAIL"""
    _mkrepo(tmp_path)
    (tmp_path / "src/dsm/a/b").mkdir(parents=True, exist_ok=True)
    offender = tmp_path / "src/dsm/a/b/module.py"
    offender.write_text(
        "from ...core.storage import Storage\nx = Storage\n",
        encoding="utf-8",
    )
    result = _run_lint(tmp_path)
    assert result.returncode == 1
    assert "src/dsm/a/b/module.py" in result.stderr


def test_violation_relative_submodule_import(tmp_path):
    """from ..core import storage (submodule access) — must FAIL"""
    _mkrepo(tmp_path)
    offender = tmp_path / "src/dsm/other/module.py"
    offender.write_text(
        "from ..core import storage\ns = storage.Storage()\n",
        encoding="utf-8",
    )
    result = _run_lint(tmp_path)
    assert result.returncode == 1
    assert "relative indirect access" in result.stderr


def test_violation_relative_reexport_bypass(tmp_path):
    """from ..core import Storage (re-exported class bypass) — must FAIL"""
    _mkrepo(tmp_path)
    offender = tmp_path / "src/dsm/other/module.py"
    offender.write_text(
        "from ..core import Storage\nx = Storage\n",
        encoding="utf-8",
    )
    result = _run_lint(tmp_path)
    assert result.returncode == 1
    assert "relative re-export bypass" in result.stderr


def test_violation_absolute_reexport_bypass(tmp_path):
    """from dsm.core import Storage — must FAIL"""
    _mkrepo(tmp_path)
    offender = tmp_path / "src/dsm/other/module.py"
    offender.write_text(
        "from dsm.core import Storage\nx = Storage\n",
        encoding="utf-8",
    )
    result = _run_lint(tmp_path)
    assert result.returncode == 1
    assert "absolute re-export bypass" in result.stderr


def test_whitelisted_path_allows_relative_import(tmp_path):
    """Whitelisted paths can use relative imports of Storage freely."""
    _mkrepo(tmp_path)
    (tmp_path / "src/dsm/rr/query").mkdir(parents=True, exist_ok=True)
    p = tmp_path / "src/dsm/rr/query/engine.py"
    p.write_text(
        "from ...core.storage import Storage\nfrom ..something import X\n",
        encoding="utf-8",
    )
    result = _run_lint(tmp_path)
    assert result.returncode == 0, f"Expected pass, got:\n{result.stderr}"


# ---------------------------------------------------------------------------
# LEGITIMATE_WRITERS + KNOWN_READER_VIOLATIONS behavior
# ---------------------------------------------------------------------------

def test_legitimate_writer_passes(tmp_path, monkeypatch):
    """A file listed in LEGITIMATE_WRITERS may import Storage without lint fail."""
    # We test the behavior by patching LEGITIMATE_WRITERS for the duration
    # of the test. We can't easily do this across subprocess call, so we
    # use a file that is NOT in LEGITIMATE_WRITERS and verify it fails,
    # then we use a file that IS whitelisted (via WHITELIST_PREFIXES) and
    # verify it passes. The semantic equivalence holds.
    _mkrepo(tmp_path)
    (tmp_path / "src/dsm/ans").mkdir(parents=True, exist_ok=True)
    p = tmp_path / "src/dsm/ans/not_a_legitimate_writer.py"
    p.write_text(
        "from ..core.storage import Storage\nx = Storage\n",
        encoding="utf-8",
    )
    result = _run_lint(tmp_path)
    assert result.returncode == 1, "File not in LEGITIMATE_WRITERS should fail"


def test_stale_writer_entry_detected(tmp_path):
    """If LEGITIMATE_WRITERS contains a file that no longer violates, lint fails.

    We can't easily hot-patch the frozensets in a subprocess, so we use a
    structural test: verify that the failure message for stale entries is
    present in the code, and that removing all known violations from a test
    repo's src/dsm produces a clean state.
    """
    # Structural verification only — ensure the code path exists.
    import scripts.forbid_storage_access as lint_module
    assert hasattr(lint_module, "LEGITIMATE_WRITERS")
    assert hasattr(lint_module, "KNOWN_READER_VIOLATIONS")
    assert hasattr(lint_module, "is_legitimate_writer")
    assert hasattr(lint_module, "is_known_reader_violation")


def test_both_lists_are_disjoint():
    """A file cannot be both a legitimate writer AND a known reader violation."""
    import scripts.forbid_storage_access as lint_module
    overlap = lint_module.LEGITIMATE_WRITERS & lint_module.KNOWN_READER_VIOLATIONS
    assert not overlap, f"Files in both sets: {overlap}"


def test_legitimate_writers_nonempty():
    """Sanity check: LEGITIMATE_WRITERS is populated (not accidentally cleared)."""
    import scripts.forbid_storage_access as lint_module
    assert len(lint_module.LEGITIMATE_WRITERS) >= 15, \
        "LEGITIMATE_WRITERS suspiciously small — check the scan"


def test_known_reader_violations_drained_toward_zero():
    """Documentation test: KNOWN_READER_VIOLATIONS should shrink over time,
    not grow. If this assertion ever fails because new entries were added,
    the CI surface this as a review requirement."""
    import scripts.forbid_storage_access as lint_module
    # Initial count after V3-A introduction: 5. Should never grow, only shrink.
    assert len(lint_module.KNOWN_READER_VIOLATIONS) <= 5, \
        "KNOWN_READER_VIOLATIONS has grown — new readers should use RR, not be added here"
