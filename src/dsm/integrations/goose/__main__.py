"""
DSM Goose Integration — CLI entry point for MCP server.

Usage:
    dsm-serve-goose
    dsm-serve-goose --data-dir /custom/path
    dsm-serve-goose --debug
"""

import argparse
import os


def main():
    """Launch DSM MCP server for Goose AI."""
    parser = argparse.ArgumentParser(
        prog="dsm-serve-goose",
        description="DSM Memory System — Provable memory with SHA-256 hash chaining for Goose AI. "
                    "Provides cryptographic audit trail, semantic recall, and cross-session persistence.",
    )
    parser.add_argument(
        "--data-dir",
        default="~/.dsm-data",
        help="DSM data directory (default: ~/.dsm-data)",
    )
    parser.add_argument(
        "--shard-size",
        type=int,
        default=10000,
        help="Max entries per shard before rotation (default: 10000)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode",
    )

    args = parser.parse_args()

    # Set environment before importing server (it reads env vars on import)
    os.environ.setdefault("DSM_DATA_DIR", os.path.expanduser(args.data_dir))
    os.environ.setdefault("DSM_SHARD_SIZE", str(args.shard_size))

    if args.debug:
        os.environ["DSM_DEBUG"] = "1"

    from dsm.integrations.goose.server import mcp

    mcp.run()


if __name__ == "__main__":
    main()
