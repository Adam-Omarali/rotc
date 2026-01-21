"""
Core tender offer evaluation logic.

This module contains the fundamental functions for evaluating tender offers,
calculating expected P&L, and determining whether to accept or decline offers.
"""

from typing import Dict, Any
from services.types.tender import Tender
from services.types.security import SecurityBook


# Transaction fee per share
TRANSACTION_FEE = 0.02
# Minimum P&L threshold to accept a tender
MIN_PNL_THRESHOLD = 5000.0


def verify_sufficient_liquidity(tender: Tender, order_book: SecurityBook) -> bool:
    """
    Verify if there's enough liquidity at the top of book to cover the tender quantity.

    For a tender where institution wants to SELL (we BUY):
        - We need to check if we can sell back on the bid side
        - Check total bid volume at best bid price

    For a tender where institution wants to BUY (we SELL):
        - We need to check if we can buy back on the ask side
        - Check total ask volume at best ask price

    Args:
        tender: The tender offer to evaluate
        order_book: Current order book for the security

    Returns:
        True if there's sufficient liquidity, False otherwise
    """
    if tender.action == "SELL":
        # Institution wants to SELL to us (we BUY from them)
        # We need to sell back, so check bid side liquidity
        if not order_book.bids:
            return False

        # Get total volume at the best bid price
        best_bid_price = order_book.bids[0].price
        total_bid_volume = sum(
            level.quantity
            for level in order_book.bids
            if level.price == best_bid_price
        )

        return total_bid_volume >= tender.quantity

    else:  # tender.action == "BUY"
        # Institution wants to BUY from us (we SELL to them)
        # We need to buy back, so check ask side liquidity
        if not order_book.asks:
            return False

        # Get total volume at the best ask price
        best_ask_price = order_book.asks[0].price
        total_ask_volume = sum(
            level.quantity
            for level in order_book.asks
            if level.price == best_ask_price
        )

        return total_ask_volume >= tender.quantity


def calculate_tender_pnl(tender: Tender, order_book: SecurityBook) -> float:
    """
    Calculate expected P&L from executing a tender offer and unwinding the position.

    The P&L calculation considers:
    1. Price difference between tender price and market execution price
    2. Transaction fees on both the tender execution and the unwind

    For a tender where institution wants to SELL (we BUY):
        - We buy at tender.price
        - We sell back at best_bid
        - P&L = quantity × (best_bid - tender.price - 2×fee)

    For a tender where institution wants to BUY (we SELL):
        - We sell at tender.price
        - We buy back at best_ask
        - P&L = quantity × (tender.price - best_ask - 2×fee)

    Args:
        tender: The tender offer to evaluate
        order_book: Current order book for the security

    Returns:
        Expected P&L in dollars (can be negative)
    """
    if tender.action == "SELL":
        # Institution wants to SELL to us (we BUY from them)
        # We buy at tender.price, sell back at best_bid
        if not order_book.bids:
            return float('-inf')  # No market to sell back into

        best_bid = order_book.bids[0].price
        # P&L = (sell_price - buy_price - fees) × quantity
        price_diff = best_bid - tender.price
        pnl_per_share = price_diff - (2 * TRANSACTION_FEE)

        return pnl_per_share * tender.quantity

    else:  # tender.action == "BUY"
        # Institution wants to BUY from us (we SELL to them)
        # We sell at tender.price, buy back at best_ask
        if not order_book.asks:
            return float('-inf')  # No market to buy back from

        best_ask = order_book.asks[0].price
        # P&L = (sell_price - buy_price - fees) × quantity
        price_diff = tender.price - best_ask
        pnl_per_share = price_diff - (2 * TRANSACTION_FEE)

        return pnl_per_share * tender.quantity


def should_accept_tender(
    tender: Tender,
    order_book: SecurityBook,
    current_positions: Dict[str, int],
    net_limit: int = 100000,
    gross_limit: int = 250000
) -> bool:
    """
    Determine whether to accept a tender offer based on multiple criteria.

    Acceptance criteria:
    1. Sufficient liquidity at top of book to cover the tender quantity
    2. Expected P&L meets or exceeds the threshold ($5,000)
    3. Accepting won't violate net position limit (100,000 shares)
    4. Accepting won't violate gross position limit (250,000 shares)

    Args:
        tender: The tender offer to evaluate
        order_book: Current order book for the security
        current_positions: Dict mapping ticker to current position size
        net_limit: Maximum net position across all securities (default: 100,000)
        gross_limit: Maximum gross position across all securities (default: 250,000)

    Returns:
        True if tender should be accepted, False otherwise
    """
    # 1. Check liquidity
    if not verify_sufficient_liquidity(tender, order_book):
        return False

    # 2. Check P&L threshold
    expected_pnl = calculate_tender_pnl(tender, order_book)
    if expected_pnl < MIN_PNL_THRESHOLD:
        return False

    # 3. Calculate position impact
    ticker = tender.ticker or ""  # Use empty string if ticker is None
    current_position = current_positions.get(ticker, 0)

    # Determine new position after accepting tender
    if tender.action == "SELL":
        # Institution sells to us, we buy (increases our position)
        new_position = current_position + tender.quantity
    else:  # tender.action == "BUY"
        # Institution buys from us, we sell (decreases our position)
        new_position = current_position - tender.quantity

    # Calculate new portfolio metrics
    updated_positions = current_positions.copy()
    updated_positions[ticker] = new_position

    # Calculate net and gross exposure
    all_positions = list(updated_positions.values())
    net_exposure = abs(sum(all_positions))  # Net can offset
    gross_exposure = sum(abs(pos) for pos in all_positions)  # Gross is additive

    # 4. Check position limits
    if net_exposure > net_limit:
        return False

    if gross_exposure > gross_limit:
        return False

    return True


def should_place_limit_order() -> bool:
    """
    Determine whether to place limit orders after accepting a tender.

    This is a placeholder function for now. In the future, this could incorporate
    market condition logic, volatility analysis, or other factors.

    Returns:
        True (always place limit orders for now)
    """
    return True
