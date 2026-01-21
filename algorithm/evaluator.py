"""
Tender Evaluation Engine

Calculates risk scores and makes accept/decline decisions for tenders.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

from services import RITClient
from services.types import Tender, Security, SecurityBook, BookLevel

from .config import AlgorithmConfig, DEFAULT_CONFIG

logger = logging.getLogger(__name__)


@dataclass
class EvaluationScores:
    """Container for all evaluation scores."""
    ils: float  # Immediate Liquidity Score (0-1 percentage)
    ils_profit: float  # Total profit from immediate liquidity
    sqs: float  # Spread Quality Score (1-10)
    obbs: float  # Order Book Balance Score (1-10)
    plr: float  # Position Limit Risk score (0-10)
    composite: float  # Weighted composite score (0-100)


@dataclass
class EvaluationResult:
    """Result of tender evaluation."""
    accept: bool
    scores: EvaluationScores
    reason: str
    projected_net_position: int
    projected_gross_position: int


class TenderEvaluator:
    """
    Evaluates tenders using a multi-factor scoring system.

    Calculates:
    - Immediate Liquidity Score (ILS): How much can be covered at profit
    - Spread Quality Score (SQS): How good is the tender spread
    - Order Book Balance Score (OBBS): Market conditions favor execution
    - Position Limit Risk (PLR): Risk of breaching position limits
    """

    def __init__(
        self,
        client: RITClient,
        config: AlgorithmConfig = DEFAULT_CONFIG,
    ):
        self.client = client
        self.config = config

    def evaluate(
        self,
        tender: Tender,
        current_positions: dict[str, int],
        time_remaining: float,
    ) -> EvaluationResult:
        """
        Evaluate a tender and decide whether to accept.

        Args:
            tender: The tender to evaluate
            current_positions: Dict mapping ticker to current position size
            time_remaining: Seconds remaining in the case

        Returns:
            EvaluationResult with decision and scores
        """
        ticker = tender.ticker or "CRZY"

        # Fetch market data
        try:
            securities = self.client.get_securities(ticker=ticker)
            security = securities[0] if securities else None
            book = self.client.get_security_book(ticker, limit=10)
        except Exception as e:
            logger.error(f"Failed to fetch market data: {e}")
            return EvaluationResult(
                accept=False,
                scores=EvaluationScores(0, 0, 0, 0, 0, 0),
                reason=f"API error: {e}",
                projected_net_position=0,
                projected_gross_position=0,
            )

        if not security:
            return EvaluationResult(
                accept=False,
                scores=EvaluationScores(0, 0, 0, 0, 0, 0),
                reason="Security not found",
                projected_net_position=0,
                projected_gross_position=0,
            )

        # Calculate position projections
        net_position = current_positions.get(ticker, 0)
        gross_position = sum(abs(p) for p in current_positions.values())

        # Tender direction: if tender action is BUY, we're selling to them (we get long)
        # If tender action is SELL, we're buying from them (we get short)
        signed_tender_size = tender.quantity if tender.action == "BUY" else -tender.quantity
        projected_net = net_position + signed_tender_size
        projected_gross = gross_position + abs(tender.quantity)

        # Calculate all scores
        ils, ils_profit = self._calculate_ils(tender, book, security)
        sqs = self._calculate_sqs(tender, security)
        obbs = self._calculate_obbs(tender, book)
        plr = self._calculate_plr(projected_net, projected_gross)

        # Calculate composite score
        composite = (
            (ils * 100 * self.config.weight_ils) +
            (sqs * self.config.weight_sqs * 10) +  # Normalize SQS to 0-100 contribution
            (obbs * self.config.weight_obbs * 10) +
            (plr * self.config.weight_plr * 10)
        )

        scores = EvaluationScores(
            ils=ils,
            ils_profit=ils_profit,
            sqs=sqs,
            obbs=obbs,
            plr=plr,
            composite=composite,
        )

        # Make decision
        accept, reason = self._make_decision(scores, ils, time_remaining)

        logger.info(
            f"Tender {tender.tender_id} evaluation: "
            f"ILS={ils:.2%}, SQS={sqs}, OBBS={obbs}, PLR={plr}, "
            f"Composite={composite:.1f}, Decision={'ACCEPT' if accept else 'DECLINE'}"
        )

        return EvaluationResult(
            accept=accept,
            scores=scores,
            reason=reason,
            projected_net_position=projected_net,
            projected_gross_position=projected_gross,
        )

    def _calculate_ils(
        self,
        tender: Tender,
        book: SecurityBook,
        security: Security,
    ) -> Tuple[float, float]:
        """
        Calculate Immediate Liquidity Score.

        For BUY tender (we need to SELL): Check bid side liquidity
        For SELL tender (we need to BUY): Check ask side liquidity

        Returns:
            Tuple of (ILS percentage 0-1, total profit available)
        """
        tender_size = tender.quantity
        tender_price = tender.price
        transaction_cost = self.config.transaction_cost_per_share

        remaining_shares = tender_size
        total_profit = 0.0

        if tender.action == "BUY":
            # We'll be selling - check bids (we want high bid prices)
            for level in book.bids:
                available = level.quantity - level.quantity_filled
                if available <= 0:
                    continue

                # Profit per share = bid_price - tender_price - transaction_cost
                profit_per_share = level.price - tender_price - transaction_cost

                if profit_per_share > 0:
                    coverable = min(remaining_shares, available)
                    total_profit += coverable * profit_per_share
                    remaining_shares -= coverable

                if remaining_shares <= 0:
                    break
        else:
            # We'll be buying - check asks (we want low ask prices)
            for level in book.asks:
                available = level.quantity - level.quantity_filled
                if available <= 0:
                    continue

                # Profit per share = tender_price - ask_price - transaction_cost
                profit_per_share = tender_price - level.price - transaction_cost

                if profit_per_share > 0:
                    coverable = min(remaining_shares, available)
                    total_profit += coverable * profit_per_share
                    remaining_shares -= coverable

                if remaining_shares <= 0:
                    break

        covered_shares = tender_size - remaining_shares
        ils_percentage = covered_shares / tender_size if tender_size > 0 else 0

        return ils_percentage, total_profit

    def _calculate_sqs(self, tender: Tender, security: Security) -> float:
        """
        Calculate Spread Quality Score.

        Measures how favorable the tender price is relative to market.
        Returns score from 1-10.
        """
        mid_price = (security.bid + security.ask) / 2
        if mid_price <= 0:
            return 1

        transaction_cost = self.config.transaction_cost_per_share

        if tender.action == "BUY":
            # They're buying from us at tender_price, we want high price
            spread_bps = (tender.price - mid_price) / mid_price * 10000
        else:
            # They're selling to us at tender_price, we want low price
            spread_bps = (mid_price - tender.price) / mid_price * 10000

        # Adjust for transaction costs
        net_spread_bps = spread_bps - (transaction_cost * 2 / mid_price * 10000)

        if net_spread_bps >= 100:  # 1% or better
            return 10
        elif net_spread_bps >= 50:  # 0.5-1%
            return 7
        elif net_spread_bps >= 30:  # 0.3-0.5%
            return 5
        elif net_spread_bps >= 20:  # 0.2-0.3%
            return 3
        else:
            return 1

    def _calculate_obbs(self, tender: Tender, book: SecurityBook) -> float:
        """
        Calculate Order Book Balance Score.

        For BUY tender (we sell): Want strong bid side
        For SELL tender (we buy): Want strong ask side
        Returns score from 1-10.
        """
        top_5_bid_volume = sum(
            (level.quantity - level.quantity_filled)
            for level in book.bids[:5]
        )
        top_5_ask_volume = sum(
            (level.quantity - level.quantity_filled)
            for level in book.asks[:5]
        )

        total_volume = top_5_bid_volume + top_5_ask_volume
        if total_volume == 0:
            return 5  # Neutral if no volume

        if tender.action == "BUY":
            # We'll sell - want strong bid side
            balance_ratio = top_5_bid_volume / total_volume
        else:
            # We'll buy - want strong ask side
            balance_ratio = top_5_ask_volume / total_volume

        if balance_ratio >= 0.60:
            return 10
        elif balance_ratio >= 0.50:
            return 7
        elif balance_ratio >= 0.40:
            return 5
        else:
            return 2

    def _calculate_plr(self, projected_net: int, projected_gross: int) -> float:
        """
        Calculate Position Limit Risk score.

        Returns score from 0-10 (0 = would breach limits).
        """
        net_utilization = abs(projected_net) / self.config.net_position_limit
        gross_utilization = projected_gross / self.config.gross_position_limit

        max_utilization = max(net_utilization, gross_utilization)

        if max_utilization > 1.0:
            return 0  # Would exceed limits
        elif max_utilization <= 0.70:
            return 10
        elif max_utilization <= 0.85:
            return 5
        elif max_utilization <= 0.95:
            return 2
        else:
            return 0

    def _make_decision(
        self,
        scores: EvaluationScores,
        ils_percentage: float,
        time_remaining: float,
    ) -> Tuple[bool, str]:
        """
        Make accept/decline decision based on scores.

        Returns:
            Tuple of (accept: bool, reason: str)
        """
        # Hard reject if would breach limits
        if scores.plr == 0:
            return False, "Would breach position limits"

        composite = scores.composite

        if composite >= self.config.accept_threshold_high:
            return True, f"High confidence (score={composite:.1f})"

        if composite >= self.config.accept_threshold_medium:
            return True, f"Moderate confidence (score={composite:.1f})"

        if composite >= self.config.accept_threshold_low:
            # Time pressure check
            if time_remaining < 120:  # Less than 2 minutes
                return False, f"Marginal score ({composite:.1f}) with time pressure"

            # ILS check
            if ils_percentage >= 0.5:
                return True, f"Marginal but 50%+ immediate coverage (score={composite:.1f})"

            return False, f"Marginal score ({composite:.1f}) with insufficient liquidity"

        return False, f"Score too low ({composite:.1f})"

    def validate_trade_safety(self, tender: Tender) -> Tuple[bool, str]:
        """
        Perform safety checks before accepting a tender.

        Returns:
            Tuple of (safe: bool, reason: str)
        """
        ticker = tender.ticker or "CRZY"

        # Check API connectivity
        try:
            securities = self.client.get_securities(ticker=ticker)
            if not securities:
                return False, "Could not fetch security data"
        except Exception as e:
            return False, f"API error: {e}"

        # Check order book sanity
        try:
            book = self.client.get_security_book(ticker, limit=5)
        except Exception as e:
            return False, f"Could not fetch order book: {e}"

        if len(book.bids) < self.config.min_book_depth:
            return False, "Insufficient bid depth"

        if len(book.asks) < self.config.min_book_depth:
            return False, "Insufficient ask depth"

        if book.bids and book.asks:
            spread = book.asks[0].price - book.bids[0].price
            if spread > self.config.max_acceptable_spread:
                return False, f"Abnormal spread ({spread:.2f})"

            if spread < 0:
                return False, "Crossed book detected"

        return True, "OK"
