#!/usr/bin/env python3
"""
Cron job script for scheduled data refresh.
Run every 15 minutes via Railway cron: */15 * * * *

Behavior:
  - First run of the day (around DAILY_BACKFILL_HOUR UTC): Full backfill + snapshot
  - All other runs: Quick price update only
  - Weekly (Monday): Update risk-free rate from FRED API

Configuration:
  DAILY_BACKFILL_HOUR: Hour (UTC) to run full backfill (default: 9 = 9 AM UTC)
  FRED_API_KEY: Optional API key for FRED (free at https://fred.stlouisfed.org/docs/api/api_key.html)
"""

import os
import sys
import requests
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

from app import create_app
from models import db, Trade, Price, PortfolioConfig

# Configuration
DAILY_BACKFILL_HOUR = int(os.environ.get('DAILY_BACKFILL_HOUR', 9))  # 9 AM UTC default
FRED_API_KEY = os.environ.get('FRED_API_KEY')  # Optional - FRED API key


def should_run_full_backfill():
    """Check if we should run full backfill (first run of the day around configured hour)."""
    now = datetime.now(timezone.utc)
    # Run full backfill if we're within 15 minutes of the configured hour
    return now.hour == DAILY_BACKFILL_HOUR and now.minute < 15


def should_update_risk_free_rate():
    """Check if we should update risk-free rate (weekly on Monday around backfill hour)."""
    now = datetime.now(timezone.utc)
    # Monday = 0, run at same time as daily backfill
    return now.weekday() == 0 and now.hour == DAILY_BACKFILL_HOUR and now.minute < 15


def fetch_risk_free_rate_from_fred():
    """
    Fetch the 3-Month Treasury Bill rate from FRED API.
    Series: DTB3 (3-Month Treasury Bill: Secondary Market Rate)
    Returns annual rate as decimal (e.g., 0.045 for 4.5%)
    """
    if not FRED_API_KEY:
        print("  No FRED_API_KEY set, skipping risk-free rate update")
        return None

    try:
        # DTB3 = 3-Month Treasury Bill rate (most common risk-free proxy)
        url = "https://api.stlouisfed.org/fred/series/observations"
        params = {
            'series_id': 'DTB3',
            'api_key': FRED_API_KEY,
            'file_type': 'json',
            'sort_order': 'desc',
            'limit': 5  # Get last few in case of missing data
        }

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Find the most recent non-missing value
        for obs in data.get('observations', []):
            value = obs.get('value', '.')
            if value != '.':  # FRED uses '.' for missing data
                rate_percent = float(value)
                rate_decimal = rate_percent / 100  # Convert 4.5 -> 0.045
                return rate_decimal

        print("  No valid rate found in FRED response")
        return None

    except requests.RequestException as e:
        print(f"  FRED API error: {e}")
        return None
    except (ValueError, KeyError) as e:
        print(f"  Error parsing FRED response: {e}")
        return None


def update_risk_free_rate(app):
    """Update the stored risk-free rate from FRED API."""
    print("\n--- Weekly Risk-Free Rate Update ---")

    rate = fetch_risk_free_rate_from_fred()

    if rate is not None:
        with app.app_context():
            PortfolioConfig.set_value('risk_free_rate', str(rate))
            print(f"  Updated risk-free rate: {rate * 100:.2f}% (annual)")
    else:
        print("  Could not fetch rate, keeping existing value")


def run_quick_update(app):
    """Quick update - just fetch current prices and update today's record."""
    print("\n--- Quick Price Update ---")

    with app.app_context():
        pm = app.portfolio_manager
        stocks = pm.get_tracked_stocks()

        if not stocks:
            print("No stocks to update.")
            return

        # Include SPY benchmark
        if 'SPY' not in stocks:
            stocks = stocks + ['SPY']

        print(f"Fetching current prices for {len(stocks)} stocks...")

        # Get current prices from API
        prices = pm.provider.get_current_prices(stocks)

        # Update/insert today's price for each stock
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        updated = 0

        for ticker, price in prices.items():
            if price is None:
                continue

            # Check if we have a price record for today
            existing = Price.query.filter(
                Price.ticker == ticker,
                Price.timestamp >= today
            ).first()

            if existing:
                # Update existing record
                existing.close = price
                existing.note = "intraday update"
                print(f"  Updated {ticker}: ${price:.2f}")
            else:
                # Create new record for today
                event_id = Price.generate_event_id(
                    ticker=ticker,
                    timestamp=today,
                    close=price,
                    kind='INTRADAY',
                    note='intraday update'
                )
                new_price = Price(
                    event_id=event_id,
                    ticker=ticker,
                    timestamp=today,
                    close=price,
                    kind='INTRADAY',
                    price_source=pm.provider.get_provider_name(),
                    note='intraday update'
                )
                db.session.add(new_price)
                print(f"  Added {ticker}: ${price:.2f}")

            updated += 1

        db.session.commit()
        print(f"Updated {updated} prices.")


def run_full_backfill(app):
    """Full backfill - fetch historical data for new stocks, update stale data."""
    print("\n--- Full Daily Backfill ---")

    with app.app_context():
        pm = app.portfolio_manager

        trade_count = Trade.query.count()
        price_count = Price.query.count()
        stocks = pm.get_tracked_stocks()
        print(f"Database: {trade_count} trades, {price_count} prices")
        print(f"Tracked stocks: {stocks}")

        if not stocks:
            print("No stocks to update. Add trades first.")
            return False

        # Bypass cooldown for cron jobs
        pm._last_backfill_ts = None

        print("Starting smart backfill...")
        success, message = pm.manual_backfill(default_lookback_days=365)

        if success:
            print(f"Backfill completed: {message}")

            print("Taking snapshot...")
            snapshot_result = pm.take_snapshot(note="daily refresh")
            print(f"Snapshot: Portfolio value ${snapshot_result['portfolio_value']:.2f}")
            return True
        else:
            print(f"Backfill failed: {message}")
            return False


def main():
    now = datetime.now(timezone.utc)
    print(f"\n{'=' * 60}")
    print(f"CRON: Stock Data Refresh")
    print(f"Time: {now.isoformat()}")
    print(f"{'=' * 60}")

    app = create_app()

    # Weekly: Update risk-free rate from FRED (Monday only)
    if should_update_risk_free_rate():
        update_risk_free_rate(app)

    # Check if we should run full backfill
    if should_run_full_backfill():
        print(f"First run of the day (hour={DAILY_BACKFILL_HOUR} UTC) - running full backfill")
        success = run_full_backfill(app)
        if not success:
            sys.exit(1)
    else:
        print(f"Regular run - quick price update only")

    # Always run quick update to get latest prices
    run_quick_update(app)

    print(f"\n{'=' * 60}")
    print(f"CRON: Completed successfully")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
