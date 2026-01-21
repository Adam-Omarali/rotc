"""
Order data models for RIT API.

Includes models for orders, order requests, and order responses.
"""

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from .enums import OrderType, OrderAction, OrderStatus


class Order(BaseModel):
    """
    Represents a trading order.

    Attributes:
        order_id: Unique identifier for the order
        period: Trading period when order was placed
        tick: Tick when order was placed
        trader: Trader ID who placed the order (optional)
        trader_id: Alternative trader ID field (optional)
        ticker: Security ticker symbol
        type: Order type (MARKET or LIMIT)
        quantity: Number of shares
        action: BUY or SELL
        price: Limit price (None for market orders)
        quantity_filled: Number of shares filled so far
        vwap: Volume-weighted average price of fills
        status: Current order status
    """

    model_config = ConfigDict(extra="ignore")

    order_id: int
    period: int
    tick: int
    trader: Optional[str] = None
    trader_id: Optional[str] = None
    ticker: str
    type: OrderType
    quantity: int
    action: OrderAction
    price: Optional[float] = None
    quantity_filled: int
    vwap: Optional[float] = None
    status: OrderStatus


class OrderRequest(BaseModel):
    """
    Request model for submitting a new order.

    Attributes:
        ticker: Security ticker symbol
        type: Order type (MARKET or LIMIT)
        quantity: Number of shares to trade
        action: BUY or SELL
        price: Limit price (required for LIMIT orders, ignored for MARKET)
        dry_run: If True, validate but don't execute (optional)
    """

    model_config = ConfigDict(extra="ignore")

    ticker: str
    type: OrderType
    quantity: int
    action: OrderAction
    price: Optional[float] = None
    dry_run: Optional[bool] = Field(default=False, alias="dry_run")


class CancelResponse(BaseModel):
    """
    Response from cancelling an order.

    Attributes:
        success: Whether cancellation succeeded
        order_id: ID of cancelled order (optional)
        message: Response message (optional)
    """

    model_config = ConfigDict(extra="ignore")

    success: bool
    order_id: Optional[int] = None
    message: Optional[str] = None


class BulkCancelResponse(BaseModel):
    """
    Response from bulk order cancellation.

    Attributes:
        cancelled_order_ids: List of successfully cancelled order IDs
    """

    model_config = ConfigDict(extra="ignore")

    cancelled_order_ids: list[int] = Field(default_factory=list)
