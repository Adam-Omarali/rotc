#!/usr/bin/env python3
"""
Run the Liability Trading Algorithm

Main entry point for running the trading algorithm against the RIT trading client.

Usage:
    python run_algorithm.py --api-key YOUR_API_KEY
    python run_algorithm.py --api-key YOUR_API_KEY --aggressive
    python run_algorithm.py --api-key YOUR_API_KEY --debug
"""

import argparse
import logging
import sys
from dataclasses import replace

from algorithm import (
    TradingAlgorithm,
    AlgorithmConfig,
    DEFAULT_CONFIG,
    create_algorithm,
)
from services import RITClient


def setup_logging(debug: bool = False) -> None:
    """Configure logging for the trading algorithm."""
    level = logging.DEBUG if debug else logging.INFO

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
        datefmt="%H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    # File handler for full logs
    file_handler = logging.FileHandler("trading_algorithm.log", mode="w")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Suppress noisy loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)


def create_aggressive_config() -> AlgorithmConfig:
    """Create a more aggressive configuration for fast markets."""
    return AlgorithmConfig(
        # Lower acceptance thresholds
        accept_threshold_high=65.0,
        accept_threshold_medium=50.0,
        accept_threshold_low=35.0,
        # Faster monitoring
        monitor_interval=1.5,
        # Less patience for repricing
        patience_urgent=3.0,
        patience_moderate=8.0,
        patience_relaxed=15.0,
        # Earlier emergency trigger
        emergency_time_threshold=45.0,
    )


def create_conservative_config() -> AlgorithmConfig:
    """Create a more conservative configuration."""
    return AlgorithmConfig(
        # Higher acceptance thresholds
        accept_threshold_high=80.0,
        accept_threshold_medium=65.0,
        accept_threshold_low=50.0,
        # More patience
        patience_urgent=8.0,
        patience_moderate=20.0,
        patience_relaxed=40.0,
        # Fewer max tenders
        max_tenders=3,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Run the Liability Trading Algorithm",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_algorithm.py --api-key ABC123
  python run_algorithm.py --api-key ABC123 --aggressive --debug
  python run_algorithm.py --api-key ABC123 --conservative
  python run_algorithm.py --api-key ABC123 --base-url http://192.168.1.100:9999/v1
        """,
    )

    parser.add_argument(
        "--api-key",
        required=True,
        help="RIT API key (must match RIT client configuration)",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:9999/v1",
        help="RIT API base URL (default: http://localhost:9999/v1)",
    )
    parser.add_argument(
        "--aggressive",
        action="store_true",
        help="Use aggressive trading configuration",
    )
    parser.add_argument(
        "--conservative",
        action="store_true",
        help="Use conservative trading configuration",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--max-tenders",
        type=int,
        default=None,
        help="Override maximum number of tenders to accept",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="API request timeout in seconds (default: 10.0)",
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(debug=args.debug)
    logger = logging.getLogger(__name__)

    # Select configuration
    if args.aggressive and args.conservative:
        logger.error("Cannot use both --aggressive and --conservative")
        sys.exit(1)

    if args.aggressive:
        config = create_aggressive_config()
        logger.info("Using AGGRESSIVE configuration")
    elif args.conservative:
        config = create_conservative_config()
        logger.info("Using CONSERVATIVE configuration")
    else:
        config = DEFAULT_CONFIG
        logger.info("Using DEFAULT configuration")

    # Apply overrides
    if args.max_tenders is not None:
        config = replace(config, max_tenders=args.max_tenders)
        logger.info(f"Overriding max_tenders to {args.max_tenders}")

    # Create and run algorithm
    logger.info("=" * 60)
    logger.info("STARTING TRADING ALGORITHM")
    logger.info(f"API URL: {args.base_url}")
    logger.info("=" * 60)

    try:
        algorithm = create_algorithm(
            api_key=args.api_key,
            config=config,
            base_url=args.base_url,
            timeout=args.timeout,
        )

        # Verify connection
        logger.info("Verifying API connection...")
        with RITClient(api_key=args.api_key, base_url=args.base_url) as test_client:
            case_info = test_client.get_case_info()
            logger.info(f"Connected to case: {case_info.name}")
            logger.info(f"Current tick: {case_info.tick}/{case_info.ticks_per_period}")
            logger.info(f"Case status: {case_info.status}")

            if case_info.status != "ACTIVE":
                logger.warning(f"Case is not ACTIVE (status={case_info.status})")
                response = input("Continue anyway? (y/n): ")
                if response.lower() != "y":
                    logger.info("Exiting")
                    sys.exit(0)

        # Run the algorithm
        algorithm.run()

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

    logger.info("Algorithm completed")


if __name__ == "__main__":
    main()
