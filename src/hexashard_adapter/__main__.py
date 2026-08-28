"""Minimal CLI. No TUI.

    python -m hexashard_adapter chat ./project
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .adapter import HexaShardAdapter
from .config import AdapterConfig
from .errors import AdapterError, ProjectNotFound
from .provider import ollama_available


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="hexashard_adapter", description="HexaShard Adapter v0.1")
    sub = p.add_subparsers(dest="cmd", required=True)
    chat = sub.add_parser("chat", help="REPL against an existing project")
    chat.add_argument("project")
    chat.add_argument("--provider", choices=("mock", "ollama"), default="mock")
    chat.add_argument("--mode", choices=("NORMAL", "READ_ONLY"), default="NORMAL")
    args = p.parse_args(argv)

    if args.cmd != "chat":
        return 2
    root = Path(args.project)
    cfg = AdapterConfig(provider=args.provider, mode=args.mode)
    if args.provider == "ollama" and not ollama_available(cfg.endpoint):
        print("ollama unavailable; use --provider mock", file=sys.stderr)
        return 2
    try:
        adapter = HexaShardAdapter.open(root, config=cfg)
    except ProjectNotFound:
        print(f"no project at {root}", file=sys.stderr)
        return 2
    print(f"project {adapter.project.config.name}  epoch {adapter.project.state.epoch}  {args.provider}")
    print("enter text; Ctrl-D to exit")
    try:
        while True:
            try:
                line = input("> ")
            except EOFError:
                print()
                break
            if not line.strip():
                continue
            try:
                result = adapter.chat(line.strip())
            except AdapterError as e:
                print(f"error: {e}")
                continue
            print(result.response_text)
            print(
                f"  [in={result.total_context_tokens} store={result.project_store_tokens} "
                f"epoch={result.epoch} trunc={result.truncated}]"
            )
    finally:
        adapter.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
