# Known Issues

## K-1: Storage.append() is not fully thread-safe

**Status**: Fixed in v0.6.1  
**Severity**: Medium (was)  
**Affected code**: src/dsm/core/storage.py (frozen kernel)

Shard-level lockfile (`integrity/{shard_id}.lock`) now covers the full
append operation (segment write + metadata commit). Concurrent appends
are serialized per shard.

---

## K-2: Crash window between fsync and last_hash update

**Status**: Fixed in v0.6.1  
**Severity**: Medium (was)  
**Affected code**: src/dsm/core/storage.py (frozen kernel)

`_commit_integrity_and_metadata()` now runs inside the same shard lock
as the segment write (after fsync). No crash window. Use `reconcile_shard()`
/ `reconcile_all()` at startup to repair any pre-fix divergence (O(1) detection).

---

## K-3: Metadata race condition outside lock

**Status**: Fixed in v0.6.1  
**Severity**: Medium (was)  
**Affected code**: src/dsm/core/storage.py (frozen kernel)

Metadata updates are inside the shard lock. `_commit_integrity_and_metadata()`
writes last_hash + entry_count + timestamps atomically under the same lock.
