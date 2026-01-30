# portfolio_manager.py

import bisect
import logging
import numpy as np
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from sqlalchemy import func, desc
from flask import g
from models import db, Price, Trade, Snapshot, PortfolioConfig
from providers import create_provider

logger = logging.getLogger(__name__)


class PortfolioManager:
    def __init__(self, app=None):
        self.app = app
        self._last_backfill_ts = None
        self._cooldown_seconds = 60
        self.provider = None
        if app:
            self.init_app(app)

    def init_app(self, app):
        self.app = app
        self.default_stocks = app.config.get('DEFAULT_PORTFOLIO_STOCKS', [])
        self.initial_cash = app.config['INITIAL_CASH']
        self._cooldown_seconds = app.config.get('MANUAL_REFRESH_COOLDOWN', 60)
        self.provider = create_provider(app.config)

    # Validation
    def _validate_tickers(self, tickers: List[str]) -> List[str]:
        return self.provider._validate_tickers(tickers)

    def _validate_trade(self, ticker: str, action: str, quantity: int, price: float):
        if action not in {'BUY', 'SELL'}:
            raise ValueError(f"[{ticker}] invalid action: {action}")
        if not isinstance(quantity, int) or quantity <= 0:
            raise ValueError(f"[{ticker}] quantity must be positive integer")
        self.provider._assert_price(price, ticker, "trade")

    def _sanitize_note(self, s: str) -> str:
        s = s or ""
        return "'" + s if s[:1] in ("=", "+", "-", "@") else s

    def get_tracked_stocks(self) -> List[str]:
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
        with self.app.app_context():
            if not PortfolioConfig.get_value('initial_cash'):
                PortfolioConfig.set_value('initial_cash', self.initial_cash)
                PortfolioConfig.set_value('start_date', datetime.now(timezone.utc).isoformat())
                logger.info(f"Initialized portfolio with ${self.initial_cash:,.2f}")

    # Price fetching
    def get_prices_from_db(self) -> Dict[str, float]:
        return self._get_prices_from_db()

    def fetch_live_prices(self) -> Dict[str, float]:
        stocks = self.get_tracked_stocks()
        logger.info(f"Fetching live prices for {len(stocks)} stocks...")
        try:
            prices = self.provider.get_current_prices(stocks)
            failed = [ticker for ticker, price in prices.items() if price is None]
            if failed:
                logger.warning(f"Some tickers failed: {failed}, filling from database...")
                prices = self._get_prices_from_db(prices)
            return prices
        except Exception as e:
            logger.error(f"Provider error: {e}")
            logger.info("Falling back to database cache...")
            return self._get_prices_from_db()

    def _get_prices_from_db(self, partial_prices: Dict[str, float] = None) -> Dict[str, float]:
        prices = partial_prices if partial_prices else {}
        stocks = self.get_tracked_stocks()
        stocks_needed = [s for s in stocks if prices.get(s) is None]

        if stocks_needed:
            subquery = db.session.query(
                Price.ticker,
                func.max(Price.timestamp).label('max_ts')
            ).filter(
                Price.ticker.in_(stocks_needed)
            ).group_by(Price.ticker).subquery()

            latest_prices = db.session.query(Price.ticker, Price.close).join(
                subquery,
                (Price.ticker == subquery.c.ticker) & (Price.timestamp == subquery.c.max_ts)
            ).all()

            for ticker, close in latest_prices:
                prices[ticker] = float(close)

            for stock in stocks_needed:
                if stock not in prices:
                    prices[stock] = 0.0
                    logger.warning(f"No price data available for {stock}")

        return prices

    def _get_fallback_price_from_db(self, ticker: str) -> float:
        latest_price = Price.query.filter_by(ticker=ticker).order_by(desc(Price.timestamp)).first()
        return float(latest_price.close) if latest_price else 0.0

    # Backfill
    def manual_backfill(self, default_lookback_days: int = 365) -> Tuple[bool, str]:
        now = datetime.now(timezone.utc)

        if self._last_backfill_ts:
            elapsed = (now - self._last_backfill_ts).total_seconds()
            if elapsed < self._cooldown_seconds:
                remaining = int(self._cooldown_seconds - elapsed)
                return False, f"Cooldown active. Please wait {remaining} seconds."

        logger.info("Starting manual backfill...")

        stocks = self.get_tracked_stocks()
        if not stocks:
            return True, "No stocks to backfill."

        if 'SPY' not in stocks:
            stocks = stocks + ['SPY']

        total_added = 0
        errors = []
        year_ago = now - timedelta(days=365)

        for stock in stocks:
            try:
                min_ts = db.session.query(func.min(Price.timestamp)).filter_by(ticker=stock).scalar()
                max_ts = db.session.query(func.max(Price.timestamp)).filter_by(ticker=stock).scalar()

                if min_ts and min_ts.tzinfo is None:
                    min_ts = min_ts.replace(tzinfo=timezone.utc)
                if max_ts and max_ts.tzinfo is None:
                    max_ts = max_ts.replace(tzinfo=timezone.utc)

                start_date = None
                end_date = now.date()
                fetch_needed = False

                if not min_ts or not max_ts:
                    logger.info(f"[{stock}] No data found. Scheduling full backfill.")
                    start_date = year_ago.date()
                    fetch_needed = True
                else:
                    if max_ts.date() < (now - timedelta(days=1)).date():
                        logger.info(f"[{stock}] Data stale (last: {max_ts.date()}). Updating...")
                        start_date = max_ts.date() + timedelta(days=1)
                        fetch_needed = True

                    if min_ts > (year_ago + timedelta(days=5)):
                        logger.info(f"[{stock}] Insufficient history. Extending back to {year_ago.date()}...")
                        start_date = year_ago.date()
                        fetch_needed = True

                if fetch_needed:
                    result = self.backfill_prices(start_date, end_date, "manual backfill", stock)
                    if result['success']:
                        total_added += result['counts'].get(stock, 0)
                    else:
                        errors.append(f"{stock}: {result.get('error')}")
                else:
                    logger.debug(f"[{stock}] Data is up to date")

            except Exception as e:
                logger.error(f"[{stock}] Error: {e}")
                errors.append(f"{stock}: {str(e)}")

        self._last_backfill_ts = now

        msg = f"Updated data. Added {total_added} records."
        if errors:
            msg += f" (Errors: {', '.join(errors[:3])})"
        return True, msg

    def _last_logged_day(self) -> Optional[datetime]:
        latest = db.session.query(func.max(Price.timestamp)).scalar()
        if latest:
            return latest.replace(hour=0, minute=0, second=0, microsecond=0)
        return None

    def backfill_prices(self, start_date, end_date, note: str = "backfill", ticker_specific: str = None) -> Dict:
        result = {'success': True, 'counts': {}, 'error': None}
        stocks = [ticker_specific] if ticker_specific else self.get_tracked_stocks()

        for stock in stocks:
            try:
                logger.info(f"[{stock}] Fetching historical data...")
                df = self.provider.get_historical_prices(stock, start_date, end_date)

                if df.empty:
                    logger.warning(f"[{stock}] No data returned")
                    result['counts'][stock] = 0
                    continue

                existing_ids = {row[0] for row in db.session.query(Price.event_id).filter(
                    Price.ticker == stock, Price.timestamp >= start_date
                ).all()}

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

                        if event_id in existing_ids:
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
                        logger.error(f"[{stock}] Error processing row: {e}")
                        continue

                db.session.commit()
                result['counts'][stock] = count
                logger.info(f"[{stock}] Added {count} new price records")

            except Exception as e:
                logger.error(f"[{stock}] Error during backfill: {e}")
                result['success'] = False
                result['error'] = str(e)
                result['counts'][stock] = 0
                db.session.rollback()

        logger.info("Backfill complete")
        return result

    # Trading
    def record_trade(self, ticker: str, action: str, quantity: int, price: float, note: str = "", timestamp: datetime = None):
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
        positions = self.get_current_positions()
        cash_before = self.get_cash_balance()
        position_before = positions.get(ticker, 0)

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

    # Snapshots
    def take_snapshot(self, note: str = "manual snapshot"):
        logger.info("Taking portfolio snapshot...")

        prices = self.get_prices_from_db()
        positions = self.get_current_positions()
        cash_balance = self.get_cash_balance()
        timestamp = datetime.now(timezone.utc)

        stocks = self.get_tracked_stocks()
        stock_value = sum(positions.get(stock, 0) * prices.get(stock, 0) for stock in stocks)
        portfolio_value = stock_value + cash_balance

        for stock in stocks:
            event_id = Snapshot.generate_event_id(timestamp, stock, positions[stock])

            if Snapshot.query.filter_by(event_id=event_id).first():
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
        logger.info(f"Snapshot saved: Portfolio value ${portfolio_value:,.2f}")
        return {'success': True, 'portfolio_value': portfolio_value}

    # Portfolio calculations
    def get_positions_and_cash(self) -> tuple:
        stocks = self.get_tracked_stocks()
        positions = {stock: 0 for stock in stocks}
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

    def get_current_positions(self) -> Dict[str, int]:
        positions, _ = self.get_positions_and_cash()
        return positions

    def get_cash_balance(self) -> float:
        _, cash = self.get_positions_and_cash()
        return cash

    def calculate_portfolio_stats(self) -> Dict:
        prices = self.get_prices_from_db()
        positions, cash = self.get_positions_and_cash()
        initial_value = float(PortfolioConfig.get_value('initial_cash', self.initial_cash))

        stock_values = {}
        total_stock_value = 0

        for stock in self.get_tracked_stocks():
            shares = positions[stock]
            price = prices.get(stock)

            if price is None:
                price = self._get_fallback_price_from_db(stock)
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
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        return db.session.query(
            Snapshot.timestamp,
            func.max(Snapshot.portfolio_value).label('value')
        ).filter(
            Snapshot.timestamp >= cutoff_date
        ).group_by(Snapshot.timestamp).order_by(Snapshot.timestamp).all()

    def get_portfolio_timeline(self, days: int = 90) -> Dict:
        snapshots = self._get_snapshots(days)
        return {
            'dates': [s.timestamp.isoformat() for s in snapshots],
            'values': [float(s.value) for s in snapshots]
        }

    def get_portfolio_timeline_with_benchmark(self, days: int = 90, benchmark_ticker: str = 'SPY') -> Dict:
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
        timeline = self.get_portfolio_timeline(days=365)

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
        stored_rate = PortfolioConfig.get_value('risk_free_rate')
        if stored_rate:
            try:
                return float(stored_rate)
            except (ValueError, TypeError):
                pass
        return 0.045

    def get_best_worst_stocks(self) -> Tuple[str, str]:
        best_stock = "N/A"
        worst_stock = "N/A"
        best_return = -float('inf')
        worst_return = float('inf')

        for stock in self.get_tracked_stocks():
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
