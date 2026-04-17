"""
DSM × MultiversX integration — public package API.

This package provides the MultiversX anchoring backend for Daryl's DSM.
It is strictly additive above the frozen DSM kernel (`src/dsm/core/`).

See docs:
    - EXECUTIVE.md  : 1-page thesis
    - SPEC.md       : full technical specification
    - BACKLOG.md    : V0/V1/V2 task breakdown

Scope of this package:
    - Regime detection for pre-Supernova / post-Supernova MultiversX
    - Payload-anchor transaction builder (V1; registry contract is V2)
    - Three-stage anchor state machine (intent → included → settled)
    - Chain watcher with WebSocket primary, polling fallback
    - Dual-schema reader for the compatibility window
    - Audit CLI entry point

Out of scope:
    - Any modification to `src/dsm/core/` (kernel is frozen since March 2026).
    - V2 registry contract, Merkle batching, cross-agent P6 flows.
    - Relayed v3 / gasless submission.
"""
from __future__ import annotations

from dsm.multiversx.backend import MultiversXAnchorBackend
from dsm.multiversx.schemas import (
    AnchorFailedEntry,
    AnchorIncludedEntry,
    AnchorIntent,
    AnchorRejectedEntry,
    AnchorSettledEntry,
    AnchorSubmissionReceipt,
    AnchorSubmittedEntry,
    AnchorTimedOutEntry,
    BackendCapabilities,
    EpochRegime,
    NetworkConfigSnapshot,
    ReconcileReport,
    VerifyResult,
)

__all__ = [
    "MultiversXAnchorBackend",
    "AnchorIntent",
    "AnchorSubmittedEntry",
    "AnchorIncludedEntry",
    "AnchorSettledEntry",
    "AnchorFailedEntry",
    "AnchorTimedOutEntry",
    "AnchorRejectedEntry",
    "AnchorSubmissionReceipt",
    "BackendCapabilities",
    "EpochRegime",
    "NetworkConfigSnapshot",
    "ReconcileReport",
    "VerifyResult",
]

__version__ = "0.1.0-scaffold"
