"""Small explicit error set. Not a taxonomy."""


class AdapterError(Exception):
    """Base adapter error."""


class ProviderUnavailable(AdapterError):
    """Provider cannot be reached or refused the call."""


class ContextBudgetExceeded(AdapterError):
    """Assembled context cannot fit without dropping critical Pins or the user turn."""


class ProjectNotFound(AdapterError):
    """No HexaShard project at the given path."""


class InvalidProviderConfiguration(AdapterError):
    """Budget/limit/provider fields are inconsistent."""


class MalformedProviderResponse(AdapterError):
    """Provider returned something that is not a usable ProviderResult."""
