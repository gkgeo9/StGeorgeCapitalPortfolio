#!/usr/bin/env python3
"""
Cron job for scheduled data refresh. Run every 15 minutes.

Schedule behavior:
- Weekends: Skip entirely
- 9 AM UTC: Full backfill + snapshot (pre-market)
- 9:30 AM - 4:00 PM ET (market hours): Intraday price updates
- 4:00-4:30 PM ET: Save daily close prices
- Outside market hours: Skip updates

Weekly Monday: Update risk-free rate from FRED
"""

import os
import sys
import logging
import requests
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv

load_dotenv()

# Use public DATABASE_URL for cron jobs if available
# (Railway internal network not accessible from cron containers)
if os.environ.get('DATABASE_PUBLIC_URL'):
    os.environ['DATABASE_URL'] = os.environ['DATABASE_PUBLIC_URL']

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from app import create_app
from models import db, Trade, Price, PortfolioConfig
from constants import DEFAULT_BENCHMARK_TICKER, DEFAULT_LOOKBACK_DAYS

# Configuration
DAILY_BACKFILL_HOUR = int(os.environ.get('DAILY_BACKFILL_HOUR', 9))
FRED_API_KEY = os.environ.get('FRED_API_KEY')

# Market hours in UTC (ET + 5, or ET + 4 during DST)
# Using conservative estimates that work year-round
MARKET_OPEN_UTC = 14   # 9:30 AM ET = 14:30 UTC (winter) / 13:30 UTC (summer)
MARKET_CLOSE_UTC = 21  # 4:00 PM ET = 21:00 UTC (winter) / 20:00 UTC (summer)


def is_weekend():
    """Check if today is a weekend (Sat=5, Sun=6)."""
    return datetime.now(timezone.utc).weekday() >= 5


def is_within_range(hour, minute, target_hour, buffer_minutes=20):
    """Check if current time is within buffer of target hour."""
    now_minutes = hour * 60 + minute
    target_minutes = target_hour * 60
    return abs(now_minutes - target_minutes) <= buffer_minutes


def should_run_full_backfill():
    """Check if we should run full backfill (around configured hour, with buffer)."""
    now = datetime.now(timezone.utc)
    return is_within_range(now.hour, now.minute, DAILY_BACKFILL_HOUR, buffer_minutes=20)


def should_update_risk_free_rate():
    """Check if we should update risk-free rate (Monday around backfill hour)."""
    now = datetime.now(timezone.utc)
    return now.weekday() == 0 and should_run_full_backfill()


def is_market_hours():
    """Check if we're within US market hours (with buffer for timing variations)."""
    now = datetime.now(timezone.utc)
    # Market hours: roughly 14:00-21:00 UTC (varies with DST)
    # Add 30 min buffer on each side
    return 13 <= now.hour <= 21


def should_save_daily_close():
    """Check if we should save daily close (shortly after market close)."""
    now = datetime.now(timezone.utc)
    # Save close between 21:00-21:30 UTC (4:00-4:30 PM ET winter)
    # or 20:00-20:30 UTC (4:00-4:30 PM ET summer)
    # Use wider window 20:00-21:30 to catch both DST scenarios
    return 20 <= now.hour <= 21 and (now.hour == 20 or now.minute <= 30)


def fetch_risk_free_rate_from_fred():
    """Fetch 3-Month Treasury Bill rate (DTB3) from FRED."""
    if not FRED_API_KEY:
        logger.info("No FRED_API_KEY set, skipping risk-free rate update")
        return None

    try:
        url = "https://api.stlouisfed.org/fred/series/observations"
        params = {
            'series_id': 'DTB3',
            'api_key': FRED_API_KEY,
            'file_type': 'json',
            'sort_order': 'desc',
            'limit': 5
        }

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        for obs in data.get('observations', []):
            value = obs.get('value', '.')
            if value != '.':
                rate_percent = float(value)
                return rate_percent / 100

        logger.warning("No valid rate found in FRED response")
        return None

    except requests.RequestException as e:
        logger.error(f"FRED API error: {e}")
        return None
    except (ValueError, KeyError) as e:
        logger.error(f"Error parsing FRED response: {e}")
        return None


def update_risk_free_rate(app):
    """Update the stored risk-free rate from FRED API."""
    logger.info("--- Weekly Risk-Free Rate Update ---")
    rate = fetch_risk_free_rate_from_fred()

    if rate is not None:
        with app.app_context():
            PortfolioConfig.set_value('risk_free_rate', str(rate))
            logger.info(f"Updated risk-free rate: {rate * 100:.2f}% (annual)")
    else:
        logger.warning("Could not fetch rate, keeping existing value")


