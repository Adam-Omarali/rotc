"""
Tender Offer Arbitrage Algorithm

This module implements a trading algorithm for the Liability Trading 3 (LT3) case,
focused on evaluating and executing tender offers with risk management.
"""

from .tender_arbitrage import (
    verify_sufficient_liquidity,
    calculate_tender_pnl,
    should_accept_tender,
    should_place_limit_order,
)
from .position_manager import PositionManager
from .execution_engine import ExecutionEngine

__all__ = [
    "verify_sufficient_liquidity",
    "calculate_tender_pnl",
    "should_accept_tender",
    "should_place_limit_order",
    "PositionManager",
    "ExecutionEngine",
]
