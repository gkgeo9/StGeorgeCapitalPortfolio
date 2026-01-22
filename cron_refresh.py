#!/usr/bin/env python3
"""
Cron job script for scheduled data refresh.
Run every 15 minutes via Railway cron: */15 * * * *

Behavior:
  - First run of the day (around DAILY_BACKFILL_HOUR UTC): Full backfill + snapshot
  - All other runs: Quick price update only

Configuration:
  DAILY_BACKFILL_HOUR: Hour (UTC) to run full backfill (default: 9 = 9 AM UTC)
"""

import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

from app import create_app
from models import db, Trade, Price

# Configuration
DAILY_BACKFILL_HOUR = int(os.environ.get('DAILY_BACKFILL_HOUR', 9))  # 9 AM UTC default


def should_run_full_backfill():
    """Check if we should run full backfill (first run of the day around configured hour)."""
    now = datetime.now(timezone.utc)
    # Run full backfill if we're within 15 minutes of the configured hour
    return now.hour == DAILY_BACKFILL_HOUR and now.minute < 15


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
