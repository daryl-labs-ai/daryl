#!/usr/bin/env python3
"""DSM v2 - Package entry point (uses main_dsm CLI: status, verify, startup-check, etc.)."""

from .cli import main_dsm

if __name__ == "__main__":
    main_dsm()
