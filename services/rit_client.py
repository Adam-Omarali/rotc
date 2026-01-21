"""
RIT Trading API Client

Professional API handler for the Rotman Interactive Trader (RIT) REST API.
Provides type-safe access to tenders, market data, orders, and trading operations.
"""

import time
from typing import Any, Dict, List, Optional, Type, Union, TypeVar
import requests
from requests.adapters import HTTPAdapter
from pydantic import BaseModel

from .types import (
    OrderType,
    OrderAction,
    OrderStatus,
    Tender,
    TenderResponse,
    Security,
    SecurityBook,
    SecurityHistory,
    TimeAndSales,
    Order,
    OrderRequest,
    CancelResponse,
    BulkCancelResponse,
    CaseInfo,
    BookLevel,
)
from .exceptions import (
    RITAPIException,
    AuthenticationError,
    RateLimitError,
    ValidationError,
    NotFoundError,
    ServerError,
)

T = TypeVar("T", bound=BaseModel)


class RITClient:
    """
    Professional handler for RIT Trading API.

    Features:
    - Session management with connection pooling
    - Automatic retry logic for rate limiting (429)
    - Comprehensive error handling
    - Type-safe requests and responses
    - Context manager support for clean resource management

    Example:
        with RITClient(api_key='YOUR_API_KEY') as client:
            tenders = client.get_tenders()
            order = client.submit_order(
                ticker='CRZY',
                order_type=OrderType.LIMIT,
                quantity=100,
                action=OrderAction.BUY,
                price=50.25
            )
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "http://localhost:9999/v1",
        timeout: float = 10.0,
        max_retries: int = 3,
        retry_backoff: float = 1.0,
    ):
        """
        Initialize RIT API client.

        Args:
            api_key: API key from RIT client (must match client configuration)
            base_url: Base API URL (default: http://localhost:9999/v1)
            timeout: Default request timeout in seconds (default: 10.0)
            max_retries: Maximum retry attempts for failed requests (default: 3)
            retry_backoff: Base backoff time for exponential retry in seconds (default: 1.0)
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff

        # Session setup with connection pooling
        self.session = requests.Session()
        self.session.headers.update(
            {
                "X-API-Key": api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

        # Connection pooling configuration
        adapter = HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=0,  # We handle retries manually
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def _handle_response(self, response: requests.Response) -> Union[Dict[str, Any], List[Any]]:
        """
        Central error handler for all API responses.

        Args:
            response: Response object from requests

        Returns:
            Parsed JSON response

        Raises:
            AuthenticationError: On 401
            RateLimitError: On 429
            ValidationError: On 400
            NotFoundError: On 404
            ServerError: On 5xx
            RITAPIException: On other errors
        """
        if response.status_code in (200, 201):
            return response.json()

        elif response.status_code == 401:
            raise AuthenticationError(
                "Invalid API key. Ensure API key matches RIT client."
            )

        elif response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 1))
            raise RateLimitError("Rate limit exceeded", retry_after=retry_after)

        elif response.status_code == 400:
            try:
                error_data = response.json()
                error_msg = error_data.get("error", "Bad request")
            except Exception:
                error_msg = "Bad request"
            raise ValidationError(error_msg)

        elif response.status_code == 404:
            raise NotFoundError("Resource not found")

        elif response.status_code >= 500:
            raise ServerError(
                f"Server error: {response.status_code}",
                status_code=response.status_code,
            )

        else:
            raise RITAPIException(
                f"Unexpected error: {response.status_code}",
                status_code=response.status_code,
            )

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        response_model: Optional[Type[T]] = None,
        retry_on_rate_limit: bool = True,
        timeout: Optional[float] = None,
    ) -> Union[Dict[str, Any], T, List[T], List[Any]]:
        """
        Generic HTTP request method with retry logic and type conversion.

        Args:
            method: HTTP method (GET, POST, DELETE)
            endpoint: API endpoint path (without base URL)
            params: Query parameters
            json_data: JSON request body
            response_model: Pydantic model for response parsing
            retry_on_rate_limit: Whether to retry on 429 errors
            timeout: Request timeout override

        Returns:
            Parsed response (dict, model instance, or list)

        Raises:
            AuthenticationError: On authentication failure
            RateLimitError: On rate limit (if retry disabled or max retries exceeded)
            RITAPIException: On other errors
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        timeout = timeout or self.timeout

        for attempt in range(self.max_retries):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data,
                    timeout=timeout,
                )

                data = self._handle_response(response)

                # Type conversion if model provided
                if response_model:
                    if isinstance(data, list):
                        return [response_model(**item) for item in data]
                    else:
                        return response_model(**data)

                return data

            except RateLimitError as e:
                if not retry_on_rate_limit or attempt == self.max_retries - 1:
                    raise

                wait_time = e.retry_after or (self.retry_backoff * (2**attempt))
                time.sleep(wait_time)
                continue

            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt == self.max_retries - 1:
                    raise RITAPIException(f"Connection failed: {str(e)}")
                time.sleep(self.retry_backoff * (2**attempt))
                continue

        raise RITAPIException("Max retries exceeded")

    # ========== Tender Methods ==========

    def get_tenders(self) -> List[Tender]:
        """
        Retrieve all active tenders.

        Returns:
            List of Tender objects

        Raises:
            AuthenticationError: If API key is invalid
            RITAPIException: On other errors
        """
        return self._request(method="GET", endpoint="/tenders", response_model=Tender)

    def accept_tender(self, tender_id: int, price: Optional[float] = None) -> Dict[str, Any]:
        """
        Accept a tender.

        Args:
            tender_id: ID of the tender to accept
            price: Price to bid (required for non-fixed-bid tenders)

        Returns:
            Response dictionary with success status

        Raises:
            ValidationError: If parameters are invalid
            NotFoundError: If tender doesn't exist
            RITAPIException: On other errors
        """
        params = {}
        if price is not None:
            params["price"] = price

        return self._request(
            method="POST", endpoint=f"/tenders/{tender_id}", params=params
        )

    def decline_tender(self, tender_id: int) -> Dict[str, Any]:
        """
        Decline a tender.

        Args:
            tender_id: ID of the tender to decline

        Returns:
            Response dictionary with success status

        Raises:
            NotFoundError: If tender doesn't exist
            RITAPIException: On other errors
        """
        return self._request(method="DELETE", endpoint=f"/tenders/{tender_id}")

    # ========== Securities / Market Data Methods ==========

    def get_securities(self, ticker: Optional[str] = None) -> List[Security]:
        """
        Get information about securities.

        Args:
            ticker: Optional ticker to filter by specific security

        Returns:
            List of Security objects

        Raises:
            AuthenticationError: If API key is invalid
            RITAPIException: On other errors
        """
        params = {"ticker": ticker} if ticker else None
        return self._request(
            method="GET", endpoint="/securities", params=params, response_model=Security
        )

    def get_security_book(
        self, ticker: str, limit: Optional[int] = None
    ) -> SecurityBook:
        """
        Get order book for a security.

        Args:
            ticker: Security ticker symbol
            limit: Maximum number of levels per side (default: 20)

        Returns:
            SecurityBook with bids and asks

        Raises:
            ValidationError: If ticker is invalid
            RITAPIException: On other errors
        """
        params = {"ticker": ticker}
        if limit is not None:
            params["limit"] = limit

        return self._request(
            method="GET",
            endpoint="/securities/book",
            params=params,
            response_model=SecurityBook,
        )

    def get_security_history(
        self,
        ticker: str,
        period: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[SecurityHistory]:
        """
        Get historical OHLC data for a security.

        Args:
            ticker: Security ticker symbol
            period: Specific period to query
            limit: Maximum number of candles to return

        Returns:
            List of SecurityHistory (OHLC candles)

        Raises:
            ValidationError: If parameters are invalid
            RITAPIException: On other errors
        """
        params = {"ticker": ticker}
        if period is not None:
            params["period"] = period
        if limit is not None:
            params["limit"] = limit

        return self._request(
            method="GET",
            endpoint="/securities/history",
            params=params,
            response_model=SecurityHistory,
        )

    def get_security_tas(
        self,
        ticker: str,
        after: Optional[int] = None,
        period: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[TimeAndSales]:
        """
        Get time and sales (trade history) for a security.

        Args:
            ticker: Security ticker symbol
            after: Only return trades after this tick
            period: Specific period to query
            limit: Maximum number of trades to return

        Returns:
            List of TimeAndSales entries

        Raises:
            ValidationError: If parameters are invalid
            RITAPIException: On other errors
        """
        params = {"ticker": ticker}
        if after is not None:
            params["after"] = after
        if period is not None:
            params["period"] = period
        if limit is not None:
            params["limit"] = limit

        return self._request(
            method="GET",
            endpoint="/securities/tas",
            params=params,
            response_model=TimeAndSales,
        )

    # ========== Order Methods ==========

    def get_orders(self, status: Optional[str] = None) -> List[Order]:
        """
        Get orders, optionally filtered by status.

        Args:
            status: Filter by status (OPEN, TRANSACTED, CANCELLED)

        Returns:
            List of Order objects

        Raises:
            AuthenticationError: If API key is invalid
            RITAPIException: On other errors
        """
        params = {"status": status} if status else None
        return self._request(
            method="GET", endpoint="/orders", params=params, response_model=Order
        )

    def get_order(self, order_id: int) -> Order:
        """
        Get a specific order by ID.

        Args:
            order_id: Order ID to retrieve

        Returns:
            Order object

        Raises:
            NotFoundError: If order doesn't exist
            RITAPIException: On other errors
        """
        return self._request(
            method="GET", endpoint=f"/orders/{order_id}", response_model=Order
        )

    def submit_order(
        self,
        ticker: str,
        order_type: OrderType,
        quantity: int,
        action: OrderAction,
        price: Optional[float] = None,
        dry_run: bool = False,
    ) -> Order:
        """
        Submit a new order.

        Args:
            ticker: Security ticker symbol
            order_type: MARKET or LIMIT
            quantity: Number of shares
            action: BUY or SELL
            price: Limit price (required for LIMIT orders)
            dry_run: If True, validate but don't execute

        Returns:
            Created Order object

        Raises:
            ValidationError: If parameters are invalid
            RateLimitError: If rate limited (429)
            RITAPIException: On other errors
        """
        if order_type == OrderType.LIMIT and price is None:
            raise ValueError("Price required for LIMIT orders")

        request_data = {
            "ticker": ticker,
            "type": order_type.value,
            "quantity": quantity,
            "action": action.value,
        }

        if price is not None:
            request_data["price"] = price

        if dry_run:
            request_data["dry_run"] = 1

        return self._request(
            method="POST",
            endpoint="/orders",
            json_data=request_data,
            response_model=Order,
        )

    def cancel_order(self, order_id: int) -> Dict[str, Any]:
        """
        Cancel a specific order.

        Args:
            order_id: ID of order to cancel

        Returns:
            Response dictionary with success status

        Raises:
            NotFoundError: If order doesn't exist
            RITAPIException: On other errors
        """
        return self._request(method="DELETE", endpoint=f"/orders/{order_id}")

    def cancel_all_orders(
        self, ticker: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cancel all orders, optionally filtered by ticker.

        Args:
            ticker: If provided, only cancel orders for this ticker

        Returns:
            Response with list of cancelled order IDs

        Raises:
            RITAPIException: On errors
        """
        if ticker:
            params = {"ticker": ticker}
        else:
            params = {"all": 1}

        return self._request(
            method="POST", endpoint="/commands/cancel", params=params
        )

    # ========== Utility Methods ==========

    def get_case_info(self) -> CaseInfo:
        """
        Get information about the current trading case.

        Returns:
            CaseInfo object with case details

        Raises:
            AuthenticationError: If API key is invalid
            RITAPIException: On other errors
        """
        return self._request(method="GET", endpoint="/case", response_model=CaseInfo)

    def get_tick(self) -> int:
        """
        Get the current tick of the running case.

        Returns:
            Current tick number

        Raises:
            AuthenticationError: If API key is invalid
            RITAPIException: On other errors
        """
        case_info = self.get_case_info()
        return case_info.tick

    # ========== Order Book Utility Methods ==========

    def calculate_book_cumulatives(
        self, book_levels: List[BookLevel]
    ) -> List[Dict[str, Any]]:
        """
        Calculate cumulative volumes and VWAPs for each book level.

        This helper method matches the pattern from the existing code,
        computing cumulative statistics across order book levels.

        Args:
            book_levels: List of BookLevel objects

        Returns:
            List of dicts with added 'cumulative_vol' and 'cumulative_vwap' fields
        """
        result = []
        cumulative_vol = 0
        cumulative_price_vol = 0.0

        for level in book_levels:
            remaining_qty = level.quantity - level.quantity_filled
            cumulative_vol += remaining_qty
            cumulative_price_vol += level.price * remaining_qty

            cumulative_vwap = (
                cumulative_price_vol / cumulative_vol if cumulative_vol > 0 else 0
            )

            result.append(
                {
                    "price": level.price,
                    "quantity": level.quantity,
                    "quantity_filled": level.quantity_filled,
                    "action": level.action,
                    "cumulative_vol": cumulative_vol,
                    "cumulative_vwap": cumulative_vwap,
                }
            )

        return result

    def get_book_with_cumulatives(
        self, ticker: str, limit: int = 20
    ) -> Dict[str, Any]:
        """
        Get order book with pre-calculated cumulative metrics.

        Args:
            ticker: Security ticker symbol
            limit: Maximum number of levels per side

        Returns:
            Dict with 'bids' and 'asks', each containing cumulative metrics

        Raises:
            ValidationError: If ticker is invalid
            RITAPIException: On other errors
        """
        book = self.get_security_book(ticker, limit)

        return {
            "ticker": ticker,
            "bids": self.calculate_book_cumulatives(book.bids),
            "asks": self.calculate_book_cumulatives(book.asks),
        }

    # ========== Context Manager Support ==========

    def __enter__(self) -> "RITClient":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - ensure session cleanup."""
        self.close()

    def close(self) -> None:
        """Close the session and cleanup resources."""
        if self.session:
            self.session.close()
