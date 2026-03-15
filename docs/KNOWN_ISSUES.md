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
