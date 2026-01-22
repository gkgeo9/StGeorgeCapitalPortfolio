#!/usr/bin/env python3
"""
Cron job script for scheduled data refresh.
Run this on a schedule (e.g., daily) via Railway cron jobs.

Usage:
  python cron_refresh.py

Railway cron setup:
  1. Create a new service in Railway
  2. Set the start command to: python cron_refresh.py
  3. In Settings > Cron Schedule, set your schedule (e.g., "0 9 * * *" for 9 AM UTC daily)
  4. Share the same DATABASE_URL and ALPHA_VANTAGE_API_KEY environment variables
"""

import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

from app import create_app


def run_scheduled_refresh():
    """Run the data refresh job."""
    print(f"\n{'=' * 60}")
    print(f"CRON JOB: Scheduled Data Refresh")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")
    print(f"{'=' * 60}\n")

    app = create_app()

    with app.app_context():
        pm = app.portfolio_manager

        # Run backfill with 30 days lookback
        print("Starting backfill...")
        success, message = pm.manual_backfill(default_lookback_days=30)

        if success:
            print(f"Backfill completed: {message}")

            # Take a snapshot
            print("Taking snapshot...")
            snapshot_result = pm.take_snapshot(note="scheduled refresh")
            print(f"Snapshot taken. Portfolio value: ${snapshot_result['portfolio_value']:.2f}")
        else:
            print(f"Backfill failed: {message}")
            sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"CRON JOB: Completed successfully")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    run_scheduled_refresh()
