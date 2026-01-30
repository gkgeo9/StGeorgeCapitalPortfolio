# services/trade_service.py
"""
Trade execution and position tracking service.
"""

import logging
from datetime import datetime, timezone
from typing import Dict

from models import db, Trade, PortfolioConfig

logger = logging.getLogger(__name__)


class TradeService:
    """Handles trade execution, position tracking, and cash balance calculations."""

    def __init__(self, initial_cash: float, provider):
        self.initial_cash = initial_cash
        self.provider = provider

    def _validate_trade(self, ticker: str, action: str, quantity: int, price: float):
        """Validate trade parameters before execution."""
        if action not in {'BUY', 'SELL'}:
            raise ValueError(f"[{ticker}] invalid action: {action}")
        if not isinstance(quantity, int) or quantity <= 0:
            raise ValueError(f"[{ticker}] quantity must be positive integer")
        self.provider._assert_price(price, ticker, "trade")

    def _sanitize_note(self, s: str) -> str:
        """Sanitize note to prevent CSV injection attacks."""
        s = s or ""
        return "'" + s if s[:1] in ("=", "+", "-", "@") else s

    def record_trade(self, ticker: str, action: str, quantity: int, price: float,
                     note: str = "", timestamp: datetime = None, tracked_stocks: list = None) -> Trade:
        """
        Record a trade in the database with full validation and audit trail.

        Args:
            ticker: Stock ticker symbol
            action: 'BUY' or 'SELL'
            quantity: Number of shares
            price: Price per share
            note: Optional trade note
            timestamp: Optional trade timestamp (defaults to now)
            tracked_stocks: List of tracked stocks for position calculation

        Returns:
            Trade object

        Raises:
            ValueError: If validation fails
        """
        self._validate_trade(ticker, action, quantity, price)

        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        elif timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        if action == 'SELL':
            first_buy = Trade.query.filter_by(ticker=ticker, action='BUY').order_by(Trade.timestamp).first()
            if first_buy:
                first_buy_ts = first_buy.timestamp
                if first_buy_ts.tzinfo is None:
                    first_buy_ts = first_buy_ts.replace(tzinfo=timezone.utc)
                if timestamp < first_buy_ts:
                    raise ValueError(f"Cannot sell before first purchase on {first_buy.timestamp.strftime('%Y-%m-%d')}")

        total_cost = quantity * price
        positions, cash = self.get_positions_and_cash(tracked_stocks or [])
        position_before = positions.get(ticker, 0)
        cash_before = cash

        if action == 'BUY':
            position_after = position_before + quantity
            cash_after = cash_before - total_cost
        else:
            position_after = position_before - quantity
            cash_after = cash_before + total_cost

        if position_after < 0:
            raise ValueError(f"[{ticker}] position cannot go negative")
        if cash_after < 0:
            raise ValueError("Insufficient cash for this trade")

        event_id = Trade.generate_event_id(timestamp, ticker, action, quantity, price)

        trade = Trade(
            event_id=event_id,
            timestamp=timestamp,
            ticker=ticker,
            action=action,
            quantity=quantity,
            price=price,
            total_cost=total_cost,
            position_before=position_before,
            position_after=position_after,
            cash_before=cash_before,
            cash_after=cash_after,
            note=self._sanitize_note(note)
        )

        db.session.add(trade)
        db.session.commit()
        logger.info(f"Recorded {action}: {quantity} {ticker} @ ${price:.2f}")
        return trade

    def get_positions_and_cash(self, tracked_stocks: list) -> tuple:
        """
        Get positions and cash balance in single pass.
        Avoids loading trades twice for separate position/cash queries.
        """
        positions = {stock: 0 for stock in tracked_stocks}
        initial_cash = float(PortfolioConfig.get_value('initial_cash', self.initial_cash))
        cash = initial_cash

        trades = Trade.query.order_by(Trade.timestamp).all()
        for trade in trades:
            if trade.action == 'BUY':
                positions[trade.ticker] = positions.get(trade.ticker, 0) + trade.quantity
                cash -= float(trade.total_cost)
            elif trade.action == 'SELL':
                positions[trade.ticker] = positions.get(trade.ticker, 0) - trade.quantity
                cash += float(trade.total_cost)

        return positions, cash

    def get_current_positions(self, tracked_stocks: list) -> Dict[str, int]:
        """Get current stock positions by calculating from all trades."""
        positions, _ = self.get_positions_and_cash(tracked_stocks)
        return positions

    def get_cash_balance(self, tracked_stocks: list) -> float:
        """Calculate current cash balance from initial cash and all trades."""
        _, cash = self.get_positions_and_cash(tracked_stocks)
        return cash
