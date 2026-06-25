"""Entry point for ``python -m prl`` — delegates to the P4 CLI."""

from __future__ import annotations

import sys

from .query.cli import main

if __name__ == "__main__":
    sys.exit(main())
