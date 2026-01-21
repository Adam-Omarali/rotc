"""
Common data models for RIT API.

Includes models for case information and other shared data structures.
"""

from pydantic import BaseModel, ConfigDict


class CaseInfo(BaseModel):
    """
    Represents information about the current trading case.

    Attributes:
        name: Name of the case
        period: Current trading period
        tick: Current tick within the period
        ticks_per_period: Number of ticks in each period
        total_periods: Total number of periods in the case
        status: Current case status (e.g., "ACTIVE", "STOPPED")
        is_enforce_trading_limits: Whether trading limits are enforced
    """

    model_config = ConfigDict(extra="ignore")

    name: str
    period: int
    tick: int
    ticks_per_period: int
    total_periods: int
    status: str
    is_enforce_trading_limits: bool
