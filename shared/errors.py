class DomainError(Exception):
    """Base domain error for the v1 skeleton."""


class NotFoundError(DomainError):
    """Raised when a requested entity does not exist."""
