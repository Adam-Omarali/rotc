"""
Tender data models for RIT API.

Tenders represent trading opportunities that must be accepted or declined.
"""

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class Tender(BaseModel):
    """
    Represents a trading tender from the RIT API.

    A tender is a trading opportunity that requires a response (accept/decline)
    within a specified time period.

    Attributes:
        tender_id: Unique identifier for the tender
        period: Current trading period
        tick: Current tick within the period
        expires: Tick when the tender expires
        caption: Description of the tender
        quantity: Number of shares in the tender
        action: Action type (BUY or SELL)
        price: Price per share
        ticker: Security ticker symbol (optional)
        is_fixed_bid: Whether the tender has a fixed price (optional)
    """

    model_config = ConfigDict(extra="ignore")

    tender_id: int
    period: int
    tick: int
    expires: int
    caption: str
    quantity: int
    action: str
    price: float
    ticker: Optional[str] = None
    is_fixed_bid: Optional[bool] = None


class TenderResponse(BaseModel):
    """
    Response from accepting or declining a tender.

    Attributes:
        success: Whether the operation succeeded
        tender_id: ID of the tender that was acted upon (optional)
        message: Response message (optional)
    """

    model_config = ConfigDict(extra="ignore")

    success: bool
    tender_id: Optional[int] = None
    message: Optional[str] = None
