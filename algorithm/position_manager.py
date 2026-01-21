"""
Position tracking and risk management.

This module manages current positions across all securities,
calculates net and gross exposure, and ensures compliance with position limits.
"""

from typing import Dict, List
from services.rit_client import RITClient
from services.types.security import Security


class PositionManager:
    """
    Manages positions and enforces risk limits.

    The PositionManager tracks current positions across CRZY and TAME,
    calculates net and gross exposure, and verifies compliance with limits.
    """

    def __init__(
        self,
        client: RITClient,
        net_limit: int = 100000,
        gross_limit: int = 250000,
        tickers: List[str] = None
    ):
        """
        Initialize the PositionManager.

        Args:
            client: RITClient instance for fetching position data
            net_limit: Maximum net position (long and short cancel out)
            gross_limit: Maximum gross position (long and short are additive)
            tickers: List of tickers to track (defaults to ['CRZY', 'TAME'])
        """
        self.client = client
        self.net_limit = net_limit
        self.gross_limit = gross_limit
        self.tickers = tickers or ['CRZY', 'TAME']

    def get_current_positions(self) -> Dict[str, int]:
        """
        Fetch current positions for all tracked securities.

        Returns:
            Dictionary mapping ticker to position size
        """
        positions = {}

        securities = self.client.get_securities()
        for security in securities:
            if security.ticker in self.tickers:
                positions[security.ticker] = security.size

        # Ensure all tracked tickers are in the dict (even if position is 0)
        for ticker in self.tickers:
            if ticker not in positions:
                positions[ticker] = 0

        return positions

    def calculate_net_exposure(self, positions: Dict[str, int]) -> int:
        """
        Calculate net exposure across all positions.

        Net exposure allows long and short positions to cancel each other out.
        For example:
        - CRZY: Long 50,000 | TAME: Long 25,000 = Net: 75,000
        - CRZY: Long 25,000 | TAME: Short 25,000 = Net: 0
        - CRZY: Short 35,000 | TAME: Long 125,000 = Net: 90,000

        Args:
            positions: Dictionary mapping ticker to position size

        Returns:
            Absolute value of net exposure
        """
        return abs(sum(positions.values()))

    def calculate_gross_exposure(self, positions: Dict[str, int]) -> int:
        """
        Calculate gross exposure across all positions.

        Gross exposure is additive - long and short positions both count.
        For example:
        - CRZY: Long 50,000 | TAME: Long 25,000 = Gross: 75,000
        - CRZY: Long 25,000 | TAME: Short 25,000 = Gross: 50,000
        - CRZY: Short 35,000 | TAME: Long 125,000 = Gross: 160,000

        Args:
            positions: Dictionary mapping ticker to position size

        Returns:
            Total gross exposure
        """
        return sum(abs(pos) for pos in positions.values())

    def check_position_limits(self, positions: Dict[str, int]) -> Dict[str, bool]:
        """
        Check if positions comply with net and gross limits.

        Args:
            positions: Dictionary mapping ticker to position size

        Returns:
            Dictionary with keys 'net_ok' and 'gross_ok' indicating compliance
        """
        net_exposure = self.calculate_net_exposure(positions)
        gross_exposure = self.calculate_gross_exposure(positions)

        return {
            'net_ok': net_exposure <= self.net_limit,
            'gross_ok': gross_exposure <= self.gross_limit,
            'net_exposure': net_exposure,
            'gross_exposure': gross_exposure,
            'net_limit': self.net_limit,
            'gross_limit': self.gross_limit,
        }

    def get_position_summary(self) -> Dict[str, any]:
        """
        Get a comprehensive summary of current positions and risk metrics.

        Returns:
            Dictionary containing positions, exposures, and limit compliance
        """
        positions = self.get_current_positions()
        limits = self.check_position_limits(positions)

        return {
            'positions': positions,
            'net_exposure': limits['net_exposure'],
            'gross_exposure': limits['gross_exposure'],
            'net_limit': self.net_limit,
            'gross_limit': self.gross_limit,
            'within_limits': limits['net_ok'] and limits['gross_ok'],
            'net_ok': limits['net_ok'],
            'gross_ok': limits['gross_ok'],
        }

    def has_open_positions(self) -> bool:
        """
        Check if there are any non-zero positions.

        Returns:
            True if any position is non-zero, False if all positions are flat
        """
        positions = self.get_current_positions()
        return any(pos != 0 for pos in positions.values())

    def get_unrealized_pnl(self) -> float:
        """
        Get total unrealized P&L across all positions.

        Returns:
            Total unrealized P&L in dollars
        """
        total_unrealized = 0.0

        securities = self.client.get_securities()
        for security in securities:
            if security.ticker in self.tickers:
                total_unrealized += security.unrealized or 0.0

        return total_unrealized

    def get_realized_pnl(self) -> float:
        """
        Get total realized P&L across all positions.

        Returns:
            Total realized P&L in dollars
        """
        total_realized = 0.0

        securities = self.client.get_securities()
        for security in securities:
            if security.ticker in self.tickers:
                total_realized += security.realized or 0.0

        return total_realized

    def get_total_pnl(self) -> float:
        """
        Get total P&L (realized + unrealized) across all positions.

        Returns:
            Total P&L in dollars
        """
        return self.get_realized_pnl() + self.get_unrealized_pnl()
