# portfolio_manager.py
"""
Core portfolio management logic using Alpha Vantage API.
"""

import numpy as np
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from sqlalchemy import func, desc
from models import db, Price, Trade, Snapshot, PortfolioConfig
from providers import create_provider


class PortfolioManager:
    """Manages portfolio operations using Alpha Vantage price data."""

    def __init__(self, app=None):
        self.app = app
        self._last_backfill_ts = None
        self._cooldown_seconds = 60
        self.provider = None
        if app:
            self.init_app(app)

    def init_app(self, app):
        """Initialize with Flask app context"""
        self.app = app
        self.default_stocks = app.config.get('DEFAULT_PORTFOLIO_STOCKS', [])
        self.initial_cash = app.config['INITIAL_CASH']
        self._cooldown_seconds = app.config.get('MANUAL_REFRESH_COOLDOWN', 60)

        self.provider = create_provider(app.config)

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
    # PRICE FETCHING
    # ========================================

    def get_prices_from_db(self) -> Dict[str, float]:
        """
        Get latest prices from DATABASE ONLY - NO API CALLS.
        Used for displaying portfolio data without hitting rate limits.
        """
        return self._get_prices_from_db()

    def fetch_live_prices(self) -> Dict[str, float]:
        """
        Fetch LIVE prices from Alpha Vantage API.
        ONLY called during manual refresh - NEVER automatically.
        """
        stocks = self.get_tracked_stocks()
        print(f"  Fetching live prices for {len(stocks)} stocks...")
        try:
            prices = self.provider.get_current_prices(stocks)

            failed = [ticker for ticker, price in prices.items() if price is None]
            if failed:
                print(f"  Some tickers failed: {failed}, filling from database...")
                prices = self._get_prices_from_db(prices)

            return prices

        except Exception as e:
            print(f"  Provider error: {e}")
            print(f"  Falling back to database cache...")
            return self._get_prices_from_db()

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

    def manual_backfill(self, default_lookback_days: int = 365) -> Tuple[bool, str]:
        """
        Manual backfill triggered by user button.
        Ensures ALL tracked stocks have at least 1 year of data.
        """
        now = datetime.now(timezone.utc)

        # Check cooldown
        if self._last_backfill_ts:
            elapsed = (now - self._last_backfill_ts).total_seconds()
            if elapsed < self._cooldown_seconds:
                remaining = int(self._cooldown_seconds - elapsed)
                return False, f"⏳ Cooldown active. Please wait {remaining} seconds before refreshing again."

        print(f"\n{'=' * 60}")
        print(f"STARTING MANUAL BACKFILL")
        print(f"{'=' * 60}")

        stocks = self.get_tracked_stocks()
        if not stocks:
            return True, "No stocks to backfill."

        # Include SPY benchmark for comparison charts
        if 'SPY' not in stocks:
            stocks = stocks + ['SPY']

        total_added = 0
        errors = []

        year_ago = now - timedelta(days=365)
        # Buffer to capture partial years that are 'close enough' but we want full year
        # Actually, let's just be strict: if min_date > year_ago + 5 days, fetch history.

        for stock in stocks:
            try:
                # 1. Get current data range for this stock
                min_ts = db.session.query(func.min(Price.timestamp)).filter_by(ticker=stock).scalar()
                max_ts = db.session.query(func.max(Price.timestamp)).filter_by(ticker=stock).scalar()
                
                # Make timezone aware if needed (DB usually returns naive if not careful, but let's assume UTC)
                if min_ts and min_ts.tzinfo is None: min_ts = min_ts.replace(tzinfo=timezone.utc)
                if max_ts and max_ts.tzinfo is None: max_ts = max_ts.replace(tzinfo=timezone.utc)

                start_date = None
                end_date = now.date()
                
                # Logic:
                # Case A: No data -> Backfill 1 year
                # Case B: Data is old (max_ts < yesterday) -> Update to today
                # Case C: Data is recent but not enough history (min_ts > year_ago) -> Backfill to year_ago

                fetch_needed = False
                
                if not min_ts or not max_ts:
                    print(f"[{stock}] No data found. Scheduling full backfill.")
                    start_date = year_ago.date()
                    fetch_needed = True
                
                else:
                    # Check if we need recent data
                    if max_ts.date() < (now - timedelta(days=1)).date():
                         print(f"[{stock}] Data stale (last: {max_ts.date()}). Updating...")
                         # We can just fetch from max_ts to now. 
                         # BUT if we ALSo need history, we should just do one big fetch or two?
                         # AlphaVantage 'full' gives everything. 'compact' gives 100 days.
                         # If we request start_date=year_ago, provider logic handles 'full' vs 'compact'.
                         start_date = max_ts.date() + timedelta(days=1)
                         fetch_needed = True

                    # Check if we need MORE history
                    # If existing history starts AFTER year_ago (plus small buffer), we need older data.
                    if min_ts > (year_ago + timedelta(days=5)):
                         print(f"[{stock}] Insufficient history (starts: {min_ts.date()}). Extending back to {year_ago.date()}...")
                         start_date = year_ago.date() # This overrides the "update only" start date, which is good.
                         fetch_needed = True

                if fetch_needed:
                    result = self.backfill_prices(
                        start_date=start_date,
                        end_date=end_date,
                        note="manual backfill",
                        ticker_specific=stock # Optimization: Only pass this stock to backfill_prices
                    )
                    
                    if result['success']:
                         count = result['counts'].get(stock, 0)
                         total_added += count
                    else:
                        errors.append(f"{stock}: {result.get('error')}")

                else:
                    print(f"[{stock}] Data is up to date (Range: {min_ts.date()} to {max_ts.date()})")

            except Exception as e:
                print(f"[{stock}] Error determining backfill needs: {e}")
                errors.append(f"{stock}: {str(e)}")

        self._last_backfill_ts = now

        msg = f"✓ Updated data. Added {total_added} records."
        if errors:
            msg += f" (Errors: {', '.join(errors[:3])}...)"
        return True, msg

    def _last_logged_day(self) -> Optional[datetime]:
        """Get the most recent datetime we have price data for"""
        latest = db.session.query(func.max(Price.timestamp)).scalar()
        if latest:
            return latest.replace(hour=0, minute=0, second=0, microsecond=0)
        return None

    def backfill_prices(self, start_date, end_date, note: str = "backfill", ticker_specific: str = None) -> Dict:
        """
        Backfill historical price data using configured provider.
        Returns dict with success status and counts.
        """
        result = {
            'success': True,
            'counts': {},
            'error': None
        }

        if ticker_specific:
            stocks = [ticker_specific]
        else:
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

                # Pre-fetch existing event_ids for this stock to avoid N+1 queries
                existing_ids_query = db.session.query(Price.event_id).filter(
                    Price.ticker == stock,
                    Price.timestamp >= start_date
                ).all()
                existing_event_ids = {row[0] for row in existing_ids_query}

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

                        if event_id in existing_event_ids:
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

    def record_trade(self, ticker: str, action: str, quantity: int, price: float, note: str = "", timestamp: datetime = None):
        """Record a trade in the database with full validation"""
        # Validate inputs
        self._assert_action(action, ticker)
        self._assert_quantity(quantity, ticker, action)
        self._assert_price(price, ticker, "record_trade")

        if action not in ['BUY', 'SELL']:
            raise ValueError(f"Invalid action: {action}")

        # Use current time if no timestamp provided
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        
        # Validation for backdated sells: Cannot sell before first purchase
        if action == 'SELL':
            first_buy = Trade.query.filter_by(ticker=ticker, action='BUY').order_by(Trade.timestamp).first()
            if first_buy and timestamp < first_buy.timestamp:
                 # Check if the date is earlier (ignoring time for user friendliness if needed, 
                 # but strictly timestamp comparison is safer for data integrity)
                 raise ValueError(f"Cannot sell before first purchase on {first_buy.timestamp.strftime('%Y-%m-%d')}")
            
            # If there are NO buys, it implies we are selling something we don't have record of buying.
            # This is generally allowed in this system if we assume initial balances or such, 
            # but strictly speaking it's odd. However, for "sell date earlier than buy date" check,
            # we only care if a buy EXISTS and is LATER than this sell.

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

        print(f"✓ Recorded {action}: {quantity} {ticker} @ ${price:.2f} = ${total_cost:,.2f} on {timestamp.strftime('%Y-%m-%d')}")

        return trade

    # ========================================
    # SNAPSHOTS (unchanged)
    # ========================================

    def take_snapshot(self, note: str = "manual snapshot"):
        """Take a snapshot of current portfolio state using DATABASE prices only (no API calls)."""
        print(f"\n📸 Taking portfolio snapshot...")

        # Use database prices ONLY - no API calls
        prices = self.get_prices_from_db()
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
        """Calculate portfolio statistics using DATABASE prices only (no API calls)."""
        # Use database prices ONLY - no API calls
        prices = self.get_prices_from_db()
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

    def get_portfolio_timeline_with_benchmark(self, days: int = 90, benchmark_ticker: str = 'SPY') -> Dict:
        """Get portfolio timeline with S&P 500 (SPY) comparison data.

        Returns:
            Dictionary containing:
            - dates: ISO format timestamps
            - values: Portfolio absolute values
            - portfolio_pct: Portfolio % change from start
            - benchmark_values: SPY prices aligned to dates
            - benchmark_pct: SPY % change from start
            - benchmark_ticker: The benchmark ticker used
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        # Get portfolio snapshots (same logic as get_portfolio_timeline)
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

        if not snapshots:
            return {
                'dates': [],
                'values': [],
                'portfolio_pct': [],
                'benchmark_values': [],
                'benchmark_pct': [],
                'benchmark_ticker': benchmark_ticker
            }

        dates = [s.timestamp.isoformat() for s in snapshots]
        values = [float(s.value) for s in snapshots]

        # Calculate portfolio % change from start
        initial_value = values[0] if values else 0
        portfolio_pct = []
        for v in values:
            if initial_value > 0:
                pct = ((v / initial_value) - 1) * 100
            else:
                pct = 0
            portfolio_pct.append(round(pct, 2))

        # Get SPY benchmark prices for the date range
        spy_prices = Price.query.filter(
            Price.ticker == benchmark_ticker,
            Price.timestamp >= cutoff_date
        ).order_by(Price.timestamp).all()

        # Create date -> price lookup (use date part only for matching)
        spy_price_map = {p.timestamp.date(): float(p.close) for p in spy_prices}

        benchmark_values = []
        benchmark_pct = []
        spy_initial = None

        # Align SPY prices to portfolio snapshot dates
        for s in snapshots:
            snapshot_date = s.timestamp.date()

            # Find SPY price for this date or closest previous date
            spy_price = spy_price_map.get(snapshot_date)
            if spy_price is None:
                # Look for closest previous date
                for spy_date in sorted(spy_price_map.keys(), reverse=True):
                    if spy_date <= snapshot_date:
                        spy_price = spy_price_map[spy_date]
                        break

            benchmark_values.append(spy_price)

            # Calculate SPY percentage change
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