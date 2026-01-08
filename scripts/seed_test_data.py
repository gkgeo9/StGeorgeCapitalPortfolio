#!/usr/bin/env python3
"""
Auto-seed script for creating realistic test trades.
Uses actual historical prices from the last 3 months.

Usage:
    python scripts/seed_test_data.py

This script will:
1. Backfill price history for the last 90 days
2. Create sample BUY trades at historical prices
3. Take a portfolio snapshot
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta, timezone
from app import create_app
from models import db, Trade, Price, PortfolioConfig
from sqlalchemy import desc


# Configuration for seed trades
# Designed to use ~$93,000 of $100,000 initial cash, leaving buffer
SEED_CONFIG = {
    'NVDA': {'shares': 50, 'buy_days_ago': 75},    # ~2.5 months ago
    'MSFT': {'shares': 80, 'buy_days_ago': 60},    # ~2 months ago
    'AAPL': {'shares': 120, 'buy_days_ago': 45},   # ~1.5 months ago
    'JPM': {'shares': 60, 'buy_days_ago': 30},     # ~1 month ago
    'UNH': {'shares': 20, 'buy_days_ago': 15},     # ~2 weeks ago
}


def get_historical_price(ticker: str, days_ago: int) -> tuple:
    """
    Get price from approximately N days ago from the database.
    Returns (price, timestamp) or (None, None) if not found.
    """
    target_date = datetime.now(timezone.utc) - timedelta(days=days_ago)

    # Query database for closest price on or before target date
    price_record = Price.query.filter(
        Price.ticker == ticker,
        Price.timestamp <= target_date
    ).order_by(desc(Price.timestamp)).first()

    if price_record:
        return float(price_record.close), price_record.timestamp

    # If no historical price, try getting the most recent price
    latest = Price.query.filter_by(ticker=ticker).order_by(desc(Price.timestamp)).first()
    if latest:
        return float(latest.close), latest.timestamp

    return None, None


def seed_trades():
    """Create realistic sample trades using historical prices."""
    app = create_app()

    with app.app_context():
        pm = app.portfolio_manager

        # Check if trades already exist
        existing_trades = Trade.query.count()
        if existing_trades > 0:
            print(f"\nWARNING: {existing_trades} trades already exist in database.")
            response = input("Do you want to continue and add more trades? (y/N): ")
            if response.lower() != 'y':
                print("Aborted.")
                return

        # Step 1: Backfill price history
        print("\n" + "=" * 60)
        print("STEP 1: Backfilling price history (last 90 days)")
        print("=" * 60)

        start_date = datetime.now().date() - timedelta(days=90)
        end_date = datetime.now().date()

        result = pm.backfill_prices(
            start_date=start_date,
            end_date=end_date,
            note="seed script backfill"
        )

        if not result['success']:
            print(f"\nERROR: Backfill failed - {result.get('error', 'Unknown error')}")
            print("Cannot proceed without price data.")
            return

        total_prices = sum(result['counts'].values())
        print(f"\nBackfill complete: {total_prices} price records added")

        # Step 2: Create trades
        print("\n" + "=" * 60)
        print("STEP 2: Creating sample trades")
        print("=" * 60)

        trades_created = []
        total_invested = 0

        for ticker, config in SEED_CONFIG.items():
            print(f"\n[{ticker}] Looking for price from {config['buy_days_ago']} days ago...")

            price, trade_date = get_historical_price(ticker, config['buy_days_ago'])

            if price is None:
                print(f"  SKIP: No price data available for {ticker}")
                continue

            # Check if we have enough cash
            cash_available = pm.get_cash_balance()
            trade_cost = config['shares'] * price

            if cash_available < trade_cost:
                print(f"  SKIP: Insufficient cash (have ${cash_available:,.2f}, need ${trade_cost:,.2f})")
                continue

            try:
                trade = pm.record_trade(
                    ticker=ticker,
                    action='BUY',
                    quantity=config['shares'],
                    price=price,
                    note=f"Initial investment - seeded on {datetime.now().strftime('%Y-%m-%d')}"
                )

                trades_created.append({
                    'ticker': ticker,
                    'shares': config['shares'],
                    'price': price,
                    'cost': trade_cost,
                    'date': trade_date
                })
                total_invested += trade_cost

                print(f"  BUY {config['shares']} shares @ ${price:.2f} = ${trade_cost:,.2f}")

            except Exception as e:
                print(f"  ERROR: Failed to create trade - {e}")

        # Step 3: Take snapshot
        print("\n" + "=" * 60)
        print("STEP 3: Taking portfolio snapshot")
        print("=" * 60)

        snapshot = pm.take_snapshot(note="Post-seed snapshot")

        # Summary
        print("\n" + "=" * 60)
        print("SEED COMPLETE - SUMMARY")
        print("=" * 60)

        print(f"\nTrades created: {len(trades_created)}")
        print("-" * 40)
        for t in trades_created:
            print(f"  {t['ticker']}: {t['shares']} shares @ ${t['price']:.2f} = ${t['cost']:,.2f}")

        print(f"\n{'Total invested:':<20} ${total_invested:,.2f}")
        print(f"{'Cash remaining:':<20} ${pm.get_cash_balance():,.2f}")
        print(f"{'Portfolio value:':<20} ${snapshot['portfolio_value']:,.2f}")

        print("\nDone! Start the app with 'python app.py' to see your portfolio.")


def clear_all_data():
    """Clear all trades, snapshots, and prices from the database."""
    app = create_app()

    with app.app_context():
        print("\nWARNING: This will delete ALL data from the database!")
        print("  - All trades")
        print("  - All snapshots")
        print("  - All price history")

        response = input("\nAre you sure you want to continue? (type 'DELETE' to confirm): ")
        if response != 'DELETE':
            print("Aborted.")
            return

        Trade.query.delete()
        from models import Snapshot
        Snapshot.query.delete()
        Price.query.delete()
        db.session.commit()

        print("\nAll data cleared successfully.")


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--clear':
        clear_all_data()
    else:
        seed_trades()
