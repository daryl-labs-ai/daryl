"""PRL command-line interface (P4) — closes Phase 1.

    python -m prl index [--project PATH] [--config PATH] [--storage-dir PATH]
    python -m prl status [--config PATH]

``index`` scans the declared project folders, builds each project map (files +
git commits + edges), and commits it to DSM via the P3 store. ``status`` is a
config-level summary (declared projects + their shards) — it does **not** read
committed DSM data: per ADR-0001 reads go through RR, which lands in P5.

The CLI imports ``open_store`` from ``prl.store`` (the registered writer) rather
than ``Storage`` directly, so it needs no ``LEGITIMATE_WRITERS`` entry of its own.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..config import PRLConfig
from ..exceptions import PRLError
from ..index import build_map, make_project_node
from ..store import open_store, prl_shard_name


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="prl", description="Project Recall Layer")
    sub = parser.add_subparsers(dest="command", required=True)

    p_index = sub.add_parser("index", help="scan declared projects and commit their map to DSM")
    p_index.add_argument("--project", help="index a single folder (ad-hoc, no config file needed)")
    p_index.add_argument("--config", help="path to the PRL config JSON")
    p_index.add_argument("--storage-dir", dest="storage_dir", help="override the DSM storage dir")

    p_status = sub.add_parser("status", help="show declared projects and their shards")
    p_status.add_argument("--config", help="path to the PRL config JSON")

    return parser


def _resolve_config(args: argparse.Namespace) -> PRLConfig:
    if getattr(args, "project", None):
        config = PRLConfig(declared_projects=[Path(args.project)])
    elif getattr(args, "config", None):
        config = PRLConfig.load(Path(args.config))
    else:
        config = PRLConfig.load()
    storage_dir = getattr(args, "storage_dir", None)
    if storage_dir:
        config = config.model_copy(update={"storage_dir": Path(storage_dir)})
    return config


def cmd_index(args: argparse.Namespace) -> int:
    try:
        config = _resolve_config(args)
    except PRLError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    store = open_store(config)
    for root in config.declared_projects:
        project = make_project_node(root)
        pmap = build_map(project, config)
        res = store.commit_map(pmap)
        print(
            f"✓ {project.name}: {len(pmap.files)} files, "
            f"{len(pmap.commits)} commits, {len(pmap.edges)} edges "
            f"→ {res.shard} (tip {res.tip_hash[:19]})"
        )
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    try:
        config = (
            PRLConfig.load(Path(args.config)) if getattr(args, "config", None) else PRLConfig.load()
        )
    except PRLError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"storage_dir: {config.storage_dir}")
    print(f"declared projects: {len(config.declared_projects)}")
    for root in config.declared_projects:
        project = make_project_node(root)
        print(f"  - {project.name}  [{prl_shard_name(project.project_id)}]  {root}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "index":
        return cmd_index(args)
    if args.command == "status":
        return cmd_status(args)
    return 1  # pragma: no cover (argparse 'required' guards this)
