"""Stable error types translated by the SillyTavern HTTP adapter."""


class SillyTavernIntegrationServiceError(RuntimeError):
    """Base error for failures at the SillyTavern integration boundary."""


class SillyTavernIntegrationServiceConflictError(
    SillyTavernIntegrationServiceError
):
    """Conflict raised when an external turn identity is reused incorrectly."""
