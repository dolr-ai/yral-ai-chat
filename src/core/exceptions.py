"""
Custom exceptions with enhanced error details
"""

from fastapi import HTTPException


class BaseAPIException(HTTPException):
    """Base exception for API errors with detailed information"""

    def __init__(
        self,
        status_code: int,
        message: str,
        error_code: str,
        details: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ):
        self.error_code = error_code
        self.details = details or {}
        super().__init__(
            status_code=status_code,
            detail={"error": error_code, "message": message, "details": self.details},
            headers=headers,
        )


class NotFoundException(BaseAPIException):
    """Resource not found exception"""

    def __init__(self, message: str = "Resource not found", details: dict[str, object] | None = None):
        super().__init__(status_code=404, message=message, error_code="not_found", details=details)


class ForbiddenException(BaseAPIException):
    """Access forbidden exception"""

    def __init__(self, message: str = "Access forbidden", details: dict[str, object] | None = None):
        super().__init__(status_code=403, message=message, error_code="forbidden", details=details)


class BadRequestException(BaseAPIException):
    """Bad request exception"""

    def __init__(self, message: str = "Bad request", details: dict[str, object] | None = None):
        super().__init__(status_code=400, message=message, error_code="bad_request", details=details)


class UnauthorizedException(BaseAPIException):
    """Unauthorized exception"""

    def __init__(self, message: str = "Unauthorized", details: dict[str, object] | None = None):
        super().__init__(status_code=401, message=message, error_code="unauthorized", details=details)


class AIServiceException(BaseAPIException):
    """AI service error exception"""

    def __init__(self, message: str = "AI service error", details: dict[str, object] | None = None):
        super().__init__(status_code=500, message=message, error_code="ai_service_error", details=details)


class TranscriptionException(BaseAPIException):
    """Audio transcription error exception"""

    def __init__(self, message: str = "Transcription error", details: dict[str, object] | None = None):
        super().__init__(status_code=500, message=message, error_code="transcription_error", details=details)


class RateLimitException(BaseAPIException):
    """Rate limit exceeded exception"""

    def __init__(self, message: str = "Rate limit exceeded", details: dict[str, object] | None = None):
        super().__init__(status_code=429, message=message, error_code="rate_limit_exceeded", details=details)


class ValidationException(BaseAPIException):
    """Validation error exception"""

    def __init__(self, message: str = "Validation error", details: dict[str, object] | None = None):
        super().__init__(status_code=422, message=message, error_code="validation_error", details=details)


class DatabaseException(BaseAPIException):
    """Database error exception"""

    def __init__(self, message: str = "Database error", details: dict[str, object] | None = None):
        super().__init__(status_code=500, message=message, error_code="database_error", details=details)


class ConflictException(BaseAPIException):
    """Resource conflict exception"""

    def __init__(self, message: str = "Resource conflict", details: dict[str, object] | None = None):
        super().__init__(status_code=409, message=message, error_code="conflict", details=details)


class ServiceUnavailableException(BaseAPIException):
    """Service unavailable exception"""

    def __init__(
        self,
        message: str = "Service unavailable",
        details: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(
            status_code=503, message=message, error_code="service_unavailable", details=details, headers=headers
        )
