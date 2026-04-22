# DSM Block Layer (experimental)

Block layer for DSM that batches multiple entries into blocks without modifying the DSM core.

## Features

- **BlockManager**: buffers entries and flushes them as blocks via the DSM Storage API
- **Configurable block size**: number of entries per block (e.g. 8, 32, 128)
- **Append-only**: each block is appended as one record; hash chain and semantics preserved
- **Separate shards**: block mode uses shards with a `_block` suffix (e.g. `sessions_block`) so classic and block mode can coexist and be compared

## Usage

```python
from dsm.core.storage import Storage
from dsm.block_layer import BlockManager

storage = Storage(data_dir="data")
bm = BlockManager(storage=storage, block_size=32)

# Append entries (same Entry type as core)
bm.append(entry)
bm.flush()  # flush any partial block

# Read back (blocks are expanded into individual entries)
entries = bm.read("sessions", limit=100)
```

## Benchmark

Compare classic (one append per entry) vs block mode:

```bash
python3 benchmarks/bench_block_layer.py
```

Example output: block size 32 can be ~20x faster than classic for 500 appends, depending on hardware.

## Design

- Uses only the public DSM Storage API (`Storage.append`, `Storage.read`, segment manager iteration).
- No changes to `src/dsm/core`.
- One block = one `Entry` whose `content` is JSON: `{"block": true, "entries": [...]}`. Readers expand these into individual entries.
