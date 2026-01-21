"""
Security and market data models for RIT API.

Includes models for securities, order book levels, and order books.
"""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class Security(BaseModel):
    """
    Represents a security (stock/asset) and its current state.

    Attributes:
        ticker: Security ticker symbol
        type: Type of security
        size: Position size (number of shares held)
        position: Current position value
        vwap: Volume-weighted average price
        nlv: Net liquidation value
        last: Last trade price
        bid: Current best bid price
        bid_size: Number of shares at bid
        ask: Current best ask price
        ask_size: Number of shares at ask
        volume: Total volume traded
        unrealized: Unrealized profit/loss
        realized: Realized profit/loss
    """

    model_config = ConfigDict(extra="ignore")

    ticker: str
    type: str
    size: int
    position: float
    vwap: float
    nlv: float
    last: float
    bid: float
    bid_size: int
    ask: float
    ask_size: int
    volume: int
    unrealized: float
    realized: float


class BookLevel(BaseModel):
    """
    Represents a single level in an order book.

    Attributes:
        price: Price at this level
        quantity: Total quantity available at this price
        quantity_filled: Amount already filled
        action: BUY or SELL
        trader: Trader ID (optional)
        order_id: Order ID for this level (optional)
    """

    model_config = ConfigDict(extra="ignore")

    price: float
    quantity: int
    quantity_filled: int
    action: str
    trader: Optional[str] = None
    order_id: Optional[int] = None


class SecurityBook(BaseModel):
    """
    Represents the full order book for a security.

    Contains separate lists of bid (buy) and ask (sell) levels,
    sorted by price.

    Attributes:
        bids: List of bid levels, sorted high to low
        asks: List of ask levels, sorted low to high
    """

    model_config = ConfigDict(extra="ignore")

    bids: List[BookLevel]
    asks: List[BookLevel]


class SecurityHistory(BaseModel):
    """
    Represents OHLC (Open, High, Low, Close) candle data.

    Attributes:
        tick: Tick timestamp
        open: Opening price
        high: Highest price
        low: Lowest price
        close: Closing price
        volume: Volume during this period
    """

    model_config = ConfigDict(extra="ignore")

    tick: int
    open: float
    high: float
    low: float
    close: float
    volume: int


class TimeAndSales(BaseModel):
    """
    Represents a time and sales (trade) entry.

    Attributes:
        tick: Tick when trade occurred
        price: Trade price
        quantity: Number of shares traded
    """

    model_config = ConfigDict(extra="ignore")

    tick: int
    price: float
    quantity: int
