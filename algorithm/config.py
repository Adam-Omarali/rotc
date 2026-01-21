"""
Trading Algorithm Configuration

Tunable constants and parameters for the liability trading algorithm.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Tuple


class ExecutionStrategy(str, Enum):
    """Execution strategy based on tender quality."""
    PATIENT_OPTIMAL = "PATIENT_OPTIMAL"
    BALANCED = "BALANCED"
    AGGRESSIVE_LOCK = "AGGRESSIVE_LOCK"


@dataclass(frozen=True)
class AlgorithmConfig:
    """
    Configuration parameters for the trading algorithm.

    All parameters can be tuned for optimization between competition rounds.
    """

    # === Tender Evaluation Weights ===
    weight_ils: float = 0.40  # Immediate Liquidity Score weight
    weight_sqs: float = 0.25  # Spread Quality Score weight
    weight_obbs: float = 0.20  # Order Book Balance Score weight
    weight_plr: float = 0.15  # Position Limit Risk weight

    # === Acceptance Thresholds ===
    accept_threshold_high: float = 70.0
    accept_threshold_medium: float = 55.0
    accept_threshold_low: float = 40.0

    # === Position Limits ===
    net_position_limit: int = 100000
    gross_position_limit: int = 250000

    # === Order Size Limits ===
    crzy_order_limit: int = 25000
    tame_order_limit: int = 10000

    # === Transaction Costs ===
    transaction_cost_per_share: float = 0.02

    # === Timing Parameters ===
    case_duration_seconds: float = 300.0  # 5 minutes
    emergency_time_threshold: float = 30.0  # seconds remaining
    monitor_interval: float = 2.0  # seconds between monitoring cycles
    main_loop_interval: float = 0.5  # seconds between main loop iterations

    # === Repricing Patience Thresholds (seconds) ===
    patience_urgent: float = 5.0
    patience_moderate: float = 15.0
    patience_relaxed: float = 30.0

    # === Risk Thresholds ===
    stop_loss_threshold: float = -5000.0  # dollars
    large_position_threshold: int = 80000

    # === Order Book Analysis ===
    min_book_depth: int = 3
    max_acceptable_spread: float = 0.50

    # === Max Tenders ===
    max_tenders: int = 5

    def get_order_limit(self, ticker: str) -> int:
        """Get order size limit for a ticker."""
        return self.crzy_order_limit if ticker == "CRZY" else self.tame_order_limit

    def get_tier_splits(self, strategy: ExecutionStrategy) -> Tuple[float, float, float]:
        """
        Get execution tier percentages for a given strategy.

        Returns:
            Tuple of (tier1_pct, tier2_pct, tier3_pct)
        """
        if strategy == ExecutionStrategy.PATIENT_OPTIMAL:
            return (0.25, 0.50, 0.25)
        elif strategy == ExecutionStrategy.BALANCED:
            return (0.40, 0.45, 0.15)
        else:  # AGGRESSIVE_LOCK
            return (0.60, 0.35, 0.05)

    def get_strategy_for_score(self, composite_score: float) -> ExecutionStrategy:
        """Determine execution strategy based on composite score."""
        if composite_score >= 80:
            return ExecutionStrategy.PATIENT_OPTIMAL
        elif composite_score >= 60:
            return ExecutionStrategy.BALANCED
        else:
            return ExecutionStrategy.AGGRESSIVE_LOCK


# Default configuration instance
DEFAULT_CONFIG = AlgorithmConfig()
