"""
Main trading loop for the Tender Offer Arbitrage Algorithm.

This script implements the core trading logic for the Liability Trading 3 (LT3) case,
evaluating and executing tender offers while managing risk and position limits.
"""

import logging
import time
import sys
from typing import Optional, Dict
from datetime import datetime

from services.rit_client import RITClient
from algorithm.tender_arbitrage import (
    should_accept_tender,
    should_place_limit_order,
    calculate_tender_pnl,
)
from algorithm.position_manager import PositionManager
from algorithm.execution_engine import ExecutionEngine


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('tender_algorithm.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class TenderAlgorithm:
    """
    Main algorithm for tender offer arbitrage trading.

    The algorithm:
    1. Polls for tender offers continuously
    2. Evaluates each tender for profitability and risk
    3. Waits until the last second to decide (maximize information)
    4. Accepts profitable tenders and places limit orders to unwind
    5. Closes all positions before case end to avoid fines
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "http://localhost:9999/v1",
        poll_interval: float = 0.5,
        tender_decision_buffer: float = 2.0,
        end_of_case_buffer: float = 10.0
    ):
        """
        Initialize the trading algorithm.

        Args:
            api_key: RIT API key
            base_url: RIT API base URL
            poll_interval: Time between polling cycles (seconds)
            tender_decision_buffer: Time before tender expiry to make decision (seconds)
            end_of_case_buffer: Time before case end to close all positions (seconds)
        """
        self.client = RITClient(api_key=api_key, base_url=base_url)
        self.position_manager = PositionManager(self.client)
        self.execution_engine = ExecutionEngine(self.client)

        self.poll_interval = poll_interval
        self.tender_decision_buffer = tender_decision_buffer
        self.end_of_case_buffer = end_of_case_buffer

        self.running = False
        self.processed_tenders = set()  # Track tenders we've already processed

    def get_time_remaining_in_case(self) -> float:
        """
        Calculate time remaining in the current trading period.

        Returns:
            Seconds remaining in the case
        """
        try:
            case_info = self.client.get_case_info()
            current_tick = case_info.tick
            ticks_per_period = case_info.ticks_per_period

            # Assuming each tick is approximately 1 second
            ticks_remaining = ticks_per_period - current_tick
            return max(0, ticks_remaining)

        except Exception as e:
            logger.error(f"Failed to get case info: {e}")
            return float('inf')  # Assume infinite time if we can't determine

    def should_close_positions(self) -> bool:
        """
        Determine if we should close all positions due to case ending.

        Returns:
            True if we should close positions now
        """
        time_remaining = self.get_time_remaining_in_case()
        return time_remaining <= self.end_of_case_buffer

    def evaluate_tender(self, tender) -> bool:
        """
        Evaluate a tender offer and decide whether to accept.

        Args:
            tender: Tender offer to evaluate

        Returns:
            True if tender should be accepted, False otherwise
        """
        ticker = tender.ticker or ""
        logger.info(f"\n{'='*60}")
        logger.info(f"Evaluating Tender ID {tender.id}")
        logger.info(f"Action: {tender.action} | Ticker: {ticker}")
        logger.info(f"Quantity: {tender.quantity} | Price: ${tender.price:.2f}")
        logger.info(f"{'='*60}")

        # Get current order book
        try:
            order_book = self.client.get_security_book(ticker)
        except Exception as e:
            logger.error(f"Failed to fetch order book for {ticker}: {e}")
            return False

        # Get current positions
        current_positions = self.position_manager.get_current_positions()

        # Log current position status
        position_summary = self.position_manager.get_position_summary()
        logger.info(f"Current Positions: {position_summary['positions']}")
        logger.info(
            f"Net Exposure: {position_summary['net_exposure']:,} / "
            f"{position_summary['net_limit']:,}"
        )
        logger.info(
            f"Gross Exposure: {position_summary['gross_exposure']:,} / "
            f"{position_summary['gross_limit']:,}"
        )

        # Calculate expected P&L
        expected_pnl = calculate_tender_pnl(tender, order_book)
        logger.info(f"Expected P&L: ${expected_pnl:,.2f}")

        # Make decision
        decision = should_accept_tender(
            tender=tender,
            order_book=order_book,
            current_positions=current_positions
        )

        logger.info(f"Decision: {'ACCEPT' if decision else 'DECLINE'}")
        return decision

    def process_tender(self, tender) -> None:
        """
        Process a tender offer (evaluate, accept/decline, execute).

        Args:
            tender: Tender offer to process
        """
        # Check if we've already processed this tender
        if tender.id in self.processed_tenders:
            return

        # Mark as processed
        self.processed_tenders.add(tender.id)

        # Calculate time until tender expires
        current_tick = self.client.get_tick()
        ticks_until_expiry = tender.expires - current_tick
        logger.info(f"Tender expires in ~{ticks_until_expiry} ticks")

        # Wait until the last second before deciding
        # We want to maximize information but leave time to execute
        if ticks_until_expiry > self.tender_decision_buffer:
            logger.info(
                f"Waiting {ticks_until_expiry - self.tender_decision_buffer:.1f} "
                f"seconds before making decision..."
            )
            time.sleep(ticks_until_expiry - self.tender_decision_buffer)

        # Evaluate the tender
        should_accept = self.evaluate_tender(tender)

        # Execute decision
        try:
            if should_accept:
                logger.info(f"Accepting tender {tender.id}...")
                result = self.client.accept_tender(tender.id)
                logger.info(f"Tender accepted: {result}")

                # Place limit orders to unwind if appropriate
                if should_place_limit_order():
                    logger.info("Placing limit orders to unwind position...")
                    orders = self.execution_engine.unwind_position_with_limits(tender)
                    logger.info(f"Placed {len(orders)} limit order(s)")

            else:
                logger.info(f"Declining tender {tender.id}...")
                result = self.client.decline_tender(tender.id)
                logger.info(f"Tender declined: {result}")

        except Exception as e:
            logger.error(f"Failed to process tender {tender.id}: {e}")

    def close_all_positions(self) -> None:
        """
        Close all open positions using market orders to avoid fines.
        """
        logger.warning("\n" + "="*60)
        logger.warning("CLOSING ALL POSITIONS TO AVOID END-OF-CASE FINES")
        logger.warning("="*60)

        # Cancel all open limit orders first
        self.execution_engine.cancel_all_orders()

        # Get current positions
        positions = self.position_manager.get_current_positions()

        # Close each position
        for ticker, position_size in positions.items():
            if position_size != 0:
                logger.warning(f"Closing {ticker} position: {position_size:,} shares")
                self.execution_engine.close_position(ticker, position_size)

        # Wait a moment for orders to fill
        time.sleep(2)

        # Log final P&L
        final_pnl = self.position_manager.get_total_pnl()
        logger.info(f"\nFinal Total P&L: ${final_pnl:,.2f}")

    def run(self) -> None:
        """
        Main trading loop.

        Continuously polls for tender offers and processes them until
        the case ends or the algorithm is stopped.
        """
        logger.info("\n" + "="*60)
        logger.info("STARTING TENDER OFFER ARBITRAGE ALGORITHM")
        logger.info("="*60)

        self.running = True

        try:
            # Check if case is active
            case_info = self.client.get_case_info()
            logger.info(f"Case: {case_info.name}")
            logger.info(f"Status: {case_info.status}")
            logger.info(f"Period: {case_info.period} / {case_info.total_periods}")

            if case_info.status != "ACTIVE":
                logger.warning(f"Case is not active (status: {case_info.status})")
                return

            # Main loop
            while self.running:
                # Check if we should close positions due to case ending
                if self.should_close_positions():
                    self.close_all_positions()
                    break

                # Poll for tender offers
                try:
                    tenders = self.client.get_tenders()

                    # Process any new tenders
                    for tender in tenders:
                        if tender.id not in self.processed_tenders:
                            self.process_tender(tender)

                except Exception as e:
                    logger.error(f"Error polling for tenders: {e}")

                # Log position status periodically
                if self.position_manager.has_open_positions():
                    summary = self.position_manager.get_position_summary()
                    logger.info(
                        f"Current P&L: ${summary.get('total_pnl', 0):,.2f} | "
                        f"Positions: {summary['positions']}"
                    )

                # Sleep before next poll
                time.sleep(self.poll_interval)

        except KeyboardInterrupt:
            logger.info("\nReceived keyboard interrupt, shutting down...")
            self.close_all_positions()

        except Exception as e:
            logger.error(f"Fatal error in main loop: {e}", exc_info=True)

        finally:
            self.running = False
            logger.info("Algorithm stopped.")

    def stop(self) -> None:
        """
        Stop the algorithm gracefully.
        """
        logger.info("Stopping algorithm...")
        self.running = False


def main():
    """
    Entry point for the tender offer arbitrage algorithm.
    """
    # Configuration
    API_KEY = "YOUR_API_KEY"  # Replace with your actual API key
    BASE_URL = "http://localhost:9999/v1"

    # Create and run algorithm
    algorithm = TenderAlgorithm(
        api_key=API_KEY,
        base_url=BASE_URL,
        poll_interval=0.5,  # Poll every 0.5 seconds
        tender_decision_buffer=2.0,  # Decide 2 seconds before expiry
        end_of_case_buffer=10.0  # Close positions 10 seconds before case end
    )

    try:
        algorithm.run()
    except Exception as e:
        logger.error(f"Algorithm failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
