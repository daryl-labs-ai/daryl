"""
AnchorBackend ABC — the contract that `src/dsm/anchor.py` depends on.

Backlog: V0-07.

This module is the *additive extension* referenced in SPEC §1. The existing
`src/dsm/anchor.py` (P4) is NOT modified by this scaffold. Instead, this
module defines the ABC separately, and `anchor.py` requires a minimal
two-line change to import and use it.

Required addition to `src/dsm/anchor.py` (to be applied in a separate PR
after the scaffold is validated):

    # at the top of anchor.py
    from dsm.anchor_backend import AnchorBackend

    # in the Anchor class, add:
    def with_backend(self, backend: AnchorBackend) -> "Anchor":
        self._backend = backend
        return self

That is the entirety of the kernel-respecting integration. Nothing else in
anchor.py changes in V0. The Anchor facade delegates `.anchor(shard_id)` to
the backend's submit/watch only after with_backend() has been called. Until
a backend is registered, the existing anchor.py behavior is preserved.

Rationale for a separate module:
    - Keeps anchor.py change surface minimal (two lines).
    - Allows the backend ABC to live in dsm.* alongside the frozen kernel
      without any new dependency from the kernel itself.
    - Makes the ABC trivially swappable for V2 (registry) or V3 (batch).

Invariants:
    - The ABC has no default implementations. Every method is abstract.
    - Backends must be stateless from the facade's perspective, OR manage
      their own state internally; the facade passes an intent and expects
      a receipt.

Test file: tests/multiversx/test_backend_contract.py (scaffold)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar, Iterator

# These imports are used only as type annotations (PEP 563 via
# `from __future__ import annotations`), so guarding them under TYPE_CHECKING
# avoids a circular import between `dsm.anchor_backend` and
# `dsm.multiversx.__init__` (which pulls in `dsm.multiversx.backend`, which
# in turn imports this module).
if TYPE_CHECKING:
    from dsm.multiversx.schemas import (
        AnchorEvent,
        AnchorIntent,
        AnchorSubmissionReceipt,
        BackendCapabilities,
        ReconcileReport,
        VerifyResult,
    )


class AnchorBackend(ABC):
    """Contract for an external-witness anchoring backend.

    Concrete implementations (e.g. MultiversXAnchorBackend) provide the
    wiring to a specific chain or service. The Anchor facade in anchor.py
    uses this ABC and does not know about MultiversX directly.

    Class attributes to override:
        backend_name: Short identifier, e.g. "multiversx".
        backend_version: Semver of the adapter implementation.

    Test file: tests/multiversx/test_backend_contract.py (scaffold)
    """

    backend_name: ClassVar[str] = "abstract"
    backend_version: ClassVar[str] = "0.0.0"

    @abstractmethod
    def capabilities(self) -> BackendCapabilities:
        """Return the capability manifest for this backend and the current regime.

        Called at facade init and whenever the facade needs to decide
        whether `anchor_settled` is required as a terminal state.
        """
        raise NotImplementedError

    @abstractmethod
    def submit(self, intent: AnchorIntent) -> AnchorSubmissionReceipt:
        """Submit the anchor. The AnchorIntent MUST already be in the DSM log.

        See concrete implementations for invariants around ordering and
        local durability (F12).
        """
        raise NotImplementedError

    @abstractmethod
    def watch(self, receipt: AnchorSubmissionReceipt) -> Iterator[AnchorEvent]:
        """Yield AnchorEvents until a terminal state is reached."""
        raise NotImplementedError

    @abstractmethod
    def verify(self, intent_entry_id: str, on_chain_ref: dict) -> VerifyResult:
        """Audit a single anchor against the on-chain record."""
        raise NotImplementedError

    @abstractmethod
    def reconcile(self, shard_id: str) -> ReconcileReport:
        """Reconcile local tail against last on-chain anchor. Used after F11."""
        raise NotImplementedError
