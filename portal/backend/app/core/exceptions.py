"""Domain exceptions for the portal backend.

These replace HTTPException in core/domain modules, allowing them to be
used from CLI, background workers, and tests without coupling to FastAPI.
The API layer catches these and translates to appropriate HTTP responses.
"""


class PortalError(Exception):
    """Base exception for all domain errors."""
    def __init__(self, message: str, code: str = "error"):
        self.message = message
        self.code = code
        super().__init__(message)


class ValidationError(PortalError):
    """Business rule validation failed (maps to 400)."""
    def __init__(self, message: str):
        super().__init__(message, code="validation_error")


class NotFoundError(PortalError):
    """Resource not found (maps to 404)."""
    def __init__(self, message: str = "资源不存在"):
        super().__init__(message, code="not_found")


class ExternalServiceError(PortalError):
    """External service (DS, etc.) failed (maps to 502)."""
    def __init__(self, message: str):
        super().__init__(message, code="external_service_error")


class PermissionDeniedError(PortalError):
    """Insufficient permissions (maps to 403)."""
    def __init__(self, message: str = "权限不足"):
        super().__init__(message, code="permission_denied")
