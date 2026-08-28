"""HexaShard Adapter v0.1 public surface."""

from .adapter import HexaShardAdapter
from .config import AdapterConfig
from .core_lock import (
    ARCHIVE_SHA256,
    FROZEN_CORE_MODULES,
    assert_core_unmodified,
    core_module_digests,
)
from .errors import (
    AdapterError,
    ContextBudgetExceeded,
    InvalidProviderConfiguration,
    MalformedProviderResponse,
    ProjectNotFound,
    ProviderUnavailable,
)
from .models import ChatTurnResult
from .provider import ChatProvider, MockChatProvider, OllamaChatProvider, UnavailableProvider

__all__ = [
    "AdapterConfig",
    "AdapterError",
    "ARCHIVE_SHA256",
    "FROZEN_CORE_MODULES",
    "ChatProvider",
    "ChatTurnResult",
    "ContextBudgetExceeded",
    "HexaShardAdapter",
    "InvalidProviderConfiguration",
    "MockChatProvider",
    "OllamaChatProvider",
    "MalformedProviderResponse",
    "ProjectNotFound",
    "ProviderUnavailable",
    "UnavailableProvider",
    "assert_core_unmodified",
    "core_module_digests",
]
