# scheduler.py
"""
Background job scheduler using APScheduler.
Handles periodic price updates and portfolio snapshots.
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
import atexit


def backfill_job(app):
    """Background job to backfill price data"""
    with app.app_context():
        print(f"\n[{datetime.now()}] Running scheduled price backfill...")
        try:
            app.portfolio_manager.backfill_prices(days=7)  # Only fetch last 7 days
            print(f"[{datetime.now()}] Price backfill complete")
        except Exception as e:
            print(f"[{datetime.now()}] Error in backfill job: {e}")


def snapshot_job(app):
    """Background job to take portfolio snapshots"""
    with app.app_context():
        print(f"\n[{datetime.now()}] Taking scheduled portfolio snapshot...")
        try:
            app.portfolio_manager.take_snapshot(note="scheduled")
            print(f"[{datetime.now()}] Snapshot complete")
        except Exception as e:
            print(f"[{datetime.now()}] Error in snapshot job: {e}")


def start_scheduler(app):
    """Initialize and start the background scheduler"""

    scheduler = BackgroundScheduler(daemon=True)

    # Schedule price backfill every 6 hours
    scheduler.add_job(
        func=lambda: backfill_job(app),
        trigger=IntervalTrigger(hours=app.config['BACKFILL_INTERVAL_HOURS']),
        id='backfill_prices',
        name='Backfill stock prices from yfinance',
        replace_existing=True
    )

    # Schedule portfolio snapshots every hour
    scheduler.add_job(
        func=lambda: snapshot_job(app),
        trigger=IntervalTrigger(hours=app.config['SNAPSHOT_INTERVAL_HOURS']),
        id='portfolio_snapshot',
        name='Take portfolio snapshot',
        replace_existing=True
    )

    scheduler.start()

    print("\n" + "=" * 60)
    print("✓ SCHEDULER STARTED")
    print("=" * 60)
    print(f"Backfill job: Every {app.config['BACKFILL_INTERVAL_HOURS']} hours")
    print(f"Snapshot job: Every {app.config['SNAPSHOT_INTERVAL_HOURS']} hour(s)")
    print("=" * 60 + "\n")

    # Shut down scheduler when exiting the app
    atexit.register(lambda: scheduler.shutdown())

    return scheduler