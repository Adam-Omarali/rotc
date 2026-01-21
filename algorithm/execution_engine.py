"""
Order execution and position unwinding logic.

This module handles the execution of trades to unwind positions acquired
through tender offers, managing both market and limit orders.
"""

import logging
from typing import List, Optional
from services.rit_client import RITClient
from services.types.order import Order
from services.types.enums import OrderType, OrderAction
from services.types.tender import Tender


logger = logging.getLogger(__name__)


class ExecutionEngine:
    """
    Manages order execution for unwinding tender positions.

    The ExecutionEngine handles:
    - Market orders for urgent position closing (to avoid fines)
    - Limit orders for optimal execution at specific price levels
    - Order size constraints (CRZY: 25,000 max, TAME: 10,000 max per order)
    """

    # Maximum order sizes per security
    MAX_ORDER_SIZES = {
        'CRZY': 25000,
        'TAME': 10000,
    }

    def __init__(self, client: RITClient):
        """
        Initialize the ExecutionEngine.

        Args:
            client: RITClient instance for submitting orders
        """
        self.client = client

    def _get_max_order_size(self, ticker: str) -> int:
        """
        Get the maximum order size for a given ticker.

        Args:
            ticker: Security ticker

        Returns:
            Maximum order size for this security
        """
        return self.MAX_ORDER_SIZES.get(ticker, 10000)

    def _split_into_orders(self, ticker: str, total_quantity: int) -> List[int]:
        """
        Split a large quantity into multiple orders respecting size limits.

        Args:
            ticker: Security ticker
            total_quantity: Total quantity to trade

        Returns:
            List of order quantities
        """
        max_size = self._get_max_order_size(ticker)
        orders = []

        remaining = abs(total_quantity)
        while remaining > 0:
            order_size = min(remaining, max_size)
            orders.append(order_size)
            remaining -= order_size

        return orders

    def place_limit_order(
        self,
        ticker: str,
        quantity: int,
        action: OrderAction,
        price: float
    ) -> List[Order]:
        """
        Place limit order(s) to unwind a position.

        If the quantity exceeds the maximum order size for the security,
        it will be split into multiple orders.

        Args:
            ticker: Security ticker
            quantity: Total quantity to trade (positive value)
            action: BUY or SELL
            price: Limit price

        Returns:
            List of submitted orders
        """
        orders = []
        order_quantities = self._split_into_orders(ticker, quantity)

        for qty in order_quantities:
            try:
                order = self.client.submit_order(
                    ticker=ticker,
                    order_type=OrderType.LIMIT,
                    quantity=qty,
                    action=action,
                    price=price
                )
                orders.append(order)
                logger.info(
                    f"Placed limit {action.value} order: {qty} {ticker} @ ${price:.2f} "
                    f"(Order ID: {order.order_id})"
                )
            except Exception as e:
                logger.error(f"Failed to place limit order for {ticker}: {e}")

        return orders

    def place_market_order(
        self,
        ticker: str,
        quantity: int,
        action: OrderAction
    ) -> List[Order]:
        """
        Place market order(s) to unwind a position urgently.

        Market orders should only be used for closing positions to avoid fines,
        as they may have unfavorable execution prices.

        If the quantity exceeds the maximum order size for the security,
        it will be split into multiple orders.

        Args:
            ticker: Security ticker
            quantity: Total quantity to trade (positive value)
            action: BUY or SELL

        Returns:
            List of submitted orders
        """
        orders = []
        order_quantities = self._split_into_orders(ticker, quantity)

        for qty in order_quantities:
            try:
                order = self.client.submit_order(
                    ticker=ticker,
                    order_type=OrderType.MARKET,
                    quantity=qty,
                    action=action
                )
                orders.append(order)
                logger.info(
                    f"Placed market {action.value} order: {qty} {ticker} "
                    f"(Order ID: {order.order_id})"
                )
            except Exception as e:
                logger.error(f"Failed to place market order for {ticker}: {e}")

        return orders

    def unwind_position_with_limits(
        self,
        tender: Tender,
        limit_offset: float = 0.05
    ) -> List[Order]:
        """
        Unwind a tender position using limit orders.

        Places limit orders at ±5 cents (or custom offset) from the tender price
        to unwind the position acquired from accepting the tender.

        Args:
            tender: The tender that was accepted
            limit_offset: Price offset from tender price (default: 0.05 = 5 cents)

        Returns:
            List of submitted orders
        """
        ticker = tender.ticker or ""

        if tender.action == "SELL":
            # Institution sold to us (we bought from them)
            # Now we need to sell back, so place limit sell at tender_price + offset
            action = OrderAction.SELL
            limit_price = tender.price + limit_offset
        else:  # tender.action == "BUY"
            # Institution bought from us (we sold to them)
            # Now we need to buy back, so place limit buy at tender_price - offset
            action = OrderAction.BUY
            limit_price = tender.price - limit_offset

        logger.info(
            f"Unwinding tender position: {action.value} {tender.quantity} {ticker} "
            f"at limit ${limit_price:.2f}"
        )

        return self.place_limit_order(
            ticker=ticker,
            quantity=tender.quantity,
            action=action,
            price=limit_price
        )

    def close_position(self, ticker: str, position_size: int) -> List[Order]:
        """
        Close a position using market orders (urgent closure to avoid fines).

        Args:
            ticker: Security ticker
            position_size: Current position size (positive for long, negative for short)

        Returns:
            List of submitted orders
        """
        if position_size == 0:
            logger.info(f"No position to close for {ticker}")
            return []

        # Determine action based on position
        if position_size > 0:
            # Long position, need to sell
            action = OrderAction.SELL
            quantity = position_size
        else:
            # Short position, need to buy
            action = OrderAction.BUY
            quantity = abs(position_size)

        logger.warning(
            f"Closing position with market orders: {action.value} {quantity} {ticker}"
        )

        return self.place_market_order(
            ticker=ticker,
            quantity=quantity,
            action=action
        )

    def cancel_all_orders(self, ticker: Optional[str] = None) -> None:
        """
        Cancel all open orders for a specific ticker or all tickers.

        Args:
            ticker: Security ticker (None to cancel all orders)
        """
        try:
            result = self.client.cancel_all_orders(ticker=ticker)
            ticker_str = ticker if ticker else "all tickers"
            logger.info(f"Cancelled all orders for {ticker_str}")
        except Exception as e:
            logger.error(f"Failed to cancel orders: {e}")

    def get_open_orders(self, ticker: Optional[str] = None) -> List[Order]:
        """
        Get all open orders, optionally filtered by ticker.

        Args:
            ticker: Security ticker (None to get all orders)

        Returns:
            List of open orders
        """
        try:
            all_orders = self.client.get_orders(status="OPEN")

            if ticker:
                return [order for order in all_orders if order.ticker == ticker]
            return all_orders

        except Exception as e:
            logger.error(f"Failed to get open orders: {e}")
            return []
