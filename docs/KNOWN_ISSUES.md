# Known Issues

## K-1: Storage.append() is not fully thread-safe

**Status**: Known, documented  
**Severity**: Medium  
**Affected code**: src/dsm/core/storage.py (frozen kernel)

The `fcntl.flock` in `Storage.append()` locks only the segment file.
However, metadata files (`segment_meta.json`, `*_last_hash.json`) are
read and written outside this lock scope, creating race conditions
under concurrent multi-threaded appends.

**Impact**: Concurrent appends from multiple threads in the same process
may produce corrupted metadata (entry count, last hash, segment rotation).
The segment data itself is protected by the file lock.

**Workaround**: Serialize appends at the application level (single writer
thread or external lock).

**Fix**: Requires kernel modification — a global lockfile covering the
full append operation (segment write + metadata updates). Deferred until
kernel freeze is lifted.

Discovered during concurrent append stress testing (March 2026).

---

## K-2: Crash window between fsync and last_hash update

**Status**: Known, documented  
**Severity**: Medium  
**Affected code**: src/dsm/core/storage.py (frozen kernel)

After writing an entry to the segment file and calling `fsync`, the kernel
updates `*_last_hash.json` in a separate step. If the process crashes
between fsync and this metadata write, the segment contains the new entry
but the last_hash file does not reflect it.

**Impact**: On next startup, integrity checks or replay may disagree with
the on-disk last_hash; the last entry can appear "missing" from metadata
or cause verify/replay to report inconsistency.

**Workaround**: Run verify after restart and, if needed, reconcile
segment content with metadata manually (do not modify kernel). Prefer
single-writer usage to reduce crash surface.

**Fix**: Deferred until kernel freeze is lifted — persist last_hash in the
same critical section as the segment write (e.g. write last_hash before
or in same fsync scope as segment tail).

---

## K-3: Metadata race condition outside lock

**Status**: Known, documented  
**Severity**: Medium  
**Affected code**: src/dsm/core/storage.py (frozen kernel)

Metadata files (`segment_meta.json`, `*_last_hash.json`) are read and
updated outside the segment file lock (or in a separate code path). Under
concurrent access (multiple processes or threads), one writer can overwrite
another’s metadata update.

**Impact**: Entry counts, last hash, or segment list can become inconsistent
with actual segment content; verify may report tampering or broken chain.

**Workaround**: Use a single writer process for a given data_dir, or an
external lock (e.g. file lock or daemon) so only one append runs at a time.

**Fix**: Requires kernel change — extend the lock to cover all metadata
reads and writes for the shard (or use a single lockfile per shard covering
segment + metadata). Deferred until kernel freeze is lifted.
