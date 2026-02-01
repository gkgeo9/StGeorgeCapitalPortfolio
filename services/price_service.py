# services/price_service.py
"""
Price fetching and historical data backfill service.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, desc

from models import db, Price, PortfolioConfig
from constants import DEFAULT_LOOKBACK_DAYS, DEFAULT_BENCHMARK_TICKER

logger = logging.getLogger(__name__)


class PriceService:
    """Handles price fetching, database queries, and historical data backfill."""

    def __init__(self, provider, cooldown_seconds: int = 60):
        self.provider = provider
        self._cooldown_seconds = cooldown_seconds

    def _check_cooldown(self) -> Tuple[bool, int]:
        """
        Check if cooldown period has passed using database-backed timestamp.
        Returns (can_proceed, remaining_seconds).
        """
        now = datetime.now(timezone.utc)
        last_refresh = PortfolioConfig.get_value('last_refresh_ts')

        if last_refresh:
            try:
                last_ts = datetime.fromisoformat(last_refresh)
                if last_ts.tzinfo is None:
                    last_ts = last_ts.replace(tzinfo=timezone.utc)
                elapsed = (now - last_ts).total_seconds()
                if elapsed < self._cooldown_seconds:
                    remaining = int(self._cooldown_seconds - elapsed)
                    return False, remaining
            except (ValueError, TypeError):
                pass

        return True, 0

    def _update_cooldown(self):
        """Update the cooldown timestamp in database."""
        PortfolioConfig.set_value('last_refresh_ts', datetime.now(timezone.utc).isoformat())

    def get_prices_from_db(self, tracked_stocks: List[str]) -> Dict[str, float]:
        """Get latest prices from database only - no API calls."""
        return self._get_prices_from_db(tracked_stocks)

    def fetch_live_prices(self, tracked_stocks: List[str]) -> Dict[str, float]:
        """
        Fetch live prices from Alpha Vantage API.
        Falls back to database cache if API fails.
        """
        logger.info(f"Fetching live prices for {len(tracked_stocks)} stocks...")
        try:
            prices = self.provider.get_current_prices(tracked_stocks)
            failed = [ticker for ticker, price in prices.items() if price is None]
            if failed:
                logger.warning(f"Some tickers failed: {failed}, filling from database...")
                prices = self._get_prices_from_db(tracked_stocks, prices)
            return prices
        except Exception as e:
            logger.error(f"Provider error: {e}")
            logger.info("Falling back to database cache...")
            return self._get_prices_from_db(tracked_stocks)

    def _get_prices_from_db(self, tracked_stocks: List[str], partial_prices: Dict[str, float] = None) -> Dict[str, float]:
        """Get latest prices from database using optimized single query."""
        prices = partial_prices if partial_prices else {}
        stocks_needed = [s for s in tracked_stocks if prices.get(s) is None]

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

    def get_fallback_price_from_db(self, ticker: str) -> float:
        """Get fallback price from database for a single ticker."""
        latest_price = Price.query.filter_by(ticker=ticker).order_by(desc(Price.timestamp)).first()
        return float(latest_price.close) if latest_price else 0.0

    def manual_backfill(self, tracked_stocks: List[str], default_lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> Tuple[bool, str]:
        """
        Manual backfill triggered by user.
        Ensures all tracked stocks have at least 1 year of historical data.
        Uses database-backed cooldown to prevent race conditions.
        """
        can_proceed, remaining = self._check_cooldown()
        if not can_proceed:
            return False, f"Cooldown active. Please wait {remaining} seconds."

        logger.info("Starting manual backfill...")

        stocks = list(tracked_stocks)
        if not stocks:
            return True, "No stocks to backfill."

        if DEFAULT_BENCHMARK_TICKER not in stocks:
            stocks = stocks + [DEFAULT_BENCHMARK_TICKER]

        now = datetime.now(timezone.utc)
        total_added = 0
        errors = []
        year_ago = now - timedelta(days=default_lookback_days)

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

        self._update_cooldown()

        msg = f"Updated data. Added {total_added} records."
        if errors:
            msg += f" (Errors: {', '.join(errors[:3])})"
        return True, msg

    def last_logged_day(self) -> Optional[datetime]:
        """Get the most recent datetime we have price data for."""
        latest = db.session.query(func.max(Price.timestamp)).scalar()
        if latest:
            return latest.replace(hour=0, minute=0, second=0, microsecond=0)
        return None

    def backfill_prices(self, start_date, end_date, note: str = "backfill", ticker_specific: str = None) -> Dict:
        """
        Backfill historical price data using configured provider.
        Returns dict with success status and counts per ticker.
        """
        result = {'success': True, 'counts': {}, 'error': None}
        stocks = [ticker_specific] if ticker_specific else []

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
