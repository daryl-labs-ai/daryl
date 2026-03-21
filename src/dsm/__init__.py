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
from .identity.identity_registry import AgentIdentity, IdentityRegistry
from .sovereignty import SovereigntyPolicy, PolicySnapshot, EnforcementResult
from .orchestrator import NeutralOrchestrator, RuleSet, AdmissionResult
from .collective import (
    CollectiveEntry,
    CollectiveShard,
    CollectiveMemoryDistiller,
    RollingDigester,
    ShardSyncEngine,
)
from .lifecycle import ShardLifecycle, ShardState, LifecycleResult, VerifyResult as LifecycleVerifyResult
from .shard_families import ShardFamily, classify_shard
from .cold_storage import ColdStorage, LocalBackend, ArchiveResult
from .summarizer import Summarizer, StructuralSummarizer, SummaryResult

__version__ = "0.8.0"

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
    # A — Identity Registry
    "IdentityRegistry",
    "AgentIdentity",
    # B — Sovereignty
    "SovereigntyPolicy",
    "PolicySnapshot",
    "EnforcementResult",
    # C — Orchestrator
    "NeutralOrchestrator",
    "RuleSet",
    "AdmissionResult",
    # D — Collective
    "CollectiveEntry",
    "CollectiveShard",
    "CollectiveMemoryDistiller",
    "RollingDigester",
    "ShardSyncEngine",
    # E — Lifecycle
    "ShardLifecycle",
    "ShardState",
    "LifecycleResult",
    "LifecycleVerifyResult",
    # Cross-cutting
    "ShardFamily",
    "classify_shard",
    # Cold Storage
    "ColdStorage",
    "LocalBackend",
    "ArchiveResult",
    # Summarizer
    "Summarizer",
    "StructuralSummarizer",
    "SummaryResult",
]
