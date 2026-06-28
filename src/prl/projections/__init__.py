"""PRL registry projections (Identity across projections, Second epoch #3).

A *projection* is a registry retrieval backend behind the PRL-owned
:class:`~prl.query.standing_read.RegistryProjection` seam. RR is the default; SQLite is a
second backend used to prove the identity model survives a projection swap. DSM stays the
certifier; a projection is read-only and re-mints nothing.
"""

from __future__ import annotations

from .sqlite_projection import SqliteProjection, build_sqlite_projection

__all__ = ["SqliteProjection", "build_sqlite_projection"]