def run_price_update(app, kind='INTRADAY', note='intraday update'):
    """Fetch current prices and save to database."""
    logger.info(f"--- Price Update ({kind}) ---")

    with app.app_context():
        pm = app.portfolio_manager
        stocks = pm.get_tracked_stocks()

        if not stocks:
            logger.info("No stocks to update.")
            return

        if DEFAULT_BENCHMARK_TICKER not in stocks:
            stocks = stocks + [DEFAULT_BENCHMARK_TICKER]

        logger.info(f"Fetching prices for {len(stocks)} stocks...")
        prices = pm.provider.get_current_prices(stocks)

        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        updated = 0

        for ticker, price in prices.items():
            if price is None:
                continue

            existing = Price.query.filter(
                Price.ticker == ticker,
                Price.timestamp >= today
            ).first()

            if existing:
                existing.close = price
                existing.kind = kind
                existing.note = note
                logger.info(f"Updated {ticker}: ${price:.2f} ({kind})")
            else:
                event_id = Price.generate_event_id(
                    ticker=ticker,
                    timestamp=today,
                    close=price,
                    kind=kind,
                    note=note
                )
                new_price = Price(
                    event_id=event_id,
                    ticker=ticker,
                    timestamp=today,
                    close=price,
                    kind=kind,
                    price_source=pm.provider.get_provider_name(),
                    note=note
                )
                db.session.add(new_price)
                logger.info(f"Added {ticker}: ${price:.2f} ({kind})")

            updated += 1

        db.session.commit()
        logger.info(f"Updated {updated} prices.")


def run_full_backfill(app):
    """Full backfill - fetch historical data for new stocks, update stale data."""
    logger.info("--- Full Daily Backfill ---")

    with app.app_context():
        pm = app.portfolio_manager

        trade_count = Trade.query.count()
        price_count = Price.query.count()
        stocks = pm.get_tracked_stocks()
        logger.info(f"Database: {trade_count} trades, {price_count} prices")
        logger.info(f"Tracked stocks: {stocks}")

        if not stocks:
            logger.warning("No stocks to update. Add trades first.")
            return False

        # Bypass cooldown for cron jobs by clearing last refresh timestamp
        PortfolioConfig.set_value('last_refresh_ts', None)

        logger.info("Starting smart backfill...")
        success, message = pm.manual_backfill(default_lookback_days=DEFAULT_LOOKBACK_DAYS)

        if success:
            logger.info(f"Backfill completed: {message}")
            logger.info("Taking snapshot...")
            snapshot_result = pm.take_snapshot(note="daily refresh")
            logger.info(f"Snapshot: Portfolio value ${snapshot_result['portfolio_value']:.2f}")
            return True
        else:
            logger.error(f"Backfill failed: {message}")
            return False


def check_market_status_api(app):
    """Check market status via provider API."""
    try:
        with app.app_context():
            return app.portfolio_manager.provider.is_market_open()
    except Exception as e:
        logger.warning(f"Could not check market status: {e}")
        return None


def main():
    now = datetime.now(timezone.utc)
    logger.info("=" * 60)
    logger.info("CRON: Stock Data Refresh")
    logger.info(f"Time: {now.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    logger.info(f"Day: {now.strftime('%A')}")
    logger.info("=" * 60)

    # Skip weekends entirely
    if is_weekend():
        logger.info("Weekend - skipping all updates")
        return

    app = create_app()

    # Weekly Monday: Update risk-free rate from FRED
    if should_update_risk_free_rate():
        update_risk_free_rate(app)

    # Morning: Full backfill (runs before market opens)
    if should_run_full_backfill():
        logger.info(f"Morning backfill window (hour ~{DAILY_BACKFILL_HOUR} UTC)")
        success = run_full_backfill(app)
        if not success:
            sys.exit(1)
        logger.info("=" * 60)
        logger.info("CRON: Completed successfully")
        logger.info("=" * 60)
        return

    # Check actual market status from API
    market_open = check_market_status_api(app)
    logger.info(f"Market status: {'OPEN' if market_open else 'CLOSED'}")

    # After market close: Save daily close prices
    if should_save_daily_close():
        logger.info("Market close window - saving daily close prices")
        run_price_update(app, kind='DAILY', note='daily close')
        logger.info("=" * 60)
        logger.info("CRON: Completed successfully")
        logger.info("=" * 60)
        return

    # During market hours: Intraday updates
    if market_open or is_market_hours():
        logger.info("Market hours - updating intraday prices")
        run_price_update(app, kind='INTRADAY', note='intraday update')
    else:
        logger.info("Outside market hours - skipping price update")

    logger.info("=" * 60)
    logger.info("CRON: Completed successfully")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
