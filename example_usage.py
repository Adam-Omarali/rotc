"""
Example usage of the RIT Trading API Client.

This file demonstrates how to use the RITClient class to interact
with the RIT trading API.
"""

from services import RITClient, OrderType, OrderAction, AuthenticationError, RateLimitError


def main():
    """Main example function demonstrating RIT client usage."""

    # Replace with your actual API key from the RIT client
    API_KEY = "YOUR API KEY HERE"

    # Example 1: Using context manager (recommended)
    print("Example 1: Basic usage with context manager")
    try:
        with RITClient(api_key=API_KEY) as client:
            # Get current case information
            case_info = client.get_case_info()
            print(f"Case: {case_info.name}")
            print(f"Current tick: {case_info.tick}")
            print(f"Status: {case_info.status}")
            print()

            # Get all active tenders
            tenders = client.get_tenders()
            print(f"Active tenders: {len(tenders)}")
            for tender in tenders:
                print(f"  - Tender {tender.tender_id}: {tender.action} {tender.quantity} @ ${tender.price}")
            print()

            # Get securities information
            securities = client.get_securities()
            print(f"Securities: {len(securities)}")
            for security in securities:
                print(f"  - {security.ticker}: Last=${security.last}, Bid=${security.bid}, Ask=${security.ask}")
            print()

            # Get order book for a specific security
            if securities:
                ticker = securities[0].ticker
                book = client.get_security_book(ticker, limit=5)
                print(f"Order book for {ticker}:")
                print("  Bids:")
                for bid in book.bids[:5]:
                    print(f"    {bid.quantity} @ ${bid.price}")
                print("  Asks:")
                for ask in book.asks[:5]:
                    print(f"    {ask.quantity} @ ${ask.price}")
                print()

            # Get current orders
            orders = client.get_orders(status="OPEN")
            print(f"Open orders: {len(orders)}")
            for order in orders:
                print(f"  - Order {order.order_id}: {order.action} {order.quantity} {order.ticker} @ ${order.price}")
            print()

    except AuthenticationError as e:
        print(f"Authentication failed: {e}")
        print("Make sure your API key matches the RIT client configuration.")
    except RateLimitError as e:
        print(f"Rate limited: {e}")
        print(f"Please wait {e.retry_after} seconds before retrying.")
    except Exception as e:
        print(f"Error: {e}")

    print("\nExample 2: Submitting orders")
    try:
        with RITClient(api_key=API_KEY) as client:
            # Submit a limit order (dry run mode for testing)
            order = client.submit_order(
                ticker="CRZY",
                order_type=OrderType.LIMIT,
                quantity=100,
                action=OrderAction.BUY,
                price=50.25,
                dry_run=True  # Set to False to actually submit
            )
            print(f"Order submitted: {order.order_id}")
            print(f"  Status: {order.status}")
            print(f"  Filled: {order.quantity_filled}/{order.quantity}")
    except Exception as e:
        print(f"Could not submit order: {e}")

    print("\nExample 3: Order book with cumulative metrics")
    try:
        with RITClient(api_key=API_KEY) as client:
            # Get book with pre-calculated cumulative volumes and VWAPs
            book_with_cumulatives = client.get_book_with_cumulatives("CRZY", limit=5)

            print(f"Book for {book_with_cumulatives['ticker']} with cumulatives:")
            print("  Bids (with cumulative VWAP):")
            for level in book_with_cumulatives['bids'][:5]:
                print(f"    {level['cumulative_vol']} @ ${level['price']} (VWAP: ${level['cumulative_vwap']:.2f})")
    except Exception as e:
        print(f"Could not fetch book: {e}")

    print("\nExample 4: Custom client configuration")
    # You can customize timeout, retries, etc.
    client = RITClient(
        api_key=API_KEY,
        base_url="http://localhost:9999/v1",
        timeout=15.0,
        max_retries=5,
        retry_backoff=2.0
    )

    try:
        tick = client.get_tick()
        print(f"Current tick: {tick}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
