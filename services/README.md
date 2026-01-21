# RIT Trading API Client

Professional API handler for the Rotman Interactive Trader (RIT) REST API.

## Features

- **Type-Safe**: Full type hints with Pydantic models for all API responses
- **Error Handling**: Comprehensive exception hierarchy for different error scenarios
- **Retry Logic**: Automatic retry with exponential backoff for rate limits and connection errors
- **Connection Pooling**: Efficient session management with connection pooling
- **Context Manager**: Clean resource management with `with` statement support
- **Customizable**: All parameters configurable with sensible defaults
- **Order Book Utilities**: Helper methods for cumulative volume/VWAP calculations

## Installation

```bash
pip install -r requirements.txt
```

## Quick Start

```python
from services import RITClient, OrderType, OrderAction

# Initialize client
with RITClient(api_key='YOUR_API_KEY') as client:
    # Get tenders
    tenders = client.get_tenders()

    # Get market data
    securities = client.get_securities()
    book = client.get_security_book('CRZY', limit=10)

    # Submit an order
    order = client.submit_order(
        ticker='CRZY',
        order_type=OrderType.LIMIT,
        quantity=100,
        action=OrderAction.BUY,
        price=50.25
    )

    # Check orders
    orders = client.get_orders(status='OPEN')
```

## API Methods

### Tenders

- `get_tenders()` - Retrieve all active tenders
- `accept_tender(tender_id, price)` - Accept a tender
- `decline_tender(tender_id)` - Decline a tender

### Market Data

- `get_securities(ticker)` - Get securities information
- `get_security_book(ticker, limit)` - Get order book for a security
- `get_security_history(ticker, period, limit)` - Get OHLC historical data
- `get_security_tas(ticker, after, period, limit)` - Get time and sales data

### Orders

- `get_orders(status)` - Get orders (optionally filtered by status)
- `get_order(order_id)` - Get specific order by ID
- `submit_order(ticker, order_type, quantity, action, price)` - Submit new order
- `cancel_order(order_id)` - Cancel specific order
- `cancel_all_orders(ticker)` - Cancel all orders (optionally filtered by ticker)

### Utilities

- `get_case_info()` - Get current case information
- `get_tick()` - Get current tick
- `calculate_book_cumulatives(book_levels)` - Calculate cumulative metrics for book levels
- `get_book_with_cumulatives(ticker, limit)` - Get order book with pre-calculated cumulatives

## Type Definitions

All API responses are automatically parsed into type-safe Pydantic models:

### Enums
- `OrderType` - MARKET, LIMIT
- `OrderAction` - BUY, SELL
- `OrderStatus` - OPEN, TRANSACTED, CANCELLED, REJECTED

### Models
- `Tender` - Trading tender information
- `Security` - Security/stock information
- `SecurityBook` - Order book with bids and asks
- `BookLevel` - Single order book level
- `Order` - Order information
- `CaseInfo` - Case metadata

## Error Handling

The client provides specific exceptions for different error scenarios:

```python
from services import (
    RITAPIException,      # Base exception
    AuthenticationError,  # 401 - Invalid API key
    RateLimitError,       # 429 - Rate limit exceeded
    ValidationError,      # 400 - Invalid parameters
    NotFoundError,        # 404 - Resource not found
    ServerError,          # 5xx - Server error
)

try:
    client.submit_order(...)
except AuthenticationError as e:
    print(f"Auth failed: {e}")
except RateLimitError as e:
    print(f"Rate limited. Retry after {e.retry_after}s")
except ValidationError as e:
    print(f"Invalid request: {e}")
```

## Configuration

```python
client = RITClient(
    api_key='YOUR_API_KEY',           # Required: API key from RIT client
    base_url='http://localhost:9999/v1',  # Default: local RIT instance
    timeout=10.0,                     # Default: 10 seconds
    max_retries=3,                    # Default: 3 retry attempts
    retry_backoff=1.0,                # Default: 1 second base backoff
)
```

## Advanced Usage

### Order Book with Cumulative Metrics

```python
# Get order book with pre-calculated cumulative volumes and VWAPs
book = client.get_book_with_cumulatives('CRZY', limit=20)

for level in book['bids']:
    print(f"Price: ${level['price']}")
    print(f"Cumulative Volume: {level['cumulative_vol']}")
    print(f"Cumulative VWAP: ${level['cumulative_vwap']:.2f}")
```

### Custom Retry Behavior

The client automatically retries on rate limits (429) and connection errors:

```python
# Automatic exponential backoff
# Attempt 1: wait 1s
# Attempt 2: wait 2s
# Attempt 3: wait 4s
# Respects 'Retry-After' header from API
```

### Dry Run Orders

Test order validation without execution:

```python
order = client.submit_order(
    ticker='CRZY',
    order_type=OrderType.LIMIT,
    quantity=100,
    action=OrderAction.BUY,
    price=50.25,
    dry_run=True  # Validates but doesn't execute
)
```

## Project Structure

```
services/
├── __init__.py              # Package exports
├── rit_client.py            # Main RITClient class
├── types/
│   ├── __init__.py          # Type exports
│   ├── enums.py             # OrderType, OrderAction, OrderStatus
│   ├── tender.py            # Tender models
│   ├── security.py          # Security and book models
│   ├── order.py             # Order models
│   └── common.py            # CaseInfo and common models
└── exceptions/
    ├── __init__.py          # Exception exports
    └── api_exceptions.py    # All exception classes
```

## Examples

See [example_usage.py](../example_usage.py) for complete working examples.

## API Documentation

Full API documentation: https://rit.306w.ca/RIT-REST-API/1.0.3/

## License

This is a client library for the RIT trading platform.
