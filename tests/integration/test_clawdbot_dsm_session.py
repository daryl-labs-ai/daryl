#!/usr/bin/env python3
"""
Minimal test: write a session to DSM from Clawdbot runtime conditions.
Run from Clawdbot dir with PYTHONPATH including repo, or from Daryl with dsm installed.

Usage:
  DATA_DIR=<path_to_data> PYTHONPATH=<repo_root> python3 tests/integration/test_clawdbot_dsm_session.py

Then verify:
  dsm read sessions --data-dir $DATA_DIR --limit 10
"""

import os
import sys


def main():
    data_dir = os.environ.get("DATA_DIR", "data")
    # Resolve to absolute so same path works for CLI
    if not os.path.isabs(data_dir):
        data_dir = os.path.abspath(data_dir)

    try:
        from dsm.core.storage import Storage
        from dsm.session.session_graph import SessionGraph
    except ImportError as e:
        print("FAIL: cannot import dsm:", e, file=sys.stderr)
        print("Run with PYTHONPATH=<repo_root> (or pip install -e .)", file=sys.stderr)
        sys.exit(1)

    storage = Storage(data_dir=data_dir)
    session_graph = SessionGraph(storage=storage)

    session_graph.start_session(source="clawdbot_test")
    session_graph.execute_action("test_action", {"message": "Clawdbot DSM integration test"})
    session_graph.end_session()

    print(f"OK: Session written to DSM data_dir={data_dir}")
    print(f"Verify with: dsm read sessions --data-dir {data_dir} --limit 10")


if __name__ == "__main__":
    main()
