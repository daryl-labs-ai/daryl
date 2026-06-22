#!/usr/bin/env python3
"""Validate the editable monorepo development install."""

from __future__ import annotations

import importlib
import sys


REQUIRED_MODULES = (
    "dsm",
    "dsm_primitives",
    "agent_mesh",
    "mcp",
    "filelock",
)


def main() -> int:
    failures: list[str] = []
    for module_name in REQUIRED_MODULES:
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # pragma: no cover - diagnostic path
            failures.append(f"{module_name}: {type(exc).__name__}: {exc}")
            continue
        origin = getattr(module, "__file__", "<namespace>")
        print(f"{module_name}: OK ({origin})")

    if failures:
        print("dev install validation failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("dev install validation: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
