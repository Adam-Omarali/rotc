"""
Main Trading Algorithm

Orchestrates tender evaluation, execution, and order management.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from services import RITClient
from services.types import Tender, Order

from .config import AlgorithmConfig, ExecutionStrategy, DEFAULT_CONFIG
from .evaluator import TenderEvaluator, EvaluationResult
from .execution import ExecutionEngine, ExecutionPlan
from .order_manager import OrderManager

logger = logging.getLogger(__name__)


@dataclass
class TenderRecord:
    """Record of a processed tender."""
    tender_id: int
    ticker: str
    quantity: int
    price: float
    action: str
    accepted: bool
    composite_score: float
    reason: str
    accept_time: Optional[float] = None
    execution_complete: bool = False
    realized_pnl: float = 0.0


@dataclass
class AlgorithmState:
    """Current state of the trading algorithm."""
    start_time: float = 0.0
    tender_count: int = 0
    processed_tender_ids: set = field(default_factory=set)
    tender_records: List[TenderRecord] = field(default_factory=list)
    emergency_mode: bool = False
    running: bool = False


class TradingAlgorithm:
    """
    Main trading algorithm orchestrator.

    Coordinates:
    - Tender detection and evaluation
    - Execution planning and order submission
    - Order monitoring and repricing
    - Emergency liquidation
    """

    def __init__(
        self,
        client: RITClient,
        config: AlgorithmConfig = DEFAULT_CONFIG,
    ):
        self.client = client
        self.config = config

        # Initialize components
        self.evaluator = TenderEvaluator(client, config)
        self.executor = ExecutionEngine(client, config)
        self.order_manager = OrderManager(client, config)

        # State
        self.state = AlgorithmState()

    def run(self) -> None:
        """
        Main trading loop.

        Runs until case ends or is stopped.
        """
        self.state.running = True
        self.state.start_time = time.time()

        logger.info("=" * 60)
        logger.info("TRADING ALGORITHM STARTED")
        logger.info(f"Config: max_tenders={self.config.max_tenders}, "
                   f"case_duration={self.config.case_duration_seconds}s")
        logger.info("=" * 60)

        last_monitor_time = 0.0

        try:
            while self.state.running:
                elapsed = time.time() - self.state.start_time
                time_remaining = self.config.case_duration_seconds - elapsed

                # Check if case is over
                if time_remaining <= 0:
                    logger.info("Case time expired")
                    break

                # Check case status from API
                try:
                    case_info = self.client.get_case_info()
                    if case_info.status != "ACTIVE":
                        logger.info(f"Case status: {case_info.status}, stopping")
                        break
                except Exception as e:
                    logger.warning(f"Could not fetch case info: {e}")

                # Emergency liquidation trigger
                if time_remaining <= self.config.emergency_time_threshold:
                    if not self.state.emergency_mode:
                        self._trigger_emergency_liquidation()
                    time.sleep(0.5)
                    continue

                # Check for new tenders
                if self.state.tender_count < self.config.max_tenders:
                    self._check_and_process_tenders(time_remaining)

                # Monitor and adjust orders (every monitor_interval seconds)
                if elapsed - last_monitor_time >= self.config.monitor_interval:
                    self._monitor_positions(time_remaining)
                    last_monitor_time = elapsed

                # Main loop sleep
                time.sleep(self.config.main_loop_interval)

        except KeyboardInterrupt:
            logger.info("Algorithm interrupted by user")
        except Exception as e:
            logger.error(f"Algorithm error: {e}", exc_info=True)
        finally:
            self._shutdown()

    def stop(self) -> None:
        """Stop the algorithm gracefully."""
        logger.info("Stop requested")
        self.state.running = False

    def _check_and_process_tenders(self, time_remaining: float) -> None:
        """Check for new tenders and process them."""
        try:
            tenders = self.client.get_tenders()
        except Exception as e:
            logger.error(f"Failed to fetch tenders: {e}")
            return

        for tender in tenders:
            # Skip already processed tenders
            if tender.tender_id in self.state.processed_tender_ids:
                continue

            logger.info(
                f"New tender detected: ID={tender.tender_id}, "
                f"{tender.action} {tender.quantity} {tender.ticker or 'CRZY'} @ {tender.price}"
            )

            self._process_tender(tender, time_remaining)

    def _process_tender(self, tender: Tender, time_remaining: float) -> None:
        """
        Process a single tender: evaluate, decide, and execute.

        Args:
            tender: The tender to process
            time_remaining: Seconds remaining in the case
        """
        self.state.processed_tender_ids.add(tender.tender_id)
        ticker = tender.ticker or "CRZY"

        # Get current positions
        positions = self.order_manager.get_current_positions()

        # Safety check
        is_safe, safety_reason = self.evaluator.validate_trade_safety(tender)
        if not is_safe:
            logger.warning(f"Safety check failed: {safety_reason}")
            self._decline_tender(tender, 0.0, safety_reason)
            return

        # Evaluate tender
        result = self.evaluator.evaluate(tender, positions, time_remaining)

        if result.accept:
            self._accept_and_execute(tender, result, time_remaining)
        else:
            self._decline_tender(tender, result.scores.composite, result.reason)

    def _accept_and_execute(
        self,
        tender: Tender,
        result: EvaluationResult,
        time_remaining: float,
    ) -> None:
        """
        Accept a tender and execute the position.

        Args:
            tender: The tender to accept
            result: Evaluation result with scores
            time_remaining: Seconds remaining
        """
        ticker = tender.ticker or "CRZY"

        # Accept the tender
        try:
            self.client.accept_tender(tender.tender_id)
            logger.info(f"ACCEPTED tender {tender.tender_id}")
        except Exception as e:
            logger.error(f"Failed to accept tender: {e}")
            self._record_tender(tender, False, result.scores.composite, f"Accept failed: {e}")
            return

        self.state.tender_count += 1

        # Record the tender
        self._record_tender(tender, True, result.scores.composite, result.reason)

        # Track the position
        self.order_manager.track_position(
            ticker=ticker,
            quantity=tender.quantity,
            entry_price=tender.price,
            tender_direction=tender.action,
        )

        # Create and execute plan
        plan = self.executor.create_execution_plan(tender, result.scores.composite)
        results = self.executor.execute_plan(plan, time_remaining)

        # Track limit orders
        for tier_idx, exec_result in enumerate(results, start=1):
            for order in exec_result.orders_placed:
                self.order_manager.track_order(order, tier=tier_idx)

        logger.info(
            f"Execution complete for tender {tender.tender_id}: "
            f"{sum(r.total_quantity for r in results)} shares across {len(results)} tiers"
        )

    def _decline_tender(
        self,
        tender: Tender,
        composite_score: float,
        reason: str,
    ) -> None:
        """
        Decline a tender.

        Args:
            tender: The tender to decline
            composite_score: Evaluation score
            reason: Reason for declining
        """
        try:
            self.client.decline_tender(tender.tender_id)
            logger.info(f"DECLINED tender {tender.tender_id}: {reason}")
        except Exception as e:
            logger.error(f"Failed to decline tender: {e}")

        self._record_tender(tender, False, composite_score, reason)

    def _record_tender(
        self,
        tender: Tender,
        accepted: bool,
        composite_score: float,
        reason: str,
    ) -> None:
        """Record a tender decision for logging."""
        record = TenderRecord(
            tender_id=tender.tender_id,
            ticker=tender.ticker or "CRZY",
            quantity=tender.quantity,
            price=tender.price,
            action=tender.action,
            accepted=accepted,
            composite_score=composite_score,
            reason=reason,
            accept_time=time.time() if accepted else None,
        )
        self.state.tender_records.append(record)

    def _monitor_positions(self, time_remaining: float) -> None:
        """
        Monitor positions and adjust orders.

        Args:
            time_remaining: Seconds remaining in the case
        """
        # Update and reprice stale orders
        self.order_manager.update_and_reprice(time_remaining)

        # Check position health
        alerts = self.order_manager.check_position_health()
        if alerts:
            for ticker in alerts:
                logger.warning(f"Position health alert for {ticker}")
                # Could trigger aggressive unwinding here

    def _trigger_emergency_liquidation(self) -> None:
        """Trigger emergency liquidation of all positions."""
        logger.warning("=" * 60)
        logger.warning("EMERGENCY LIQUIDATION TRIGGERED")
        logger.warning("=" * 60)

        self.state.emergency_mode = True

        positions = self.order_manager.get_current_positions()
        self.executor.emergency_liquidation(positions)

    def _shutdown(self) -> None:
        """Clean shutdown of the algorithm."""
        self.state.running = False

        logger.info("=" * 60)
        logger.info("ALGORITHM SHUTDOWN")
        logger.info(f"Total tenders processed: {len(self.state.tender_records)}")
        logger.info(f"Tenders accepted: {self.state.tender_count}")
        logger.info("=" * 60)

        # Print summary
        self._print_summary()

    def _print_summary(self) -> None:
        """Print summary of trading session."""
        logger.info("\n--- TENDER SUMMARY ---")
        for record in self.state.tender_records:
            status = "ACCEPTED" if record.accepted else "DECLINED"
            logger.info(
                f"  Tender {record.tender_id}: {status} "
                f"({record.action} {record.quantity} {record.ticker} @ {record.price}) "
                f"Score={record.composite_score:.1f} - {record.reason}"
            )

        # Final positions
        try:
            securities = self.client.get_securities()
            logger.info("\n--- FINAL POSITIONS ---")
            for security in securities:
                if security.size != 0:
                    logger.info(
                        f"  {security.ticker}: {security.size} shares, "
                        f"Unrealized={security.unrealized:.2f}, "
                        f"Realized={security.realized:.2f}"
                    )

            # Total P&L
            total_unrealized = sum(s.unrealized for s in securities)
            total_realized = sum(s.realized for s in securities)
            logger.info(f"\n--- TOTAL P&L ---")
            logger.info(f"  Unrealized: ${total_unrealized:.2f}")
            logger.info(f"  Realized: ${total_realized:.2f}")
            logger.info(f"  Total: ${total_unrealized + total_realized:.2f}")
        except Exception as e:
            logger.error(f"Could not fetch final positions: {e}")


def create_algorithm(
    api_key: str,
    config: Optional[AlgorithmConfig] = None,
    **client_kwargs,
) -> TradingAlgorithm:
    """
    Factory function to create a configured trading algorithm.

    Args:
        api_key: RIT API key
        config: Algorithm configuration (uses defaults if not provided)
        **client_kwargs: Additional arguments for RITClient

    Returns:
        Configured TradingAlgorithm instance
    """
    client = RITClient(api_key=api_key, **client_kwargs)
    config = config or DEFAULT_CONFIG

    return TradingAlgorithm(client=client, config=config)
