#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSM v2 - Root Package
Exports only essential, stable, package-relative modules
"""

from .core.storage import Storage
from .core.models import Entry, ShardMeta
from .causal import (
    create_dispatch_hash,
    create_routing_hash,
    DispatchRecord,
    verify_dispatch_hash,
    verify_causal_chain,
)
from .attestation import (
    ComputeAttestation,
    create_attestation,
    verify_attestation,
    verify_attestation_against_data,
    sign_attestation,
)

__version__ = "0.7.0"

__all__ = [
    "__version__",
    "Storage",
    "Entry",
    "ShardMeta",
    "create_dispatch_hash",
    "create_routing_hash",
    "DispatchRecord",
    "verify_dispatch_hash",
    "verify_causal_chain",
    "ComputeAttestation",
    "create_attestation",
    "verify_attestation",
    "verify_attestation_against_data",
    "sign_attestation",
]
