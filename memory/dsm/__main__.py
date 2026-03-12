#!/usr/bin/env python3
"""DSM v2 - Package entry point"""

from .cli import DSMCLI

if __name__ == "__main__":
    cli = DSMCLI()
    cli.main()
