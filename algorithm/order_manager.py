"""
Order Manager

Monitors and manages open orders, handles repricing and position tracking.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from services import RITClient, OrderType, OrderAction
from services.types import Order, Security, OrderStatus

from .config import AlgorithmConfig, DEFAULT_CONFIG

logger = logging.getLogger(__name__)


@dataclass
class TrackedOrder:
    """Order being tracked by the manager."""
    order_id: int
    ticker: str
    action: OrderAction
    quantity: int
    price: float
    created_time: float  # Timestamp when order was placed
    tier: int  # Which execution tier (1, 2, or 3)
    reprice_count: int = 0


@dataclass
class PositionState:
    """Current state of a position."""
    ticker: str
    quantity: int
    entry_price: float
    accept_time: float
    tender_direction: str  # Original tender action


class OrderManager:
    """
    Manages open orders and positions.

    Responsibilities:
    - Track open limit orders
    - Monitor order fills
    - Reprice stale orders based on urgency
    - Track position states
    """

    def __init__(
        self,
        client: RITClient,
        config: AlgorithmConfig = DEFAULT_CONFIG,
    ):
        self.client = client
        self.config = config
        self.tracked_orders: Dict[int, TrackedOrder] = {}
        self.positions: Dict[str, PositionState] = {}
        self._cancelled_orders: Set[int] = set()

    def track_order(self, order: Order, tier: int) -> None:
        """
        Start tracking an order.

        Args:
            order: The order to track
            tier: Which execution tier (1, 2, or 3)
        """
        if order.type != OrderType.LIMIT:
            return  # Only track limit orders

        tracked = TrackedOrder(
            order_id=order.order_id,
            ticker=order.ticker,
            action=order.action,
            quantity=order.quantity,
            price=order.price,
            created_time=time.time(),
            tier=tier,
        )
        self.tracked_orders[order.order_id] = tracked
        logger.debug(f"Now tracking order {order.order_id}")

    def track_position(
        self,
        ticker: str,
        quantity: int,
        entry_price: float,
        tender_direction: str,
    ) -> None:
        """
        Start tracking a position from a tender.

        Args:
            ticker: Security ticker
            quantity: Position size
            entry_price: Price from tender
            tender_direction: Original tender action (BUY/SELL)
        """
        self.positions[ticker] = PositionState(
            ticker=ticker,
            quantity=quantity,
            entry_price=entry_price,
            accept_time=time.time(),
            tender_direction=tender_direction,
        )
        logger.info(f"Tracking position: {ticker} {quantity} @ {entry_price}")

    def get_current_positions(self) -> Dict[str, int]:
        """
        Get current position sizes from the API.

        Returns:
            Dict mapping ticker to position size
        """
        positions = {}
        try:
            securities = self.client.get_securities()
            for security in securities:
                positions[security.ticker] = security.size
        except Exception as e:
            logger.error(f"Failed to fetch positions: {e}")

        return positions

    def update_and_reprice(
        self,
        time_remaining: float,
    ) -> None:
        """
        Update order states and reprice stale orders.

        Args:
            time_remaining: Seconds remaining in the case
        """
        if not self.tracked_orders:
            return

        current_time = time.time()

        # Calculate urgency
        time_urgency = 1 - (time_remaining / self.config.case_duration_seconds)
        positions = self.get_current_positions()

        # Check position urgency
        max_position_utilization = 0
        for ticker, size in positions.items():
            utilization = abs(size) / self.config.net_position_limit
            max_position_utilization = max(max_position_utilization, utilization)

        urgency = max(time_urgency, max_position_utilization)

        # Get patience threshold based on urgency
        patience = self._get_patience_threshold(urgency)

        # Fetch current order states
        try:
            open_orders = self.client.get_orders(status="OPEN")
        except Exception as e:
            logger.error(f"Failed to fetch open orders: {e}")
            return

        open_order_ids = {o.order_id for o in open_orders}

        # Remove filled/cancelled orders from tracking
        to_remove = []
        for order_id in self.tracked_orders:
            if order_id not in open_order_ids and order_id not in self._cancelled_orders:
                to_remove.append(order_id)
                logger.debug(f"Order {order_id} filled or cancelled")

        for order_id in to_remove:
            del self.tracked_orders[order_id]

        # Check for stale orders that need repricing
        for order_id, tracked in list(self.tracked_orders.items()):
            if order_id in self._cancelled_orders:
                continue

            order_age = current_time - tracked.created_time

            if order_age > patience:
                logger.info(
                    f"Order {order_id} is stale (age={order_age:.1f}s, patience={patience:.1f}s), repricing"
                )
                self._reprice_order(tracked, urgency)

    def _get_patience_threshold(self, urgency: float) -> float:
        """Get patience threshold based on urgency level."""
        if urgency >= 0.8:
            return self.config.patience_urgent
        elif urgency >= 0.6:
            return self.config.patience_moderate
        elif urgency >= 0.4:
            return self.config.patience_moderate
        else:
            return self.config.patience_relaxed

    def _reprice_order(self, tracked: TrackedOrder, urgency: float) -> None:
        """
        Cancel and replace an order with a more aggressive price.

        Args:
            tracked: The order to reprice
            urgency: Current urgency level (0-1)
        """
        # Cancel the old order
        try:
            self.client.cancel_order(tracked.order_id)
            self._cancelled_orders.add(tracked.order_id)
            logger.debug(f"Cancelled order {tracked.order_id} for repricing")
        except Exception as e:
            logger.error(f"Failed to cancel order {tracked.order_id}: {e}")
            return

        # Remove from tracking
        if tracked.order_id in self.tracked_orders:
            del self.tracked_orders[tracked.order_id]

        # Get fresh order book
        try:
            book = self.client.get_security_book(tracked.ticker, limit=5)
        except Exception as e:
            logger.error(f"Failed to fetch order book: {e}")
            # Fall back to market order
            self._submit_market_order(tracked)
            return

        # Calculate new price
        tick_size = 0.01

        if tracked.action == OrderAction.SELL:
            if urgency >= 0.7:
                # High urgency: match best bid
                new_price = book.bids[0].price if book.bids else tracked.price
            else:
                # Lower urgency: improve by 1 tick
                new_price = round(tracked.price - tick_size, 2)
        else:  # BUY
            if urgency >= 0.7:
                # High urgency: match best ask
                new_price = book.asks[0].price if book.asks else tracked.price
            else:
                # Lower urgency: improve by 1 tick
                new_price = round(tracked.price + tick_size, 2)

        # Submit new order
        try:
            new_order = self.client.submit_order(
                ticker=tracked.ticker,
                order_type=OrderType.LIMIT,
                quantity=tracked.quantity,
                action=tracked.action,
                price=new_price,
            )

            # Track the new order
            new_tracked = TrackedOrder(
                order_id=new_order.order_id,
                ticker=tracked.ticker,
                action=tracked.action,
                quantity=tracked.quantity,
                price=new_price,
                created_time=time.time(),
                tier=tracked.tier,
                reprice_count=tracked.reprice_count + 1,
            )
            self.tracked_orders[new_order.order_id] = new_tracked

            logger.info(
                f"Repriced order: {tracked.order_id} -> {new_order.order_id}, "
                f"price {tracked.price} -> {new_price}"
            )

        except Exception as e:
            logger.error(f"Failed to place repriced order: {e}")
            # Fall back to market order if limit fails
            if urgency >= 0.7:
                self._submit_market_order(tracked)

    def _submit_market_order(self, tracked: TrackedOrder) -> None:
        """Submit a market order as fallback."""
        try:
            order = self.client.submit_order(
                ticker=tracked.ticker,
                order_type=OrderType.MARKET,
                quantity=tracked.quantity,
                action=tracked.action,
            )
            logger.info(f"Fallback market order placed: {order.order_id}")
        except Exception as e:
            logger.error(f"Market order fallback failed: {e}")

    def cancel_all_for_ticker(self, ticker: str) -> None:
        """
        Cancel all tracked orders for a ticker.

        Args:
            ticker: Security ticker
        """
        to_cancel = [
            order_id
            for order_id, tracked in self.tracked_orders.items()
            if tracked.ticker == ticker
        ]

        for order_id in to_cancel:
            try:
                self.client.cancel_order(order_id)
                self._cancelled_orders.add(order_id)
                del self.tracked_orders[order_id]
                logger.debug(f"Cancelled order {order_id}")
            except Exception as e:
                logger.error(f"Failed to cancel order {order_id}: {e}")

    def cancel_all_orders(self) -> None:
        """Cancel all tracked orders."""
        try:
            self.client.cancel_all_orders()
            self._cancelled_orders.update(self.tracked_orders.keys())
            self.tracked_orders.clear()
            logger.info("Cancelled all orders")
        except Exception as e:
            logger.error(f"Failed to cancel all orders: {e}")

    def get_unfilled_quantity(self, ticker: str) -> int:
        """
        Get total unfilled quantity for a ticker.

        Args:
            ticker: Security ticker

        Returns:
            Total unfilled quantity across all tracked orders
        """
        total = 0
        for tracked in self.tracked_orders.values():
            if tracked.ticker == ticker:
                total += tracked.quantity
        return total

    def check_position_health(self) -> List[str]:
        """
        Check if any positions need attention.

        Returns:
            List of tickers that need aggressive unwinding
        """
        alerts = []
        positions = self.get_current_positions()

        for ticker, size in positions.items():
            if abs(size) > self.config.large_position_threshold:
                alerts.append(ticker)
                logger.warning(f"Large position alert: {ticker} = {size}")

        # Also check unrealized P&L
        try:
            securities = self.client.get_securities()
            for security in securities:
                if security.unrealized < self.config.stop_loss_threshold:
                    if security.ticker not in alerts:
                        alerts.append(security.ticker)
                    logger.warning(
                        f"Stop loss alert: {security.ticker} unrealized = {security.unrealized}"
                    )
        except Exception as e:
            logger.error(f"Failed to check P&L: {e}")

        return alerts
