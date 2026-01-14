# portfolio_manager.py
"""
Core portfolio management logic with provider abstraction.
Now uses pluggable price providers (yfinance OR Alpha Vantage).
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
import time
from sqlalchemy import func, desc
from models import db, Price, Trade, Snapshot, PortfolioConfig
from providers import PriceDataService


class PortfolioManager:
    """Manages portfolio operations with pluggable price providers"""

    def __init__(self, app=None):
        self.app = app
        self._last_backfill_ts = None
        self._cooldown_seconds = 60  # Default, will be overridden by config
        self.provider = None  # Will be initialized in init_app
        if app:
            self.init_app(app)

    def init_app(self, app):
        """Initialize with Flask app context"""
        self.app = app
        self.stocks = [] # Deprecated, use get_tracked_stocks()
        self.default_stocks = app.config.get('DEFAULT_PORTFOLIO_STOCKS', [])
        self.initial_cash = app.config['INITIAL_CASH']
        self.shares_per_trade = app.config['SHARES_PER_TRADE']
        self.max_retries = app.config['YFINANCE_MAX_RETRIES']
        self.retry_delay = app.config['YFINANCE_RETRY_DELAY']
        self._cooldown_seconds = app.config.get('MANUAL_REFRESH_COOLDOWN', 60)

        # Initialize price provider (auto-selects based on config/env)
        self.provider = PriceDataService.create_provider(app.config)
        print(f"  Portfolio Manager using: {self.provider.get_provider_name()}")

    # ========================================
    # VALIDATION METHODS (delegated to provider)
    # ========================================

    def _validate_tickers(self, tickers: List[str]) -> List[str]:
        """Delegate to provider"""
        return self.provider._validate_tickers(tickers)

    def _assert_action(self, action: str, ticker: str) -> None:
        """Validate trade action"""
        if action not in {'BUY', 'SELL', 'NONE'}:
            raise ValueError(f"[{ticker}] invalid action: {action}")

    def _assert_quantity(self, qty: int, ticker: str, action: str) -> None:
        """Validate trade quantity"""
        if not isinstance(qty, int):
            raise ValueError(f"[{ticker}] qty must be int")
        if action == 'NONE' and qty != 0:
            raise ValueError(f"[{ticker}] qty must be 0 for NONE")
        if action in {'BUY', 'SELL'} and qty <= 0:
            raise ValueError(f"[{ticker}] qty must be >0 for {action}")

    def _assert_position(self, pos_after: int, ticker: str, action: str, qty: int) -> None:
        """Validate position after trade"""
        if not isinstance(pos_after, int):
            raise ValueError(f"[{ticker}] position_after must be int")
        if pos_after < 0:
            raise ValueError(f"[{ticker}] position_after cannot be negative")

    def _assert_price(self, price: float, ticker: str, context: str) -> None:
        """Delegate to provider"""
        self.provider._assert_price(price, ticker, context)

    def _assert_cash(self, cash_after: float) -> None:
        """Validate cash balance"""
        try:
            c = float(cash_after)
        except Exception:
            raise ValueError("cash_after must be numeric")
        if c < 0:
            raise ValueError("cash_after cannot be negative")

    def _sanitize_note(self, s: str) -> str:
        """Sanitize note to prevent CSV injection"""
        s = s or ""
        return "'" + s if s[:1] in ("=", "+", "-", "@") else s

    # ========================================
    # DYNAMIC STOCK MANAGEMENT
    # ========================================

    def get_tracked_stocks(self) -> List[str]:
        """
        Get list of all stocks currently tracked in the portfolio.
        Combines default stocks (if DB empty) with any stocks present in positions or history.
        """
        # Get stocks from trades (positions)
        trade_tickers = db.session.query(Trade.ticker).distinct().all()
        trade_tickers = [t[0] for t in trade_tickers]

        # Get stocks from price history
        price_tickers = db.session.query(Price.ticker).distinct().all()
        price_tickers = [t[0] for t in price_tickers]

        # Combine unique tickers
        all_tickers = set(trade_tickers + price_tickers)

        # If database is empty, return defaults
        if not all_tickers:
            return self.default_stocks

        return sorted(list(all_tickers))

    # ========================================
    # INITIALIZATION
    # ========================================

    def initialize_portfolio(self):
        """Initialize portfolio configuration in database"""
        with self.app.app_context():
            if not PortfolioConfig.get_value('initial_cash'):
                PortfolioConfig.set_value('initial_cash', self.initial_cash)
                PortfolioConfig.set_value('start_date', datetime.now(timezone.utc).isoformat())
                print(f"✓ Initialized portfolio with ${self.initial_cash:,.2f}")

    # ========================================
    # PRICE FETCHING (now uses provider)
    # ========================================

    def get_current_prices(self, use_cache=True) -> Dict[str, float]:
        """
        Get current prices using configured provider.
        Falls back to database cache if provider fails.
        """
        try:
            # Use provider to get prices
            prices = self.provider.get_current_prices(self.stocks)

            # Check for None values (failed fetches)
            failed = [ticker for ticker, price in prices.items() if price is None]

            if failed and use_cache:
                print(f"  Some tickers failed: {failed}, using database cache...")
                prices = self._get_prices_from_db(prices)

            return prices

        except Exception as e:
            print(f"  Provider error: {e}")
            if use_cache:
                print(f"  Falling back to database cache...")
                return self._get_prices_from_db()
            raise

    def _get_prices_from_db(self, partial_prices: Dict[str, float] = None) -> Dict[str, float]:
        """Get latest prices from database as fallback"""
        prices = partial_prices if partial_prices else {}
        stocks = self.get_tracked_stocks()

        for stock in stocks:
            if prices.get(stock) is None:
                latest_price = Price.query.filter_by(ticker=stock) \
                    .order_by(desc(Price.timestamp)) \
                    .first()

                if latest_price:
                    prices[stock] = float(latest_price.close)
                else:
                    # Return 0.0 instead of hardcoded $100 - this indicates missing data
                    prices[stock] = 0.0
                    print(f"  WARNING: No price data available for {stock} - using $0.00")

        return prices

    def _get_fallback_price_from_db(self, ticker: str) -> float:
        """Get fallback price from database for a single ticker"""
        latest_price = Price.query.filter_by(ticker=ticker) \
            .order_by(desc(Price.timestamp)) \
            .first()

        if latest_price:
            return float(latest_price.close)
        return 0.0

    # ========================================
    # BACKFILL (now uses provider)
    # ========================================

    def manual_backfill(self, default_lookback_days: int = 7) -> Tuple[bool, str]:
        """
        Manual backfill triggered by user button.
        Has cooldown to avoid rate limits.
        Returns (success, message)
        """
        now = datetime.now(timezone.utc)

        # Check cooldown
        if self._last_backfill_ts:
            elapsed = (now - self._last_backfill_ts).total_seconds()
            if elapsed < self._cooldown_seconds:
                remaining = int(self._cooldown_seconds - elapsed)
                return False, f"⏳ Cooldown active. Please wait {remaining} seconds before refreshing again."

        # Determine date range
        today = now.date()
        last_datetime = self._last_logged_day()

        if last_datetime is None:
            start_date = today - timedelta(days=default_lookback_days)
            message_prefix = "Initial backfill"
        else:
            last_date = last_datetime.date() if isinstance(last_datetime, datetime) else last_datetime
            start_date = last_date + timedelta(days=1)

            if start_date > today:
                return False, "✓ Already up to date"
            message_prefix = "Incremental backfill"

        end_date = today

        # Run backfill
        result = self.backfill_prices(
            start_date=start_date,
            end_date=end_date,
            note="manual backfill"
        )

        self._last_backfill_ts = now

        if result['success']:
            total_added = sum(result['counts'].values())
            return True, f"✓ {message_prefix}: Added {total_added} price records"
        else:
            return False, f"⚠️ Backfill failed: {result.get('error', 'Unknown error')}"

    def _last_logged_day(self) -> Optional[datetime]:
        """Get the most recent datetime we have price data for"""
        latest = db.session.query(func.max(Price.timestamp)).scalar()
        if latest:
            return latest.replace(hour=0, minute=0, second=0, microsecond=0)
        return None

    def backfill_prices(self, start_date, end_date, note: str = "backfill") -> Dict:
        """
        Backfill historical price data using configured provider.
        Returns dict with success status and counts.
        """
        print(f"\n{'=' * 60}")
        print(f"BACKFILLING PRICE DATA")
        print(f"Using provider: {self.provider.get_provider_name()}")
        print(f"{'=' * 60}\n")

        result = {
            'success': True,
            'counts': {},
            'error': None
        }

        stocks = self.get_tracked_stocks()
        for stock in stocks:
            try:
                print(f"[{stock}] Fetching historical data...")

                # Use provider to get historical data
                df = self.provider.get_historical_prices(stock, start_date, end_date)

                if df.empty:
                    print(f"[{stock}] No data returned")
                    result['counts'][stock] = 0
                    continue

                count = 0
                for _, row in df.iterrows():
                    try:
                        event_id = Price.generate_event_id(
                            ticker=stock,
                            timestamp=row['timestamp'],
                            close=row['close'],
                            kind='HISTORY',
                            note=note
                        )

                        existing = Price.query.filter_by(event_id=event_id).first()
                        if existing:
                            continue

                        price = Price(
                            event_id=event_id,
                            ticker=stock,
                            timestamp=row['timestamp'],
                            close=row['close'],
                            open=row.get('open'),
                            high=row.get('high'),
                            low=row.get('low'),
                            volume=row.get('volume'),
                            kind='HISTORY',
                            price_source=self.provider.get_provider_name(),
                            out_of_order=False,
                            note=note
                        )

                        db.session.add(price)
                        count += 1

                    except Exception as e:
                        print(f"[{stock}] Error processing row: {e}")
                        continue

                db.session.commit()
                result['counts'][stock] = count
                print(f"[{stock}] Added {count} new price records")

            except Exception as e:
                print(f"[{stock}] Error during backfill: {e}")
                result['success'] = False
                result['error'] = str(e)
                result['counts'][stock] = 0
                db.session.rollback()
                continue

        print(f"\n{'=' * 60}")
        print(f"BACKFILL COMPLETE")
        print(f"{'=' * 60}\n")

        return result

    # ========================================
    # TRADING (unchanged)
    # ========================================

    def record_trade(self, ticker: str, action: str, quantity: int, price: float, note: str = ""):
        """Record a trade in the database with full validation"""
        # Validate inputs
        self._assert_action(action, ticker)
        self._assert_quantity(quantity, ticker, action)
        self._assert_price(price, ticker, "record_trade")

        if action not in ['BUY', 'SELL']:
            raise ValueError(f"Invalid action: {action}")

        total_cost = quantity * price

        # Get current state
        positions = self.get_current_positions()
        cash_before = self.get_cash_balance()
        position_before = positions.get(ticker, 0)

        # Calculate new state
        if action == 'BUY':
            position_after = position_before + quantity
            cash_after = cash_before - total_cost
        else:  # SELL
            position_after = position_before - quantity
            cash_after = cash_before + total_cost

        # Final validations
        self._assert_position(position_after, ticker, action, quantity)
        self._assert_cash(cash_after)

        timestamp = datetime.now(timezone.utc)
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

        print(f"✓ Recorded {action}: {quantity} {ticker} @ ${price:.2f} = ${total_cost:,.2f}")

        return trade

    # ========================================
    # SNAPSHOTS (unchanged)
    # ========================================

    def take_snapshot(self, note: str = "manual snapshot"):
        """Take a snapshot of current portfolio state"""
        print(f"\n📸 Taking portfolio snapshot...")

        prices = self.get_current_prices()
        positions = self.get_current_positions()
        cash_balance = self.get_cash_balance()

        timestamp = datetime.now(timezone.utc)

        stocks = self.get_tracked_stocks()
        stock_value = sum(positions.get(stock, 0) * prices.get(stock, 0) for stock in stocks)
        portfolio_value = stock_value + cash_balance

        for stock in stocks:
            event_id = Snapshot.generate_event_id(timestamp, stock, positions[stock])

            existing = Snapshot.query.filter_by(event_id=event_id).first()
            if existing:
                continue

            snapshot = Snapshot(
                event_id=event_id,
                timestamp=timestamp,
                ticker=stock,
                position=positions[stock],
                cash_balance=cash_balance,
                portfolio_value=portfolio_value,
                note=self._sanitize_note(note)
            )
            db.session.add(snapshot)

        db.session.commit()
        print(f"✓ Snapshot saved: Portfolio value ${portfolio_value:,.2f}")

        return {'success': True, 'portfolio_value': portfolio_value}

    # ========================================
    # PORTFOLIO CALCULATIONS (unchanged)
    # ========================================

    def get_current_positions(self) -> Dict[str, int]:
        """Get current stock positions by calculating from all trades"""
        stocks = self.get_tracked_stocks()
        positions = {stock: 0 for stock in stocks}

        trades = Trade.query.order_by(Trade.timestamp).all()

        for trade in trades:
            if trade.action == 'BUY':
                positions[trade.ticker] += trade.quantity
            elif trade.action == 'SELL':
                positions[trade.ticker] -= trade.quantity

        return positions

    def get_cash_balance(self) -> float:
        """Calculate current cash balance from initial cash and all trades"""
        initial_cash = float(PortfolioConfig.get_value('initial_cash', self.initial_cash))

        trades = Trade.query.order_by(Trade.timestamp).all()

        cash = initial_cash
        for trade in trades:
            if trade.action == 'BUY':
                cash -= float(trade.total_cost)
            elif trade.action == 'SELL':
                cash += float(trade.total_cost)

        return cash

    def calculate_portfolio_stats(self) -> Dict:
        """Calculate comprehensive portfolio statistics"""
        prices = self.get_current_prices()
        positions = self.get_current_positions()
        cash = self.get_cash_balance()
        initial_value = float(PortfolioConfig.get_value('initial_cash', self.initial_cash))

        stock_values = {}
        total_stock_value = 0

        stocks = self.get_tracked_stocks()
        for stock in stocks:
            shares = positions[stock]
            price = prices.get(stock)

            # Handle None prices gracefully
            if price is None:
                price = self._get_fallback_price_from_db(stock)
                if price == 0.0 and shares > 0:
                    print(f"  WARNING: No price for {stock} with {shares} shares - value will be $0")

            value = shares * price

            stock_values[stock] = {
                'shares': shares,
                'price': price,
                'value': value,
                'weight': 0
            }
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

    def get_portfolio_timeline(self, days: int = 90) -> Dict:
        """Get portfolio value over time from snapshots"""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        snapshots = db.session.query(
            Snapshot.timestamp,
            func.max(Snapshot.portfolio_value).label('value')
        ).filter(
            Snapshot.timestamp >= cutoff_date
        ).group_by(
            Snapshot.timestamp
        ).order_by(
            Snapshot.timestamp
        ).all()

        dates = [s.timestamp.isoformat() for s in snapshots]
        values = [float(s.value) for s in snapshots]

        return {
            'dates': dates,
            'values': values
        }

    def calculate_performance_metrics(self) -> Dict:
        """Calculate advanced performance metrics"""
        timeline = self.get_portfolio_timeline(days=365)

        if len(timeline['values']) < 2:
            return {
                'volatility': 0,
                'sharpe_ratio': 0,
                'max_drawdown': 0,
                'win_rate': 0
            }

        values = np.array(timeline['values'])
        returns = np.diff(values) / values[:-1]

        volatility = float(np.std(returns) * np.sqrt(252) * 100) if len(returns) > 0 else 0

        peak = values[0]
        max_dd = 0
        for value in values:
            if value > peak:
                peak = value
            dd = ((peak - value) / peak) * 100
            if dd > max_dd:
                max_dd = dd

        trades = Trade.query.filter_by(action='BUY').all()
        winning_trades = 0

        if trades:
            for trade in trades:
                latest_price = Price.query.filter_by(ticker=trade.ticker) \
                    .order_by(desc(Price.timestamp)) \
                    .first()

                if latest_price and float(latest_price.close) > float(trade.price):
                    winning_trades += 1

            win_rate = (winning_trades / len(trades) * 100)
        else:
            win_rate = 0

        risk_free_rate = 0.05 / 252
        excess_returns = returns - risk_free_rate
        sharpe = float(np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252)) if len(returns) > 1 and np.std(
            excess_returns) > 0 else 0

        return {
            'volatility': volatility,
            'sharpe_ratio': sharpe,
            'max_drawdown': max_dd,
            'win_rate': win_rate
        }

    def get_best_worst_stocks(self) -> Tuple[str, str]:
        """Identify best and worst performing stocks"""
        best_stock = "N/A"
        worst_stock = "N/A"
        best_return = -float('inf')
        worst_return = float('inf')

        stocks = self.get_tracked_stocks()
        for stock in stocks:
            first_price = Price.query.filter_by(ticker=stock) \
                .order_by(Price.timestamp) \
                .first()

            last_price = Price.query.filter_by(ticker=stock) \
                .order_by(desc(Price.timestamp)) \
                .first()

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