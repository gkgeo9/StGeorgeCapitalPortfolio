# scheduler.py
"""
Background job scheduler - DISABLED automatic updates.
All updates now happen via manual button triggers.
Keeping scheduler infrastructure for future use if needed.
"""

from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import atexit


def start_scheduler(app):
    """
    Initialize scheduler but don't add any automatic jobs.
    All updates are now manual via API endpoints.
    """

    scheduler = BackgroundScheduler(daemon=True)

    # No automatic jobs added - all updates are manual now

    scheduler.start()

    print("\n" + "=" * 60)
    print("✓ SCHEDULER STARTED (Manual Mode)")
    print("=" * 60)
    print("All portfolio updates are now triggered manually via UI buttons")
    print("No automatic background jobs running")
    print("=" * 60 + "\n")

    # Shut down scheduler when exiting the app
    atexit.register(lambda: scheduler.shutdown())

    return scheduler