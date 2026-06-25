"""P4 tests — the `python -m prl` CLI (index + status).

Requires the real DSM kernel (commit path writes via Storage.append). Validates
the index command end-to-end (incl. verify_shard), status output, error paths,
and the `python -m prl` entrypoint wiring via subprocess.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from dsm.core.storage import Storage
from dsm.verify import verify_shard

from prl.query.cli import build_parser, cmd_status, main
from prl.store import prl_shard_name
from prl.index import make_project_node


def _project_dir(tmp_path):
    d = tmp_path / "proj"
    (d / "src").mkdir(parents=True)
    (d / "src" / "m.py").write_bytes(b"print(1)\n")
    (d / "README.md").write_bytes(b"# hi\n")
    return d


# --- index -----------------------------------------------------------------


def test_index_single_project_commits_and_verifies(tmp_path, capsys):
    proj = _project_dir(tmp_path)
    dsm_dir = tmp_path / "dsm"
    rc = main(["index", "--project", str(proj), "--storage-dir", str(dsm_dir)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "✓ proj:" in out and "files" in out

    # the project's shard verifies clean
    storage = Storage(data_dir=str(dsm_dir))
    shard = prl_shard_name(make_project_node(proj).project_id)
    report = verify_shard(storage, shard)
    assert str(report["status"]).endswith("OK")
    assert report["total_entries"] > 0


def test_index_with_config_file(tmp_path, capsys):
    proj = _project_dir(tmp_path)
    dsm_dir = tmp_path / "dsm"
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({
        "declared_projects": [str(proj)],
        "storage_dir": str(dsm_dir),
    }))
    rc = main(["index", "--config", str(cfg)])
    assert rc == 0
    assert "✓ proj:" in capsys.readouterr().out


def test_index_bad_config_returns_error(tmp_path, capsys):
    missing = tmp_path / "nope.json"
    rc = main(["index", "--config", str(missing)])
    assert rc == 2
    assert "error:" in capsys.readouterr().err


# --- status ----------------------------------------------------------------


def test_status_lists_projects_and_shards(tmp_path, capsys):
    proj = _project_dir(tmp_path)
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"declared_projects": [str(proj)], "storage_dir": str(tmp_path / "dsm")}))
    rc = main(["status", "--config", str(cfg)])
    assert rc == 0
    out = capsys.readouterr().out
    shard = prl_shard_name(make_project_node(proj).project_id)
    assert "declared projects: 1" in out
    assert shard in out


def test_status_does_not_read_dsm(tmp_path, capsys):
    # status must work even when nothing has ever been committed (no DSM dir).
    proj = _project_dir(tmp_path)
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"declared_projects": [str(proj)], "storage_dir": str(tmp_path / "never")}))
    assert main(["status", "--config", str(cfg)]) == 0
    assert not (tmp_path / "never").exists()  # no read/write side effects


# --- parser / entrypoint ---------------------------------------------------


def test_parser_requires_subcommand():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_python_m_prl_entrypoint(tmp_path):
    """`python -m prl index --project ...` runs end-to-end via __main__.py."""
    proj = _project_dir(tmp_path)
    dsm_dir = tmp_path / "dsm"
    env = dict(os.environ)
    # PYTHONPATH is set by the harness to include src/ (+ packages); inherit it.
    proc = subprocess.run(
        [sys.executable, "-m", "prl", "index", "--project", str(proj),
         "--storage-dir", str(dsm_dir)],
        capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 0, proc.stderr
    assert "✓ proj:" in proc.stdout
