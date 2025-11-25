"""
Custom exceptions
"""
from fastapi import HTTPException


class NotFoundException(HTTPException):
    """Resource not found exception"""
    def __init__(self, message: str = "Resource not found"):
        super().__init__(status_code=404, detail=message)


class ForbiddenException(HTTPException):
    """Access forbidden exception"""
    def __init__(self, message: str = "Access forbidden"):
        super().__init__(status_code=403, detail=message)


class BadRequestException(HTTPException):
    """Bad request exception"""
    def __init__(self, message: str = "Bad request"):
        super().__init__(status_code=400, detail=message)


class UnauthorizedException(HTTPException):
    """Unauthorized exception"""
    def __init__(self, message: str = "Unauthorized"):
        super().__init__(status_code=401, detail=message)


class AIServiceException(HTTPException):
    """AI service error exception"""
    def __init__(self, message: str = "AI service error"):
        super().__init__(status_code=500, detail=message)


class TranscriptionException(HTTPException):
    """Audio transcription error exception"""
    def __init__(self, message: str = "Transcription error"):
        super().__init__(status_code=500, detail=message)


class RateLimitException(HTTPException):
    """Rate limit exceeded exception"""
    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(status_code=429, detail=message)


