"""PRL exception taxonomy.

Flat hierarchy under :class:`PRLError`, mirroring the pattern used by the
repository's primitive/kernel error families. P0 only needs config-loading,
validation, and the Entry-mapping boundary; richer subclasses (scan, store,
query) are added by later milestones.
"""

from __future__ import annotations


class PRLError(Exception):
    """Base class for every PRL error."""


class PRLConfigError(PRLError):
    """Raised when a PRL configuration cannot be loaded or is invalid."""


class PRLValidationError(PRLError):
    """Raised when a PRL model fails validation at a boundary.

    Wraps Pydantic ``ValidationError`` so callers never see the underlying
    library type leak through (same boundary-wrapping rule as the kernel).
    """


class PRLEntryMappingError(PRLError):
    """Raised when a DSM Entry (or draft) cannot be mapped to a PRL node.

    Covers an unknown / missing ``metadata['action_name']`` and a ``content``
    payload that is not decodable canonical JSON.
    """
