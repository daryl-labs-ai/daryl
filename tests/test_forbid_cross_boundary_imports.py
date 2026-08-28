"""ADR-HEXASHARD-0001 — the guard that keeps extraction cheap.

HexaShard is an independent runtime temporarily co-located in this repository.
The cost of moving it to its own repository later is set almost entirely by
whether a production import ever crossed the boundary in either direction.

These tests prove the guard holds on the real tree, and that it would actually
fail if someone crossed it — which is the only property that matters.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "forbid_cross_boundary_imports.py"

sys.path.insert(0, str(REPO / "scripts"))
from forbid_cross_boundary_imports import BOUNDARY, main, scan  # noqa: E402


def _fake_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return tmp_path


# -- the real repository ---------------------------------------------------

def test_the_repository_currently_honours_the_boundary():
    assert scan(REPO) == []


def test_script_runs_clean_as_a_command():
    proc = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "no cross-boundary imports" in proc.stdout


def test_both_directions_are_covered_by_configuration():
    assert BOUNDARY["src/hexashard"] == frozenset({"dsm", "prl"})
    assert BOUNDARY["src/hexashard_adapter"] == frozenset({"dsm", "prl"})
    assert BOUNDARY["src/dsm"] == frozenset({"hexashard", "hexashard_adapter"})
    assert BOUNDARY["src/prl"] == frozenset({"hexashard", "hexashard_adapter"})


# -- it must actually fail -------------------------------------------------

@pytest.mark.parametrize("rel,body,imported", [
    ("src/hexashard/leak.py", "from dsm.core import storage\n", "dsm"),
    ("src/hexashard/leak.py", "import dsm\n", "dsm"),
    ("src/hexashard/leak.py", "from prl.store import dsm_commit\n", "prl"),
    ("src/hexashard_adapter/leak.py", "import dsm.core.storage\n", "dsm"),
    ("src/hexashard_adapter/leak.py", "from prl import daryl_cli\n", "prl"),
])
def test_hexashard_importing_daryl_is_a_violation(tmp_path, rel, body, imported):
    root = _fake_repo(tmp_path, {rel: body})
    violations = scan(root)
    assert len(violations) == 1
    assert violations[0].imported == imported
    assert violations[0].file == rel


@pytest.mark.parametrize("rel,body,imported", [
    ("src/dsm/leak.py", "import hexashard\n", "hexashard"),
    ("src/dsm/leak.py", "from hexashard import Project\n", "hexashard"),
    ("src/dsm/leak.py", "import hexashard_adapter\n", "hexashard_adapter"),
    ("src/prl/leak.py", "from hexashard_adapter import HexaShardAdapter\n", "hexashard_adapter"),
    ("src/prl/leak.py", "from hexashard.store import SourceStore\n", "hexashard"),
])
def test_daryl_importing_hexashard_is_a_violation(tmp_path, rel, body, imported):
    root = _fake_repo(tmp_path, {rel: body})
    violations = scan(root)
    assert len(violations) == 1
    assert violations[0].imported == imported


def test_violation_exits_nonzero_and_points_at_the_adr(tmp_path, capsys):
    _fake_repo(tmp_path, {"src/hexashard/leak.py": "import dsm\n"})
    assert main(["--root", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "ADR-HEXASHARD-0001" in err
    assert "must not import dsm" in err


def test_a_clean_tree_exits_zero(tmp_path):
    _fake_repo(tmp_path, {
        "src/hexashard/ok.py": "from .store import SourceStore\nimport json\n",
        "src/dsm/ok.py": "from dsm.core import storage\nimport hashlib\n",
    })
    assert main(["--root", str(tmp_path)]) == 0


# -- the edges that matter -------------------------------------------------

def test_type_checking_imports_are_not_exempt(tmp_path):
    """A type-only import still means the package cannot travel alone."""
    root = _fake_repo(tmp_path, {"src/hexashard/leak.py": (
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from dsm.core.storage import Storage\n"
    )})
    assert len(scan(root)) == 1


def test_relative_imports_within_a_package_are_fine(tmp_path):
    root = _fake_repo(tmp_path, {"src/hexashard/ok.py": (
        "from .store import SourceStore\n"
        "from ..hexashard import nothing\n"
    )})
    assert scan(root) == []


def test_mentions_in_comments_and_strings_are_ignored(tmp_path):
    root = _fake_repo(tmp_path, {"src/hexashard/ok.py": (
        '"""HexaShard does not depend on dsm or prl."""\n'
        "# import dsm  <- deliberately not an import\n"
        'NOTE = "see prl.store.dsm_commit for the DSM side"\n'
    )})
    assert scan(root) == []


def test_a_similarly_named_package_is_not_a_false_positive(tmp_path):
    """`dsm_primitives` is a separate distribution and not part of the rule."""
    root = _fake_repo(tmp_path, {
        "src/hexashard/ok.py": "import dsmith\nimport dsm_primitives\n",
    })
    assert scan(root) == []


def test_tests_and_scripts_are_not_scanned(tmp_path):
    """Tests may legitimately import both sides — this file does."""
    root = _fake_repo(tmp_path, {
        "tests/test_x.py": "import hexashard\nimport dsm\n",
        "scripts/x.py": "import hexashard\nimport dsm\n",
    })
    assert scan(root) == []


def test_unrelated_source_trees_are_not_scanned(tmp_path):
    root = _fake_repo(tmp_path, {"src/other/x.py": "import hexashard\nimport dsm\n"})
    assert scan(root) == []


def test_every_violation_in_a_file_is_reported(tmp_path):
    root = _fake_repo(tmp_path, {"src/hexashard/leak.py": (
        "import dsm\n"
        "from prl import daryl_cli\n"
    )})
    assert len(scan(root)) == 2


def test_missing_root_is_an_internal_error(tmp_path):
    assert main(["--root", str(tmp_path / "nope")]) == 2
