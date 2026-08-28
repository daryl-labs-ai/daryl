"""HexaShard Core v0.1 -- a bounded project-context runtime.

Keep the chat.  Shard the context.

    from hexashard import Project
    p = Project.create("./demo", name="demo", mission="...")
    p.add_source("spec", "Brief", "...")
    turn = p.handle_turn("what did we decide about X?")

Public surface is deliberately small; everything else is an implementation
detail of these primitives.
"""

from .context import ActiveState, BudgetReport, EpochTransition, enforce_budget, rotation_signal
from .metrics import Metrics
from .models import (
    Hex,
    HexStatus,
    HexType,
    Pin,
    PinStatus,
    Relation,
    SizeClass,
    Source,
    SourceStatus,
    Temperature,
)
from .pins import PinReconciliation, PinResolution
from .project import Project, ProjectConfig, TurnResult
from .providers import MockModelProvider, ModelProvider, ModelResult
from .retrieval import Ambiguity, RetrievalFilters, RetrievalResult, Retriever
from .store import HexMap, PinStore, RelationStore, SourceStore
from .tokens import estimate_tokens, json_tokens
from .trust import InMemoryTrustBackend, NullTrustBackend, TrustBackend

__version__ = "0.1.0"

__all__ = [
    "ActiveState", "Ambiguity", "BudgetReport", "EpochTransition", "Hex", "HexMap",
    "HexStatus", "HexType", "InMemoryTrustBackend", "Metrics", "MockModelProvider",
    "ModelProvider", "ModelResult", "NullTrustBackend", "Pin", "PinReconciliation",
    "PinResolution", "PinStatus", "PinStore", "Project", "ProjectConfig", "Relation",
    "RelationStore", "RetrievalFilters", "RetrievalResult", "Retriever", "SizeClass",
    "Source", "SourceStatus", "SourceStore", "Temperature", "TrustBackend", "TurnResult",
    "enforce_budget", "estimate_tokens", "json_tokens", "rotation_signal", "__version__",
]
