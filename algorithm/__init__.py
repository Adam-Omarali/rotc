"""
Liability Trading Algorithm Package

Adaptive market-making algorithm for RIT tender trading.
"""

from .config import AlgorithmConfig, ExecutionStrategy, DEFAULT_CONFIG
from .evaluator import TenderEvaluator, EvaluationScores, EvaluationResult
from .execution import ExecutionEngine, ExecutionPlan, ExecutionResult
from .order_manager import OrderManager, TrackedOrder, PositionState
from .trading_algorithm import TradingAlgorithm, TenderRecord, AlgorithmState, create_algorithm

__all__ = [
    # Config
    "AlgorithmConfig",
    "ExecutionStrategy",
    "DEFAULT_CONFIG",
    # Evaluator
    "TenderEvaluator",
    "EvaluationScores",
    "EvaluationResult",
    # Execution
    "ExecutionEngine",
    "ExecutionPlan",
    "ExecutionResult",
    # Order Manager
    "OrderManager",
    "TrackedOrder",
    "PositionState",
    # Main Algorithm
    "TradingAlgorithm",
    "TenderRecord",
    "AlgorithmState",
    "create_algorithm",
]
