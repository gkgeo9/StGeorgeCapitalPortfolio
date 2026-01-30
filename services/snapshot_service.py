# services/snapshot_service.py
"""
Portfolio snapshot service.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List

from models import db, Snapshot

logger = logging.getLogger(__name__)


class SnapshotService:
    """Handles portfolio snapshot creation and retrieval."""

    def _sanitize_note(self, s: str) -> str:
        """Sanitize note to prevent CSV injection attacks."""
        s = s or ""
        return "'" + s if s[:1] in ("=", "+", "-", "@") else s

    def take_snapshot(self, prices: Dict[str, float], positions: Dict[str, int],
                      cash_balance: float, tracked_stocks: List[str],
                      note: str = "manual snapshot") -> Dict:
        """
        Take a snapshot of current portfolio state.

        Args:
            prices: Dict of ticker -> price
            positions: Dict of ticker -> shares
            cash_balance: Current cash balance
            tracked_stocks: List of tracked stock tickers
            note: Optional snapshot note

        Returns:
            Dict with success status and portfolio value
        """
        logger.info("Taking portfolio snapshot...")

        timestamp = datetime.now(timezone.utc)
        stock_value = sum(positions.get(stock, 0) * prices.get(stock, 0) for stock in tracked_stocks)
        portfolio_value = stock_value + cash_balance

        for stock in tracked_stocks:
            event_id = Snapshot.generate_event_id(timestamp, stock, positions.get(stock, 0))

            if Snapshot.query.filter_by(event_id=event_id).first():
                continue

            snapshot = Snapshot(
                event_id=event_id,
                timestamp=timestamp,
                ticker=stock,
                position=positions.get(stock, 0),
                cash_balance=cash_balance,
                portfolio_value=portfolio_value,
                note=self._sanitize_note(note)
            )
            db.session.add(snapshot)

        db.session.commit()
        logger.info(f"Snapshot saved: Portfolio value ${portfolio_value:,.2f}")
        return {'success': True, 'portfolio_value': portfolio_value}
