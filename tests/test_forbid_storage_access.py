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
