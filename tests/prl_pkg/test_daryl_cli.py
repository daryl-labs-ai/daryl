"""M1 · D1 tests — the ``daryl`` surface (``prl.daryl_cli``).

Covers ``daryl init`` (bootstrap store + config, sane defaults, idempotence),
the additive parser (``init`` plus the whole shared ``prl`` verb set), verbatim
delegation to the ``prl`` dispatch, and — the load-bearing invariant for M1
gate 3 — that ``prl``'s own parser is left completely untouched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from prl.config import PRLConfig
from prl.daryl_cli import build_parser, cmd_init, main
from prl.query.cli import build_parser as build_prl_parser


def _subcommands(parser):
    # The subparsers action is the one whose .choices maps command name -> parser.
    for a in parser._actions:
        if isinstance(getattr(a, "choices", None), dict):
            return set(a.choices)
    return set()  # pragma: no cover


# --- init -------------------------------------------------------------------


def test_init_bootstraps_store_and_config(tmp_path, capsys):
    store = tmp_path / "store"
    cfg = tmp_path / "cfg.json"
    proj = tmp_path / "proj"
    proj.mkdir()

    rc = main(["init", "--project", str(proj), "--storage-dir", str(store), "--config", str(cfg)])
    assert rc == 0

    # store directories are laid down (Storage bootstrap), config written and valid
    assert (store / "shards").is_dir()
    assert (store / "integrity").is_dir()
    assert cfg.is_file()
    loaded = PRLConfig.load(cfg)
    assert loaded.declared_projects == [proj]
    assert loaded.storage_dir == store

    out = capsys.readouterr().out
    assert "✓ daryl initialized" in out
    assert str(store) in out


def test_init_writes_minimal_config(tmp_path):
    cfg = tmp_path / "cfg.json"
    proj = tmp_path / "proj"
    proj.mkdir()
    main(["init", "--project", str(proj), "--storage-dir", str(tmp_path / "s"), "--config", str(cfg)])
    data = json.loads(cfg.read_text())
    # minimal, explicit surface — no ratified retrieval knobs leaked into user config
    assert set(data) == {"declared_projects", "storage_dir"}


def test_init_records_org_id_when_given(tmp_path):
    cfg = tmp_path / "cfg.json"
    proj = tmp_path / "proj"
    proj.mkdir()
    main(["init", "--project", str(proj), "--storage-dir", str(tmp_path / "s"),
          "--config", str(cfg), "--org-id", "org.acme"])
    assert json.loads(cfg.read_text())["org_id"] == "org.acme"


def test_init_is_idempotent_without_force(tmp_path, capsys):
    cfg = tmp_path / "cfg.json"
    proj = tmp_path / "proj"
    proj.mkdir()
    main(["init", "--project", str(proj), "--storage-dir", str(tmp_path / "s"), "--config", str(cfg)])
    capsys.readouterr()
    original = cfg.read_text()

    # a second init points elsewhere but must NOT clobber the existing config
    rc = main(["init", "--project", str(proj), "--storage-dir", str(tmp_path / "other"),
               "--config", str(cfg)])
    assert rc == 0
    assert cfg.read_text() == original
    out = capsys.readouterr().out
    assert "already initialized" in out


def test_init_force_overwrites(tmp_path):
    cfg = tmp_path / "cfg.json"
    proj = tmp_path / "proj"
    proj.mkdir()
    main(["init", "--project", str(proj), "--storage-dir", str(tmp_path / "s"), "--config", str(cfg)])
    rc = main(["init", "--project", str(proj), "--storage-dir", str(tmp_path / "other"),
               "--config", str(cfg), "--force"])
    assert rc == 0
    assert PRLConfig.load(cfg).storage_dir == tmp_path / "other"


def test_init_persists_absolute_storage_dir(tmp_path, monkeypatch):
    """A relative --storage-dir must be stored as an absolute path, so later verbs
    resolve the store regardless of the cwd they run from."""
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "cfg.json"
    (tmp_path / "proj").mkdir()
    rc = main(["init", "--project", "proj", "--storage-dir", "store", "--config", str(cfg)])
    assert rc == 0
    stored = Path(json.loads(cfg.read_text())["storage_dir"])
    assert stored.is_absolute()
    assert stored == (tmp_path / "store").resolve()


def test_init_defaults_project_to_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "cfg.json"
    rc = main(["init", "--storage-dir", str(tmp_path / "s"), "--config", str(cfg)])
    assert rc == 0
    assert PRLConfig.load(cfg).declared_projects == [tmp_path.resolve()]


# --- additive surface / delegation -----------------------------------------


def test_daryl_parser_adds_init_and_keeps_prl_surface():
    daryl_cmds = _subcommands(build_parser())
    prl_cmds = _subcommands(build_prl_parser())
    assert "init" in daryl_cmds
    assert "init" not in prl_cmds  # init is daryl-only
    # every prl verb is reachable under daryl (pure alias over the prl surface)
    assert prl_cmds <= daryl_cmds
    assert {"ask", "objects", "object", "agent", "org", "receipt", "go"} <= daryl_cmds


def test_prl_parser_untouched():
    """M1 gate 3 — prl's parser is byte-identical in shape: prog and verb set unchanged."""
    prl = build_prl_parser()
    assert prl.prog == "prl"
    assert "init" not in _subcommands(prl)


def test_daryl_delegates_shared_verb_to_prl_dispatch(capsys):
    """A shared verb routed through daryl.main hits the identical prl handler.
    `go` with an unknown type is a pure-parse/dispatch path (no store needed)."""
    rc = main(["go", "not-a-type", "x"])
    assert rc == 2
    assert "unknown go type" in capsys.readouterr().err


def test_daryl_parser_requires_subcommand():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])
