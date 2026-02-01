# services/analytics_service.py
"""
Portfolio analytics and performance metrics service.
"""

import bisect
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

import numpy as np
from sqlalchemy import func, desc

from models import db, Price, Snapshot, PortfolioConfig
from constants import (
    DEFAULT_TIMELINE_DAYS, DEFAULT_LOOKBACK_DAYS,
    DEFAULT_BENCHMARK_TICKER, DEFAULT_RISK_FREE_RATE
)

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Handles portfolio analytics, timeline, and performance calculations."""

    def __init__(self, initial_cash: float):
        self.initial_cash = initial_cash

    def calculate_portfolio_stats(self, prices: Dict[str, float], positions: Dict[str, int],
                                   cash: float, tracked_stocks: List[str],
                                   get_fallback_price_fn) -> Dict:
        """
        Calculate portfolio statistics using provided prices.

        Args:
            prices: Dict of ticker -> price
            positions: Dict of ticker -> shares
            cash: Current cash balance
            tracked_stocks: List of tracked stock tickers
            get_fallback_price_fn: Function to get fallback price from DB

        Returns:
            Dict with portfolio stats
        """
        initial_value = float(PortfolioConfig.get_value('initial_cash', self.initial_cash))

        stock_values = {}
        total_stock_value = 0

        for stock in tracked_stocks:
            shares = positions.get(stock, 0)
            price = prices.get(stock)

            if price is None:
                price = get_fallback_price_fn(stock)
                if price == 0.0 and shares > 0:
                    logger.warning(f"No price for {stock} with {shares} shares")

            value = shares * price
            stock_values[stock] = {'shares': shares, 'price': price, 'value': value, 'weight': 0}
            total_stock_value += value

        total_portfolio_value = total_stock_value + cash
        total_pnl = total_portfolio_value - initial_value
        pnl_percent = (total_pnl / initial_value * 100) if initial_value > 0 else 0

        for stock in stock_values:
            if total_portfolio_value > 0:
                stock_values[stock]['weight'] = (stock_values[stock]['value'] / total_portfolio_value * 100)

        return {
            'stock_values': stock_values,
            'prices': prices,
            'positions': positions,
            'total_stock_value': total_stock_value,
            'cash': cash,
            'total_portfolio_value': total_portfolio_value,
            'total_pnl': total_pnl,
            'pnl_percent': pnl_percent,
            'initial_value': initial_value
        }

    def _get_snapshots(self, days: int):
        """Get portfolio snapshots for the specified number of days."""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        return db.session.query(
            Snapshot.timestamp,
            func.max(Snapshot.portfolio_value).label('value')
        ).filter(
            Snapshot.timestamp >= cutoff_date
        ).group_by(Snapshot.timestamp).order_by(Snapshot.timestamp).all()

    def get_portfolio_timeline(self, days: int = DEFAULT_TIMELINE_DAYS) -> Dict:
        """Get portfolio value over time from snapshots."""
        snapshots = self._get_snapshots(days)
        return {
            'dates': [s.timestamp.isoformat() for s in snapshots],
            'values': [float(s.value) for s in snapshots]
        }

    def get_portfolio_timeline_with_benchmark(self, days: int = DEFAULT_TIMELINE_DAYS,
                                               benchmark_ticker: str = DEFAULT_BENCHMARK_TICKER) -> Dict:
        """
        Get portfolio timeline with benchmark comparison data.

        Returns dict containing:
        - dates: ISO format timestamps
        - values: Portfolio absolute values
        - portfolio_pct: Portfolio % change from start
        - benchmark_values: Benchmark prices aligned to dates
        - benchmark_pct: Benchmark % change from start
        - benchmark_ticker: The benchmark ticker used
        """
        snapshots = self._get_snapshots(days)

        if not snapshots:
            return {
                'dates': [], 'values': [], 'portfolio_pct': [],
                'benchmark_values': [], 'benchmark_pct': [], 'benchmark_ticker': benchmark_ticker
            }

        dates = [s.timestamp.isoformat() for s in snapshots]
        values = [float(s.value) for s in snapshots]

        initial_value = values[0] if values else 0
        portfolio_pct = [round(((v / initial_value) - 1) * 100, 2) if initial_value > 0 else 0 for v in values]

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        spy_prices = Price.query.filter(
            Price.ticker == benchmark_ticker,
            Price.timestamp >= cutoff_date
        ).order_by(Price.timestamp).all()

        spy_price_map = {p.timestamp.date(): float(p.close) for p in spy_prices}
        sorted_spy_dates = sorted(spy_price_map.keys())

        benchmark_values = []
        benchmark_pct = []
        spy_initial = None

        for s in snapshots:
            snapshot_date = s.timestamp.date()
            spy_price = spy_price_map.get(snapshot_date)

            if spy_price is None and sorted_spy_dates:
                idx = bisect.bisect_right(sorted_spy_dates, snapshot_date) - 1
                if idx >= 0:
                    spy_price = spy_price_map[sorted_spy_dates[idx]]

            benchmark_values.append(spy_price)

            if spy_price is not None:
                if spy_initial is None:
                    spy_initial = spy_price
                pct = ((spy_price / spy_initial) - 1) * 100 if spy_initial > 0 else 0
                benchmark_pct.append(round(pct, 2))
            else:
                benchmark_pct.append(None)

        return {
            'dates': dates,
            'values': values,
            'portfolio_pct': portfolio_pct,
            'benchmark_values': benchmark_values,
            'benchmark_pct': benchmark_pct,
            'benchmark_ticker': benchmark_ticker
        }

    def calculate_performance_metrics(self) -> Dict:
        """
        Calculate advanced performance metrics.

        Returns dict with:
        - volatility: Annualized volatility (daily std * sqrt(252) * 100)
        - sharpe_ratio: Annualized Sharpe ratio
        """
        timeline = self.get_portfolio_timeline(days=DEFAULT_LOOKBACK_DAYS)

        if len(timeline['values']) < 2:
            return {'volatility': 0, 'sharpe_ratio': 0}

        values = np.array(timeline['values'])
        daily_returns = np.diff(values) / values[:-1]

        daily_std = float(np.std(daily_returns)) if len(daily_returns) > 0 else 0
        volatility = daily_std * np.sqrt(252) * 100

        annual_rf = self.get_risk_free_rate()
        daily_rf = annual_rf / 252

        avg_daily_return = float(np.mean(daily_returns)) if len(daily_returns) > 0 else 0
        avg_excess_return = avg_daily_return - daily_rf

        if len(daily_returns) > 1 and daily_std > 0:
            sharpe = float(np.sqrt(252) * (avg_excess_return / daily_std))
        else:
            sharpe = 0

        return {'volatility': volatility, 'sharpe_ratio': sharpe}

    def get_risk_free_rate(self) -> float:
        """
        Get the current risk-free rate (annual).
        Uses stored rate from FRED API, falls back to default if not available.
        """
        stored_rate = PortfolioConfig.get_value('risk_free_rate')
        if stored_rate:
            try:
                return float(stored_rate)
            except (ValueError, TypeError):
                pass
        return DEFAULT_RISK_FREE_RATE

    def get_best_worst_stocks(self, tracked_stocks: List[str]) -> Tuple[str, str]:
        """Identify best and worst performing stocks based on price change."""
        best_stock = "N/A"
        worst_stock = "N/A"
        best_return = -float('inf')
        worst_return = float('inf')

        for stock in tracked_stocks:
            first_price = Price.query.filter_by(ticker=stock).order_by(Price.timestamp).first()
            last_price = Price.query.filter_by(ticker=stock).order_by(desc(Price.timestamp)).first()

            if first_price and last_price:
                first_val = float(first_price.close)
                last_val = float(last_price.close)
                ret = ((last_val - first_val) / first_val) * 100

                if ret > best_return:
                    best_return = ret
                    best_stock = f"{stock} (+{ret:.1f}%)"

                if ret < worst_return:
                    worst_return = ret
                    worst_stock = f"{stock} ({ret:+.1f}%)"

        return best_stock, worst_stock
