#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON:-python}"

cd "$ROOT_DIR"

echo "Using Python: $("$PYTHON_BIN" --version)"

"$PYTHON_BIN" -m pip install -U pip

# dsm-primitives is an internal peer package. Install it first so the root
# package's honest runtime dependency can resolve without requiring PyPI.
"$PYTHON_BIN" -m pip install -e packages/dsm-primitives

"$PYTHON_BIN" -m pip install -e ".[dev]"

# agent-mesh is a monorepo peer used by cross-package integration tests.
"$PYTHON_BIN" -m pip install -e "agent-mesh[dev]"

"$PYTHON_BIN" scripts/validate_dev_install.py
