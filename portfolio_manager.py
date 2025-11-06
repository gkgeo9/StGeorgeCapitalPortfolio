# portfolio_manager.py
"""
Core portfolio management logic.
Handles calculations, statistics, and portfolio operations using database.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
import time
from sqlalchemy import func, desc
from models import db, Price, Trade, Snapshot, PortfolioConfig


class PortfolioManager:
    """Manages portfolio operations and calculations"""

    def __init__(self, app=None):
        self.app = app
        if app:
            self.init_app(app)

    def init_app(self, app):
        """Initialize with Flask app context"""
        self.app = app
        self.stocks = app.config['PORTFOLIO_STOCKS']
        self.initial_cash = app.config['INITIAL_CASH']
        self.shares_per_trade = app.config['SHARES_PER_TRADE']
        self.max_retries = app.config['YFINANCE_MAX_RETRIES']
        self.retry_delay = app.config['YFINANCE_RETRY_DELAY']

    def initialize_portfolio(self):
        """Initialize portfolio configuration in database"""
        with self.app.app_context():
            # Set initial values if not exists
            if not PortfolioConfig.get_value('initial_cash'):
                PortfolioConfig.set_value('initial_cash', self.initial_cash)
                PortfolioConfig.set_value('start_date', datetime.now(timezone.utc).isoformat())
                print(f"✓ Initialized portfolio with ${self.initial_cash:,.2f}")

    def get_current_prices(self, use_cache=True) -> Dict[str, float]:
        """
        Get current prices for all stocks.
        With rate limit handling and database fallback.
        """
        prices = {}

        for attempt in range(self.max_retries):
            try:
                if attempt > 0:
                    time.sleep(self.retry_delay * (2 ** attempt))  # Exponential backoff

                for stock in self.stocks:
                    try:
                        ticker = yf.Ticker(stock)
                        hist = ticker.history(period='1d')

                        if not hist.empty:
                            prices[stock] = float(hist['Close'].iloc[-1])
                        else:
                            # Fallback to info
                            info = ticker.info
                            prices[stock] = float(info.get('regularMarketPrice', 0))

                        time.sleep(0.2)  # Rate limit protection

                    except Exception as e:
                        if "429" in str(e):
                            raise  # Re-raise to trigger retry
                        print(f"  Warning: Could not fetch {stock}: {e}")
                        prices[stock] = None

                # If we got all prices, return
                if all(v is not None for v in prices.values()):
                    return prices

                # Use database fallback for missing prices
                if use_cache:
                    prices = self._get_prices_from_db(prices)
                    return prices

                return prices

            except Exception as e:
                if "429" in str(e) and attempt < self.max_retries - 1:
                    print(f"  Rate limit hit, retrying in {self.retry_delay * (2 ** attempt)}s...")
                    continue
                else:
                    print(f"  Error fetching prices, using database fallback: {e}")
                    if use_cache:
                        return self._get_prices_from_db()

        # Last resort
        return self._get_prices_from_db()

    def _get_prices_from_db(self, partial_prices: Dict[str, float] = None) -> Dict[str, float]:
        """Get latest prices from database as fallback"""
        prices = partial_prices if partial_prices else {}

        for stock in self.stocks:
            if prices.get(stock) is None:
                latest_price = Price.query.filter_by(ticker=stock) \
                    .order_by(desc(Price.timestamp)) \
                    .first()

                if latest_price:
                    prices[stock] = float(latest_price.close)
                else:
                    prices[stock] = 100.0  # Default fallback

        return prices

    def backfill_prices(self, days: int = 365, force: bool = False):
        """
        Backfill historical price data from yfinance.
        Only fetches data we don't already have (unless force=True).
        """
        print(f"\n{'=' * 60}")
        print(f"BACKFILLING PRICE DATA ({days} days)")
        print(f"{'=' * 60}\n")

        end_date = datetime.now(timezone.utc)

        for stock in self.stocks:
            try:
                # Find last logged date for this stock
                if not force:
                    last_price = Price.query.filter_by(ticker=stock) \
                        .order_by(desc(Price.timestamp)) \
                        .first()

                    if last_price:
                        start_date = last_price.timestamp + timedelta(days=1)
                        print(f"[{stock}] Updating from {start_date.date()}...")
                    else:
                        start_date = end_date - timedelta(days=days)
                        print(f"[{stock}] Initial backfill from {start_date.date()}...")
                else:
                    start_date = end_date - timedelta(days=days)
                    print(f"[{stock}] Force backfill from {start_date.date()}...")

                # Skip if start_date is in the future
                if start_date.date() >= end_date.date():
                    print(f"[{stock}] Already up to date")
                    continue

                # Fetch data from yfinance
                ticker = yf.Ticker(stock)
                hist = ticker.history(
                    start=start_date.strftime('%Y-%m-%d'),
                    end=end_date.strftime('%Y-%m-%d'),
                    interval='1d',
                    auto_adjust=False
                )

                if hist.empty:
                    print(f"[{stock}] No data returned")
                    continue

                # Insert into database
                count = 0
                for timestamp, row in hist.iterrows():
                    price = Price(
                        ticker=stock,
                        timestamp=timestamp.to_pydatetime().replace(tzinfo=timezone.utc),
                        close=float(row['Close']),
                        open=float(row['Open']),
                        high=float(row['High']),
                        low=float(row['Low']),
                        volume=int(row['Volume']),
                        note='backfill'
                    )

                    # Check if already exists
                    existing = Price.query.filter_by(
                        ticker=stock,
                        timestamp=price.timestamp
                    ).first()

                    if not existing:
                        db.session.add(price)
                        count += 1

                db.session.commit()
                print(f"[{stock}] Added {count} new price records")

                time.sleep(0.5)  # Rate limit protection

            except Exception as e:
                print(f"[{stock}] Error during backfill: {e}")
                db.session.rollback()
                continue

        print(f"\n{'=' * 60}")
        print(f"BACKFILL COMPLETE")
        print(f"{'=' * 60}\n")

    def record_trade(self, ticker: str, action: str, quantity: int, price: float, note: str = ""):
        """Record a trade in the database"""
        if action not in ['BUY', 'SELL']:
            raise ValueError(f"Invalid action: {action}")

        if quantity <= 0:
            raise ValueError("Quantity must be positive")

        if price <= 0:
            raise ValueError("Price must be positive")

        total_cost = quantity * price

        trade = Trade(
            timestamp=datetime.now(timezone.utc),
            ticker=ticker,
            action=action,
            quantity=quantity,
            price=price,
            total_cost=total_cost,
            note=note
        )

        db.session.add(trade)
        db.session.commit()

        print(f"✓ Recorded {action}: {quantity} {ticker} @ ${price:.2f} = ${total_cost:,.2f}")

        return trade

    def take_snapshot(self, note: str = "scheduled"):
        """Take a snapshot of current portfolio state"""
        print(f"\n📸 Taking portfolio snapshot...")

        prices = self.get_current_prices()
        positions = self.get_current_positions()
        cash_balance = self.get_cash_balance()

        timestamp = datetime.now(timezone.utc)

        # Calculate total portfolio value
        stock_value = sum(positions[stock] * prices[stock] for stock in self.stocks)
        portfolio_value = stock_value + cash_balance

        # Create snapshot for each stock
        for stock in self.stocks:
            snapshot = Snapshot(
                timestamp=timestamp,
                ticker=stock,
                position=positions[stock],
                cash_balance=cash_balance,
                portfolio_value=portfolio_value,
                note=note
            )
            db.session.add(snapshot)

        db.session.commit()
        print(f"✓ Snapshot saved: Portfolio value ${portfolio_value:,.2f}")

    def get_current_positions(self) -> Dict[str, int]:
        """Get current stock positions by calculating from all trades"""
        positions = {stock: 0 for stock in self.stocks}

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

        # Calculate stock values
        stock_values = {}
        total_stock_value = 0

        for stock in self.stocks:
            shares = positions[stock]
            price = prices[stock]
            value = shares * price

            stock_values[stock] = {
                'shares': shares,
                'price': price,
                'value': value,
                'weight': 0  # Will calculate after total
            }
            total_stock_value += value

        # Calculate totals and percentages
        total_portfolio_value = total_stock_value + cash
        total_pnl = total_portfolio_value - initial_value
        pnl_percent = (total_pnl / initial_value * 100) if initial_value > 0 else 0

        # Calculate weights
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

        # Get unique timestamps from snapshots
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
        # Get portfolio timeline
        timeline = self.get_portfolio_timeline(days=365)

        if len(timeline['values']) < 2:
            return {
                'volatility': 0,
                'sharpe_ratio': 0,
                'max_drawdown': 0,
                'win_rate': 0
            }

        # Calculate returns
        values = np.array(timeline['values'])
        returns = np.diff(values) / values[:-1]

        # Volatility (annualized)
        volatility = float(np.std(returns) * np.sqrt(252) * 100) if len(returns) > 0 else 0

        # Max drawdown
        peak = values[0]
        max_dd = 0
        for value in values:
            if value > peak:
                peak = value
            dd = ((peak - value) / peak) * 100
            if dd > max_dd:
                max_dd = dd

        # Win rate from trades
        trades = Trade.query.filter_by(action='BUY').all()
        winning_trades = 0

        if trades:
            for trade in trades:
                # Get latest price for this stock
                latest_price = Price.query.filter_by(ticker=trade.ticker) \
                    .order_by(desc(Price.timestamp)) \
                    .first()

                if latest_price and float(latest_price.close) > float(trade.price):
                    winning_trades += 1

            win_rate = (winning_trades / len(trades) * 100)
        else:
            win_rate = 0

        # Sharpe ratio (simplified)
        risk_free_rate = 0.05 / 252  # Daily risk-free rate
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

        for stock in self.stocks:
            # Get first and last price
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