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
from .exceptions import PRLError
from .ingest import MAX_ANSWER_CHARS, import_chatgpt
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
    _add_import_subparser(sub)
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


def _add_import_subparser(sub: "argparse._SubParsersAction") -> None:
    p_import = sub.add_parser(
        "import",
        help="import a conversation corpus into the store (turn-level observations)",
    )
    p_import.add_argument("source", choices=["chatgpt"], help="corpus format")
    p_import.add_argument(
        "export",
        help="path to the export — a normalized ChatGPT JSON (raw .zip lands in a later release)",
    )
    p_import.add_argument("--config", help="path to the PRL config JSON (default: the init'ed store)")
    p_import.add_argument("--storage-dir", dest="storage_dir", help="override the DSM storage dir")
    p_import.add_argument("--org-id", dest="org_id", help="owning organization id (optional)")


def _resolve_write_config(args: argparse.Namespace) -> PRLConfig:
    """Resolve the store to write into: an explicit --config, else an explicit
    --storage-dir, else the init'ed default config. ``declared_projects`` is unused on the
    write path (it exists only to satisfy the P0 invariant)."""
    if getattr(args, "config", None):
        config = PRLConfig.load(Path(args.config))
    elif getattr(args, "storage_dir", None):
        config = PRLConfig(declared_projects=[Path(".")], storage_dir=Path(args.storage_dir))
    else:
        config = PRLConfig.load()  # the store `daryl init` wrote; honest error if absent
    if getattr(args, "storage_dir", None):
        config = config.model_copy(update={"storage_dir": Path(args.storage_dir)})
    return config


def cmd_import(args: argparse.Namespace) -> int:
    """Import a ChatGPT corpus: every conversation turn becomes an Observation act in the
    store. Prints progress + the required counts (conversations · subjects · acts ·
    truncations) and corpus-derived first-step pointers."""
    def _progress(done: int, total: int) -> None:
        if done == total or done % 100 == 0:
            print(f"  … {done}/{total} conversations", file=sys.stderr)

    try:
        config = _resolve_write_config(args)
        print(f"importing {args.source} corpus into {config.storage_dir} …")
        report = import_chatgpt(
            config, args.export, org_id=getattr(args, "org_id", None), on_progress=_progress
        )
    except PRLError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"✓ imported {report.acts} acts from {report.conversations} conversations")
    print(f"  subjects:    {report.subjects}")
    print(f"  acts:        {report.acts}")
    print(f"  truncations: {report.truncations}  (turns over {MAX_ANSWER_CHARS} chars, marked)")
    n = report.normalization
    if n.any():
        # P5: nothing dropped silently — official-tree drops reported by reason.
        print(f"  normalization (official export): "
              f"branches={n.dropped_branches} system={n.dropped_system} "
              f"hidden={n.dropped_hidden} empty={n.dropped_empty} "
              f"non-text-placeholders={n.placeholder_nontext}")
    if report.suggestions:
        print("\nTry these now:")
        for line in report.suggestions:
            print(f"  {line}")
    return 0


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
    if args.command == "import":
        return cmd_import(args)
    return dispatch(args)  # every shared verb runs the identical prl handler


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
