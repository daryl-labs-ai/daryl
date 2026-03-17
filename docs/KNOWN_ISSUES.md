# Known Issues

> **Note (v0.7.0):** Issues K-1, K-2, and K-3 have been resolved. See commits for details.
> S-1 (seed encryption), S-2 (key rotation), S-3 (witness hash), S-5 (startup check),
> and W-7 (Windows compatibility) have also been fixed.

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
