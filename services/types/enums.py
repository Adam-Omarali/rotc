"""
Enum definitions for RIT API types.

Provides type-safe enumerations for order types, actions, and statuses.
"""

from enum import Enum


class OrderType(str, Enum):
    """
    Type of order to submit.

    Attributes:
        MARKET: Market order - executes immediately at current market price
        LIMIT: Limit order - executes only at specified price or better
    """

    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderAction(str, Enum):
    """
    Action to take in an order.

    Attributes:
        BUY: Buy/long position
        SELL: Sell/short position
    """

    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    """
    Current status of an order.

    Attributes:
        OPEN: Order is active and not yet filled
        TRANSACTED: Order has been filled
        CANCELLED: Order was cancelled before filling
        REJECTED: Order was rejected by the system
    """

    OPEN = "OPEN"
    TRANSACTED = "TRANSACTED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
