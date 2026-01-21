"""
RIT Trading API Services Package

Professional API handler for Rotman Interactive Trader (RIT).

Usage:
    from services import RITClient, OrderType, OrderAction

    with RITClient(api_key='YOUR_API_KEY') as client:
        tenders = client.get_tenders()
        order = client.submit_order(
            ticker='CRZY',
            order_type=OrderType.LIMIT,
            quantity=100,
            action=OrderAction.BUY,
            price=50.25
        )
"""

from .rit_client import RITClient

# Import commonly used types
from .types import (
    OrderType,
    OrderAction,
    OrderStatus,
    Tender,
    Security,
    SecurityBook,
    Order,
    CaseInfo,
)

# Import commonly used exceptions
from .exceptions import (
    RITAPIException,
    AuthenticationError,
    RateLimitError,
    ValidationError,
)

__all__ = [
    # Main client
    "RITClient",
    # Common enums
    "OrderType",
    "OrderAction",
    "OrderStatus",
    # Common types
    "Tender",
    "Security",
    "SecurityBook",
    "Order",
    "CaseInfo",
    # Common exceptions
    "RITAPIException",
    "AuthenticationError",
    "RateLimitError",
    "ValidationError",
]

__version__ = "1.0.0"
