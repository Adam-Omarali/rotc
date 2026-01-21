"""
Custom exception classes for RIT API client.

Provides a hierarchy of exceptions for different API error scenarios.
"""

from typing import Optional


class RITAPIException(Exception):
    """
    Base exception for all RIT API errors.

    Attributes:
        message: Error message describing what went wrong
        status_code: HTTP status code if applicable
    """

    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)

    def __str__(self) -> str:
        if self.status_code:
            return f"[{self.status_code}] {self.message}"
        return self.message


class AuthenticationError(RITAPIException):
    """
    Raised when API authentication fails (HTTP 401).

    This typically occurs when:
    - API key is missing or invalid
    - API key doesn't match the RIT client configuration
    """

    def __init__(self, message: str = "Invalid API key. Ensure API key matches RIT client."):
        super().__init__(message, status_code=401)


class RateLimitError(RITAPIException):
    """
    Raised when API rate limit is exceeded (HTTP 429).

    Attributes:
        retry_after: Number of seconds to wait before retrying (from Retry-After header)
    """

    def __init__(self, message: str = "Rate limit exceeded", retry_after: Optional[int] = None):
        self.retry_after = retry_after
        super().__init__(message, status_code=429)

    def __str__(self) -> str:
        base_msg = super().__str__()
        if self.retry_after:
            return f"{base_msg}. Retry after {self.retry_after} seconds"
        return base_msg


class ValidationError(RITAPIException):
    """
    Raised when request validation fails (HTTP 400).

    This occurs when request parameters are invalid or missing required fields.
    """

    def __init__(self, message: str = "Bad request"):
        super().__init__(message, status_code=400)


class NotFoundError(RITAPIException):
    """
    Raised when requested resource is not found (HTTP 404).

    This occurs when trying to access orders, tenders, or securities that don't exist.
    """

    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, status_code=404)


class ServerError(RITAPIException):
    """
    Raised when the server encounters an error (HTTP 5xx).

    This indicates an issue with the RIT server itself.
    """

    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message, status_code=status_code)
