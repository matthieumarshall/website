"""Domain exceptions raised by services and integrations.

These carry no HTTP knowledge; :mod:`website.web.handlers` maps each class to
an HTTP status code, so the business layers stay framework-independent.
"""


class DomainError(Exception):
    """Base class for all expected, user-facing domain failures."""

    def __init__(self, message: str = "") -> None:
        """Store a human-readable message describing the failure."""
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    """A requested entity does not exist."""


class InvalidRequestError(DomainError):
    """The request is malformed (for example, an unsupported file type)."""


class ValidationError(DomainError):
    """Submitted data failed a business validation rule."""


class ConflictError(DomainError):
    """The request conflicts with existing state (duplicates, limits)."""


class ForbiddenError(DomainError):
    """The current user may not perform this action right now."""


class PayloadTooLargeError(DomainError):
    """An uploaded file exceeds the permitted size."""


class ServiceUnavailableError(DomainError):
    """A required external service is unavailable or misconfigured."""


class UpstreamError(DomainError):
    """An external service returned an unexpected response."""


class OperationFailedError(DomainError):
    """An internal operation failed unexpectedly."""
