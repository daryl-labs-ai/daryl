# -*- coding: utf-8 -*-
"""
DSM v2 - Block layer benchmark: classic (one append per entry) vs block mode.

Run from repo root with PYTHONPATH including dsm, e.g.:
  PYTHONPATH=/opt/daryl python3 -m dsm.block_layer.benchmark
"""

import os
import sys
import time
import uuid
import tempfile
from pathlib import Path

# Allow running as script from repo root (src layout)
if __name__ == "__main__" and "__file__" in dir():
    _dsm_root = Path(__file__).resolve().parent.parent
    _repo = _dsm_root.parent.parent
    if str(_repo) not in sys.path:
        sys.path.insert(0, str(_repo))
    if str(_dsm_root) not in sys.path:
        sys.path.insert(0, str(_dsm_root))

from dsm.core.storage import Storage
from dsm.core.models import Entry
from dsm.block_layer.manager import BlockManager
from datetime import datetime, timezone


def make_entry(i: int, shard: str = "sessions") -> Entry:
    return Entry(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        session_id="bench-session",
        source="benchmark",
        content=f"entry {i} content",
        shard=shard,
        hash="",
        prev_hash=None,
        metadata={"i": i},
        version="v2.0",
    )


def run_classic(storage: Storage, n: int, shard: str) -> float:
    """Append n entries one-by-one (classic mode). Returns elapsed seconds."""
    start = time.perf_counter()
    for i in range(n):
        entry = make_entry(i, shard)
        storage.append(entry)
    elapsed = time.perf_counter() - start
    return elapsed


def run_block(block_mgr: BlockManager, n: int, shard: str) -> float:
    """Append n entries via block layer (batched). Returns elapsed seconds."""
    start = time.perf_counter()
    for i in range(n):
        entry = make_entry(i, shard)
        block_mgr.append(entry)
    block_mgr.flush()
    elapsed = time.perf_counter() - start
    return elapsed


def main():
    n = 500
    block_sizes = [1, 8, 32, 128]
    shard = "sessions"

    print("DSM Block Layer Benchmark")
    print("=" * 60)
    print(f"Entries per run: {n}")
    print(f"Shard: {shard}")
    print()

    with tempfile.TemporaryDirectory(prefix="dsm_block_bench_") as tmp:
        # Classic: one append per entry (own data dir)
        data_classic = os.path.join(tmp, "classic")
        os.makedirs(data_classic, exist_ok=True)
        storage_classic = Storage(data_dir=data_classic)
        t_classic = run_classic(storage_classic, n, shard)
        print(f"Classic (1 append/entry): {t_classic:.4f}s  ({n / t_classic:.0f} entries/s)")

        for block_size in block_sizes:
            data_block = os.path.join(tmp, f"block_{block_size}")
            os.makedirs(data_block, exist_ok=True)
            storage_block = Storage(data_dir=data_block)
            block_mgr = BlockManager(storage=storage_block, block_size=block_size)
            t_block = run_block(block_mgr, n, shard)
            speedup = t_classic / t_block if t_block > 0 else 0
            print(f"Block (size={block_size:3d}):    {t_block:.4f}s  ({n / t_block:.0f} entries/s)  speedup={speedup:.2f}x")

    print()
    print("Done (append-only semantics preserved in both modes).")


if __name__ == "__main__":
    main()
