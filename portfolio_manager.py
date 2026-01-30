# portfolio_manager.py
"""
Core portfolio management facade.
Delegates to specialized services for cleaner separation of concerns.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from flask import g
from models import db, Price, Trade, PortfolioConfig
from providers import create_provider
from services.trade_service import TradeService
from services.price_service import PriceService
from services.snapshot_service import SnapshotService
from services.analytics_service import AnalyticsService
from constants import DEFAULT_LOOKBACK_DAYS, DEFAULT_TIMELINE_DAYS, DEFAULT_BENCHMARK_TICKER

logger = logging.getLogger(__name__)


class PortfolioManager:
    """
    Manages portfolio operations using Alpha Vantage price data.

    This is a facade that delegates to specialized services:
    - TradeService: Trade execution and position tracking
    - PriceService: Price fetching and backfill
    - SnapshotService: Portfolio snapshot creation
    - AnalyticsService: Performance calculations

    Maintains backward compatibility with existing API.
    """

    def __init__(self, app=None):
        self.app = app
        self._cooldown_seconds = 60
        self.provider = None
        self._trade_service = None
        self._price_service = None
        self._snapshot_service = None
        self._analytics_service = None
        if app:
            self.init_app(app)

    def init_app(self, app):
        """Initialize with Flask app context."""
        self.app = app
        self.default_stocks = app.config.get('DEFAULT_PORTFOLIO_STOCKS', [])
        self.initial_cash = app.config['INITIAL_CASH']
        self._cooldown_seconds = app.config.get('MANUAL_REFRESH_COOLDOWN', 60)
        self.provider = create_provider(app.config)

        # Initialize services
        self._trade_service = TradeService(self.initial_cash, self.provider)
        self._price_service = PriceService(self.provider, self._cooldown_seconds)
        self._snapshot_service = SnapshotService()
        self._analytics_service = AnalyticsService(self.initial_cash)

    def _validate_tickers(self, tickers: List[str]) -> List[str]:
        """Validate and clean ticker list. Delegates to provider."""
        return self.provider._validate_tickers(tickers)

    def _sanitize_note(self, s: str) -> str:
        """Sanitize note to prevent CSV injection attacks."""
        s = s or ""
        return "'" + s if s[:1] in ("=", "+", "-", "@") else s

    def get_tracked_stocks(self) -> List[str]:
        """
        Get list of all stocks currently tracked in the portfolio.
        Combines default stocks with any stocks present in trades or price history.
        Results are cached per-request to avoid repeated DB queries.
        """
        try:
            if hasattr(g, '_tracked_stocks_cache'):
                return g._tracked_stocks_cache
        except RuntimeError:
            pass

        trade_tickers = [t[0] for t in db.session.query(Trade.ticker).distinct().all()]
        price_tickers = [t[0] for t in db.session.query(Price.ticker).distinct().all()]
        all_tickers = set(trade_tickers + price_tickers)

        result = sorted(list(all_tickers)) if all_tickers else self.default_stocks

        try:
            g._tracked_stocks_cache = result
        except RuntimeError:
            pass

        return result

    def initialize_portfolio(self):
        """Initialize portfolio configuration in database."""
        with self.app.app_context():
            if not PortfolioConfig.get_value('initial_cash'):
                PortfolioConfig.set_value('initial_cash', self.initial_cash)
                PortfolioConfig.set_value('start_date', datetime.now(timezone.utc).isoformat())
                logger.info(f"Initialized portfolio with ${self.initial_cash:,.2f}")

    # Price fetching - delegated to PriceService
    def get_prices_from_db(self) -> Dict[str, float]:
        """Get latest prices from database only - no API calls."""
        return self._price_service.get_prices_from_db(self.get_tracked_stocks())

    def fetch_live_prices(self) -> Dict[str, float]:
        """
        Fetch live prices from Alpha Vantage API.
        Falls back to database cache if API fails.
        """
        return self._price_service.fetch_live_prices(self.get_tracked_stocks())

    def _get_prices_from_db(self, partial_prices: Dict[str, float] = None) -> Dict[str, float]:
        """Get latest prices from database using optimized single query."""
        return self._price_service._get_prices_from_db(self.get_tracked_stocks(), partial_prices)

    def _get_fallback_price_from_db(self, ticker: str) -> float:
        """Get fallback price from database for a single ticker."""
        return self._price_service.get_fallback_price_from_db(ticker)

    # Backfill - delegated to PriceService
    def manual_backfill(self, default_lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> Tuple[bool, str]:
        """
        Manual backfill triggered by user.
        Ensures all tracked stocks have at least 1 year of historical data.
        Uses database-backed cooldown to prevent race conditions.
        """
        return self._price_service.manual_backfill(self.get_tracked_stocks(), default_lookback_days)

    def _last_logged_day(self) -> Optional[datetime]:
        """Get the most recent datetime we have price data for."""
        return self._price_service.last_logged_day()

    def backfill_prices(self, start_date, end_date, note: str = "backfill", ticker_specific: str = None) -> Dict:
        """
        Backfill historical price data using configured provider.
        Returns dict with success status and counts per ticker.
        """
        return self._price_service.backfill_prices(start_date, end_date, note, ticker_specific)

    # Trading - delegated to TradeService
    def record_trade(self, ticker: str, action: str, quantity: int, price: float, note: str = "", timestamp: datetime = None):
        """
        Record a trade in the database with full validation and audit trail.

        Args:
            ticker: Stock ticker symbol
            action: 'BUY' or 'SELL'
            quantity: Number of shares
            price: Price per share
            note: Optional trade note
            timestamp: Optional trade timestamp (defaults to now)

        Returns:
            Trade object

        Raises:
            ValueError: If validation fails
        """
        return self._trade_service.record_trade(ticker, action, quantity, price, note, timestamp, self.get_tracked_stocks())

    # Snapshots - delegated to SnapshotService
    def take_snapshot(self, note: str = "manual snapshot"):
        """
        Take a snapshot of current portfolio state using database prices only.
        No API calls are made during snapshot.
        """
        prices = self.get_prices_from_db()
        positions = self.get_current_positions()
        cash_balance = self.get_cash_balance()
        return self._snapshot_service.take_snapshot(prices, positions, cash_balance, self.get_tracked_stocks(), note)

    # Portfolio calculations - delegated to TradeService and AnalyticsService
    def get_positions_and_cash(self) -> tuple:
        """
        Get positions and cash balance in single pass.
        Avoids loading trades twice for separate position/cash queries.
        """
        return self._trade_service.get_positions_and_cash(self.get_tracked_stocks())

    def get_current_positions(self) -> Dict[str, int]:
        """Get current stock positions by calculating from all trades."""
        return self._trade_service.get_current_positions(self.get_tracked_stocks())

    def get_cash_balance(self) -> float:
        """Calculate current cash balance from initial cash and all trades."""
        return self._trade_service.get_cash_balance(self.get_tracked_stocks())

    def calculate_portfolio_stats(self) -> Dict:
        """Calculate portfolio statistics using database prices only (no API calls)."""
        prices = self.get_prices_from_db()
        positions, cash = self.get_positions_and_cash()
        return self._analytics_service.calculate_portfolio_stats(
            prices, positions, cash, self.get_tracked_stocks(),
            self._get_fallback_price_from_db
        )

    def _get_snapshots(self, days: int):
        """Get portfolio snapshots for the specified number of days."""
        return self._analytics_service._get_snapshots(days)

    def get_portfolio_timeline(self, days: int = DEFAULT_TIMELINE_DAYS) -> Dict:
        """Get portfolio value over time from snapshots."""
        return self._analytics_service.get_portfolio_timeline(days)

    def get_portfolio_timeline_with_benchmark(self, days: int = DEFAULT_TIMELINE_DAYS, benchmark_ticker: str = DEFAULT_BENCHMARK_TICKER) -> Dict:
        """
        Get portfolio timeline with benchmark (default SPY) comparison data.

        Returns dict containing:
        - dates: ISO format timestamps
        - values: Portfolio absolute values
        - portfolio_pct: Portfolio % change from start
        - benchmark_values: Benchmark prices aligned to dates
        - benchmark_pct: Benchmark % change from start
        - benchmark_ticker: The benchmark ticker used
        """
        return self._analytics_service.get_portfolio_timeline_with_benchmark(days, benchmark_ticker)

    def calculate_performance_metrics(self) -> Dict:
        """
        Calculate advanced performance metrics.

        Returns dict with:
        - volatility: Annualized volatility (daily std * sqrt(252) * 100)
        - sharpe_ratio: Annualized Sharpe ratio
        """
        return self._analytics_service.calculate_performance_metrics()

    def get_risk_free_rate(self) -> float:
        """
        Get the current risk-free rate (annual).
        Uses stored rate from FRED API, falls back to default if not available.
        """
        return self._analytics_service.get_risk_free_rate()

    def get_best_worst_stocks(self) -> Tuple[str, str]:
        """Identify best and worst performing stocks based on price change."""
        return self._analytics_service.get_best_worst_stocks(self.get_tracked_stocks())
