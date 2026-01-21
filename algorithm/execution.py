"""
Execution Engine

Handles tiered order execution for unwinding tender positions.
"""

import logging
import time
from dataclasses import dataclass
from typing import List, Optional

from services import RITClient, OrderType, OrderAction
from services.types import Tender, Order, SecurityBook

from .config import AlgorithmConfig, ExecutionStrategy, DEFAULT_CONFIG

logger = logging.getLogger(__name__)


@dataclass
class ExecutionPlan:
    """Plan for executing a tender position."""
    ticker: str
    total_quantity: int
    direction: OrderAction  # Direction to unwind (opposite of tender)
    strategy: ExecutionStrategy
    tier1_quantity: int
    tier2_quantity: int
    tier3_quantity: int


@dataclass
class ExecutionResult:
    """Result of an execution tier."""
    orders_placed: List[Order]
    total_quantity: int
    errors: List[str]


class ExecutionEngine:
    """
    Executes tender positions using a tiered approach.

    Tiers:
    - Tier 1: Market orders for immediate profit lock
    - Tier 2: Aggressive limit orders at best bid/ask
    - Tier 3: Passive limit orders for price improvement
    """

    def __init__(
        self,
        client: RITClient,
        config: AlgorithmConfig = DEFAULT_CONFIG,
    ):
        self.client = client
        self.config = config

    def create_execution_plan(
        self,
        tender: Tender,
        composite_score: float,
    ) -> ExecutionPlan:
        """
        Create an execution plan for a tender.

        Args:
            tender: The accepted tender
            composite_score: Score from tender evaluation

        Returns:
            ExecutionPlan with quantities for each tier
        """
        ticker = tender.ticker or "CRZY"
        quantity = tender.quantity

        # Determine direction: opposite of tender action
        if tender.action == "BUY":
            direction = OrderAction.SELL  # They bought from us, we need to sell
        else:
            direction = OrderAction.BUY  # They sold to us, we need to buy

        # Get strategy and tier splits
        strategy = self.config.get_strategy_for_score(composite_score)
        tier1_pct, tier2_pct, tier3_pct = self.config.get_tier_splits(strategy)

        tier1_qty = int(quantity * tier1_pct)
        tier2_qty = int(quantity * tier2_pct)
        tier3_qty = quantity - tier1_qty - tier2_qty  # Remainder to tier 3

        logger.info(
            f"Execution plan for {ticker}: {strategy.value} - "
            f"T1={tier1_qty}, T2={tier2_qty}, T3={tier3_qty}"
        )

        return ExecutionPlan(
            ticker=ticker,
            total_quantity=quantity,
            direction=direction,
            strategy=strategy,
            tier1_quantity=tier1_qty,
            tier2_quantity=tier2_qty,
            tier3_quantity=tier3_qty,
        )

    def execute_plan(
        self,
        plan: ExecutionPlan,
        time_remaining: float,
    ) -> List[ExecutionResult]:
        """
        Execute all tiers of the plan.

        Args:
            plan: The execution plan
            time_remaining: Seconds remaining in the case

        Returns:
            List of ExecutionResults for each tier
        """
        results = []

        # Execute Tier 1: Market orders
        if plan.tier1_quantity > 0:
            result = self.execute_tier1(plan.ticker, plan.tier1_quantity, plan.direction)
            results.append(result)
            time.sleep(0.5)  # Brief delay between tiers

        # Execute Tier 2: Aggressive limit orders
        if plan.tier2_quantity > 0:
            result = self.execute_tier2(plan.ticker, plan.tier2_quantity, plan.direction)
            results.append(result)
            time.sleep(0.3)

        # Execute Tier 3: Passive limit orders (only if we have time)
        if plan.tier3_quantity > 0 and time_remaining > 60:
            result = self.execute_tier3(plan.ticker, plan.tier3_quantity, plan.direction)
            results.append(result)
        elif plan.tier3_quantity > 0:
            # Not enough time for passive orders, add to tier 2
            logger.info(f"Time pressure - converting tier3 to aggressive orders")
            result = self.execute_tier2(plan.ticker, plan.tier3_quantity, plan.direction)
            results.append(result)

        return results

    def execute_tier1(
        self,
        ticker: str,
        quantity: int,
        direction: OrderAction,
    ) -> ExecutionResult:
        """
        Execute Tier 1: Market orders for immediate execution.

        Args:
            ticker: Security ticker
            quantity: Total quantity to execute
            direction: BUY or SELL

        Returns:
            ExecutionResult with placed orders
        """
        logger.info(f"Tier 1: Executing {quantity} {ticker} {direction.value} as MARKET")

        orders = []
        errors = []
        order_limit = self.config.get_order_limit(ticker)
        remaining = quantity

        while remaining > 0:
            order_size = min(remaining, order_limit)

            try:
                order = self.client.submit_order(
                    ticker=ticker,
                    order_type=OrderType.MARKET,
                    quantity=order_size,
                    action=direction,
                )
                orders.append(order)
                logger.debug(f"Tier 1 order placed: {order.order_id} for {order_size}")
            except Exception as e:
                error_msg = f"Tier 1 order failed: {e}"
                logger.error(error_msg)
                errors.append(error_msg)

            remaining -= order_size
            time.sleep(0.1)  # Small delay between orders

        return ExecutionResult(
            orders_placed=orders,
            total_quantity=quantity - remaining,
            errors=errors,
        )

    def execute_tier2(
        self,
        ticker: str,
        quantity: int,
        direction: OrderAction,
    ) -> ExecutionResult:
        """
        Execute Tier 2: Aggressive limit orders at best bid/ask.

        Args:
            ticker: Security ticker
            quantity: Total quantity to execute
            direction: BUY or SELL

        Returns:
            ExecutionResult with placed orders
        """
        logger.info(f"Tier 2: Executing {quantity} {ticker} {direction.value} as aggressive LIMIT")

        orders = []
        errors = []
        order_limit = self.config.get_order_limit(ticker)

        # Get fresh order book
        try:
            book = self.client.get_security_book(ticker, limit=5)
        except Exception as e:
            logger.error(f"Failed to fetch order book: {e}")
            # Fall back to market orders
            return self.execute_tier1(ticker, quantity, direction)

        # Determine target price
        if direction == OrderAction.SELL:
            # Selling: place at best bid to get filled quickly
            if book.bids:
                target_price = book.bids[0].price
            else:
                logger.warning("No bids available, falling back to market order")
                return self.execute_tier1(ticker, quantity, direction)
        else:
            # Buying: place at best ask to get filled quickly
            if book.asks:
                target_price = book.asks[0].price
            else:
                logger.warning("No asks available, falling back to market order")
                return self.execute_tier1(ticker, quantity, direction)

        # Split into multiple orders
        num_orders = max(1, (quantity + order_limit - 1) // order_limit)
        base_size = quantity // num_orders
        remainder = quantity % num_orders

        for i in range(num_orders):
            order_size = base_size + (1 if i < remainder else 0)
            if order_size <= 0:
                continue

            try:
                order = self.client.submit_order(
                    ticker=ticker,
                    order_type=OrderType.LIMIT,
                    quantity=order_size,
                    action=direction,
                    price=target_price,
                )
                orders.append(order)
                logger.debug(f"Tier 2 order placed: {order.order_id} for {order_size} @ {target_price}")
            except Exception as e:
                error_msg = f"Tier 2 order failed: {e}"
                logger.error(error_msg)
                errors.append(error_msg)

        return ExecutionResult(
            orders_placed=orders,
            total_quantity=sum(o.quantity for o in orders),
            errors=errors,
        )

    def execute_tier3(
        self,
        ticker: str,
        quantity: int,
        direction: OrderAction,
    ) -> ExecutionResult:
        """
        Execute Tier 3: Passive limit orders for price improvement.

        Args:
            ticker: Security ticker
            quantity: Total quantity to execute
            direction: BUY or SELL

        Returns:
            ExecutionResult with placed orders
        """
        logger.info(f"Tier 3: Executing {quantity} {ticker} {direction.value} as passive LIMIT")

        orders = []
        errors = []
        order_limit = self.config.get_order_limit(ticker)
        tick_size = 0.01

        # Get fresh order book
        try:
            book = self.client.get_security_book(ticker, limit=5)
        except Exception as e:
            logger.error(f"Failed to fetch order book: {e}")
            return self.execute_tier2(ticker, quantity, direction)

        # Determine target price (1-2 ticks better than best)
        if direction == OrderAction.SELL:
            # Selling: place slightly above best bid for price improvement
            if book.bids:
                target_price = round(book.bids[0].price + (1.5 * tick_size), 2)
            else:
                return self.execute_tier2(ticker, quantity, direction)
        else:
            # Buying: place slightly below best ask for price improvement
            if book.asks:
                target_price = round(book.asks[0].price - (1.5 * tick_size), 2)
            else:
                return self.execute_tier2(ticker, quantity, direction)

        # Split into multiple orders
        num_orders = max(1, (quantity + order_limit - 1) // order_limit)
        base_size = quantity // num_orders
        remainder = quantity % num_orders

        for i in range(num_orders):
            order_size = base_size + (1 if i < remainder else 0)
            if order_size <= 0:
                continue

            try:
                order = self.client.submit_order(
                    ticker=ticker,
                    order_type=OrderType.LIMIT,
                    quantity=order_size,
                    action=direction,
                    price=target_price,
                )
                orders.append(order)
                logger.debug(f"Tier 3 order placed: {order.order_id} for {order_size} @ {target_price}")
            except Exception as e:
                error_msg = f"Tier 3 order failed: {e}"
                logger.error(error_msg)
                errors.append(error_msg)

        return ExecutionResult(
            orders_placed=orders,
            total_quantity=sum(o.quantity for o in orders),
            errors=errors,
        )

    def emergency_liquidation(self, positions: dict[str, int]) -> List[ExecutionResult]:
        """
        Emergency liquidation of all positions with market orders.

        Used when time is running out.

        Args:
            positions: Dict mapping ticker to position size

        Returns:
            List of ExecutionResults
        """
        logger.warning("EMERGENCY LIQUIDATION initiated")

        results = []

        # First cancel all open orders
        try:
            self.client.cancel_all_orders()
            logger.info("Cancelled all open orders")
        except Exception as e:
            logger.error(f"Failed to cancel orders: {e}")

        # Market order all positions
        for ticker, position in positions.items():
            if position == 0:
                continue

            direction = OrderAction.SELL if position > 0 else OrderAction.BUY
            quantity = abs(position)

            logger.info(f"Emergency liquidation: {direction.value} {quantity} {ticker}")
            result = self.execute_tier1(ticker, quantity, direction)
            results.append(result)

        return results
