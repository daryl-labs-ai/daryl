"""DSM exceptions — all custom exceptions for modules A→E."""


class DSMError(Exception):
    """Base exception for all DSM errors."""


# --- Module A: Identity Registry ---

class IdentityNotFound(DSMError):
    """Raised when an agent_id cannot be resolved in the registry."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        super().__init__(f"Agent not found: {agent_id}")


class UnauthorizedRevocation(DSMError):
    """Raised when a non-owner tries to revoke an agent."""

    def __init__(self, agent_id: str, caller_id: str, owner_id: str):
        self.agent_id = agent_id
        self.caller_id = caller_id
        self.owner_id = owner_id
        super().__init__(
            f"Cannot revoke {agent_id}: caller {caller_id} is not owner {owner_id}"
        )


# --- Module B: Sovereignty ---

class PolicyViolation(DSMError):
    """Raised when an action violates sovereignty policy."""


class InvalidPolicyStructure(DSMError):
    """Raised when a policy dict is malformed."""


# --- Module C: Orchestrator ---

class RoutingError(DSMError):
    """Raised when the orchestrator cannot route a contribution."""


# --- Module D: Collective ---

class SyncConflict(DSMError):
    """Raised when collective sync detects a conflict."""


# --- Module E: Lifecycle ---

class ShardLifecycleError(DSMError):
    """Raised on lifecycle state transition errors."""
