"""
RIT API Exception Package

Exports all custom exception classes for convenient imports.
"""

from .api_exceptions import (
    RITAPIException,
    AuthenticationError,
    RateLimitError,
    ValidationError,
    NotFoundError,
    ServerError,
)

__all__ = [
    "RITAPIException",
    "AuthenticationError",
    "RateLimitError",
    "ValidationError",
    "NotFoundError",
    "ServerError",
]
