"""Daryl — the user-facing CLI (M1 · D1).

``daryl`` IS the ``prl`` recall/navigation surface with a product face, plus one
new command: ``init``. Every shared verb (``ask``, ``objects``, ``object``,
``agent``, ``org``, ``receipt``, ``go``, …) is delegated *verbatim* to
``prl.query.cli`` — same parsers, same handlers, no behavior fork, no rename of
internals. ``prl`` is untouched; ``daryl`` is a purely additive surface (M1 gate 3).

D1 scope is deliberately narrow: the entry point, the aliased surface, and
``daryl init`` (bootstrap store + config). The product-polished ``--help`` and the
"verbs work by default against the init'ed store" wiring are D3, not here.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from .config import _DEFAULT_CONFIG_PATH, PRLConfig
from .query.cli import dispatch, register_common_subparsers
from .store import open_storage

# The store's default home. Mirrors ``PRLConfig.storage_dir``'s default so
# ``daryl init`` and a hand-written config agree on where the store lives.
_DEFAULT_STORAGE_DIR = Path.home() / ".daryl" / "prl"

_DESCRIPTION = "Daryl — recall receipt-backed answers from your own corpus."


def build_parser() -> argparse.ArgumentParser:
    """The ``daryl`` parser: ``init`` first (the one new verb), then the entire
    shared ``prl`` surface registered identically."""
    parser = argparse.ArgumentParser(prog="daryl", description=_DESCRIPTION)
    sub = parser.add_subparsers(dest="command", required=True)
    _add_init_subparser(sub)
    register_common_subparsers(sub)  # ask / objects / object / agent / org / receipt / go / …
    return parser


def _add_init_subparser(sub: "argparse._SubParsersAction") -> None:
    p_init = sub.add_parser(
        "init",
        help="bootstrap a Daryl store + config (run once, sane defaults)",
    )
    p_init.add_argument(
        "--project",
        help="folder to declare as the recall scope (default: current directory)",
    )
    p_init.add_argument(
        "--storage-dir",
        dest="storage_dir",
        help="where the store lives (default: ~/.daryl/prl)",
    )
    p_init.add_argument(
        "--config",
        help="path to write the config JSON (default: ~/.daryl/prl/config.json)",
    )
    p_init.add_argument(
        "--org-id",
        dest="org_id",
        help="owning organization id (optional, e.g. org.acme)",
    )
    p_init.add_argument(
        "--force",
        action="store_true",
        help="overwrite an existing config instead of leaving it untouched",
    )


def cmd_init(args: argparse.Namespace) -> int:
    """Bootstrap the store directory and write a minimal config — sane defaults,
    no questions. Idempotent: an existing config is reported, never clobbered
    (unless ``--force``). The store's tamper-evident chain is *not* written here;
    ``Storage`` only lays down its ``shards/`` and ``integrity/`` directories."""
    project = Path(args.project).expanduser().resolve() if args.project else Path.cwd()
    # Persist an absolute store path — a relative one in the config would resolve
    # against whatever cwd a later `daryl <verb>` happens to run from.
    storage_dir = (
        Path(args.storage_dir).expanduser().resolve() if args.storage_dir else _DEFAULT_STORAGE_DIR
    )
    config_path = Path(args.config).expanduser() if args.config else _DEFAULT_CONFIG_PATH

    if config_path.exists() and not args.force:
        print(f"daryl is already initialized — config at {config_path}")
        try:
            existing = PRLConfig.load(config_path)
            print(f"  storage_dir: {existing.storage_dir}")
        except Exception:  # noqa: BLE001  # nosec B110 — best-effort readback of an existing config; never fatal
            pass
        print("re-run with --force to overwrite.")
        return 0

    data: dict[str, object] = {
        "declared_projects": [str(project)],
        "storage_dir": str(storage_dir),
    }
    if args.org_id:
        data["org_id"] = args.org_id

    try:
        config = PRLConfig(**data)  # validate before we write anything
    except ValidationError as exc:
        print(f"error: invalid config: {exc}", file=sys.stderr)
        return 2

    # Bootstrap the store: constructing Storage creates <storage_dir>/shards and
    # <storage_dir>/integrity (idempotent, no chain writes).
    open_storage(config)

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    print("✓ daryl initialized")
    print(f"  store:   {config.storage_dir}")
    print(f"  config:  {config_path}")
    print(f"  scope:   {project}")
    print("Next: import a conversation corpus to recall against, then `daryl ask`.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "init":
        return cmd_init(args)
    return dispatch(args)  # every shared verb runs the identical prl handler


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
