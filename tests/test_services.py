"""
Tests for service layer classes.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import os
os.environ['TESTING'] = 'true'
os.environ['SECRET_KEY'] = 'test-secret-key'

from app import create_app
from models import db, Price, Trade, Snapshot, PortfolioConfig


@pytest.fixture(scope='function')
def app():
    """Create application for testing."""
    application = create_app('testing')
    application.config['TESTING'] = True
    application.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    application.config['WTF_CSRF_ENABLED'] = False

    with application.app_context():
        db.create_all()
        PortfolioConfig.set_value('initial_cash', 100000)
        yield application
        db.drop_all()


class TestTradeService:
    """Test TradeService functionality."""

    def test_validate_trade_valid_buy(self, app):
        """Test validation passes for valid BUY trade."""
        from services.trade_service import TradeService

        mock_provider = MagicMock()
        mock_provider._assert_price = MagicMock()

        service = TradeService(100000, mock_provider)
        # Should not raise
        service._validate_trade('AAPL', 'BUY', 10, 150.0)
        mock_provider._assert_price.assert_called_once()

    def test_validate_trade_valid_sell(self, app):
        """Test validation passes for valid SELL trade."""
        from services.trade_service import TradeService

        mock_provider = MagicMock()
        mock_provider._assert_price = MagicMock()

        service = TradeService(100000, mock_provider)
        service._validate_trade('AAPL', 'SELL', 5, 155.0)
        mock_provider._assert_price.assert_called_once()

    def test_validate_trade_invalid_action(self, app):
        """Test validation fails for invalid action."""
        from services.trade_service import TradeService

        mock_provider = MagicMock()
        service = TradeService(100000, mock_provider)

        with pytest.raises(ValueError, match="invalid action"):
            service._validate_trade('AAPL', 'HOLD', 10, 150.0)

    def test_validate_trade_negative_quantity(self, app):
        """Test validation fails for negative quantity."""
        from services.trade_service import TradeService

        mock_provider = MagicMock()
        service = TradeService(100000, mock_provider)

        with pytest.raises(ValueError, match="positive integer"):
            service._validate_trade('AAPL', 'BUY', -10, 150.0)

    def test_validate_trade_zero_quantity(self, app):
        """Test validation fails for zero quantity."""
        from services.trade_service import TradeService

        mock_provider = MagicMock()
        service = TradeService(100000, mock_provider)

        with pytest.raises(ValueError, match="positive integer"):
            service._validate_trade('AAPL', 'BUY', 0, 150.0)

    def test_sanitize_note_csv_injection(self, app):
        """Test CSV injection prevention."""
        from services.trade_service import TradeService

        mock_provider = MagicMock()
        service = TradeService(100000, mock_provider)

        assert service._sanitize_note("=SUM(A1)") == "'=SUM(A1)"
        assert service._sanitize_note("+cmd") == "'+cmd"
        assert service._sanitize_note("-cmd") == "'-cmd"
        assert service._sanitize_note("@import") == "'@import"
        assert service._sanitize_note("Normal note") == "Normal note"
        assert service._sanitize_note(None) == ""

    def test_get_positions_empty(self, app):
        """Test get_positions_and_cash with no trades."""
        from services.trade_service import TradeService

        with app.app_context():
            mock_provider = MagicMock()
            service = TradeService(100000, mock_provider)

            positions, cash = service.get_positions_and_cash(['AAPL', 'GOOGL'])
            assert positions == {'AAPL': 0, 'GOOGL': 0}
            assert cash == 100000


class TestPriceService:
    """Test PriceService functionality."""

    def test_check_cooldown_no_previous(self, app):
        """Test cooldown check with no previous refresh."""
        from services.price_service import PriceService

        with app.app_context():
            mock_provider = MagicMock()
            service = PriceService(mock_provider, cooldown_seconds=60)

            can_proceed, remaining = service._check_cooldown()
            assert can_proceed is True
            assert remaining == 0

    def test_check_cooldown_within_cooldown(self, app):
        """Test cooldown check within cooldown period."""
        from services.price_service import PriceService

        with app.app_context():
            # Set recent refresh timestamp
            PortfolioConfig.set_value('last_refresh_ts', datetime.now(timezone.utc).isoformat())

            mock_provider = MagicMock()
            service = PriceService(mock_provider, cooldown_seconds=60)

            can_proceed, remaining = service._check_cooldown()
            assert can_proceed is False
            assert remaining > 0

    def test_check_cooldown_after_cooldown(self, app):
        """Test cooldown check after cooldown period expired."""
        from services.price_service import PriceService
        from datetime import timedelta

        with app.app_context():
            # Set old refresh timestamp (2 minutes ago)
            old_ts = datetime.now(timezone.utc) - timedelta(minutes=2)
            PortfolioConfig.set_value('last_refresh_ts', old_ts.isoformat())

            mock_provider = MagicMock()
            service = PriceService(mock_provider, cooldown_seconds=60)

            can_proceed, remaining = service._check_cooldown()
            assert can_proceed is True
            assert remaining == 0

    def test_get_fallback_price_from_db(self, app):
        """Test getting fallback price from database."""
        from services.price_service import PriceService

        with app.app_context():
            # Add a price record
            price = Price(
                event_id=Price.generate_event_id('AAPL', datetime(2024, 1, 1, tzinfo=timezone.utc), 150.0),
                ticker='AAPL',
                timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
                close=150.0,
                kind='HISTORY',
                price_source='test'
            )
            db.session.add(price)
            db.session.commit()

            mock_provider = MagicMock()
            service = PriceService(mock_provider)

            result = service.get_fallback_price_from_db('AAPL')
            assert result == 150.0

    def test_get_fallback_price_no_data(self, app):
        """Test fallback price returns 0 when no data."""
        from services.price_service import PriceService

        with app.app_context():
            mock_provider = MagicMock()
            service = PriceService(mock_provider)

            result = service.get_fallback_price_from_db('UNKNOWN')
            assert result == 0.0


class TestSnapshotService:
    """Test SnapshotService functionality."""

    def test_take_snapshot(self, app):
        """Test taking a portfolio snapshot."""
        from services.snapshot_service import SnapshotService

        with app.app_context():
            service = SnapshotService()

            prices = {'AAPL': 150.0, 'GOOGL': 140.0}
            positions = {'AAPL': 10, 'GOOGL': 5}
            cash_balance = 98500.0
            tracked_stocks = ['AAPL', 'GOOGL']

            result = service.take_snapshot(prices, positions, cash_balance, tracked_stocks, "test snapshot")

            assert result['success'] is True
            # 10 * 150 + 5 * 140 + 98500 = 1500 + 700 + 98500 = 100700
            assert result['portfolio_value'] == 100700.0

            # Verify snapshots were created
            snapshots = Snapshot.query.all()
            assert len(snapshots) == 2  # One for each stock


class TestAnalyticsService:
    """Test AnalyticsService functionality."""

    def test_calculate_portfolio_stats(self, app):
        """Test portfolio statistics calculation."""
        from services.analytics_service import AnalyticsService

        with app.app_context():
            service = AnalyticsService(100000)

            prices = {'AAPL': 150.0, 'GOOGL': 140.0}
            positions = {'AAPL': 10, 'GOOGL': 0}
            cash = 98500.0
            tracked_stocks = ['AAPL', 'GOOGL']

            def fallback_fn(ticker):
                return 0.0

            result = service.calculate_portfolio_stats(prices, positions, cash, tracked_stocks, fallback_fn)

            assert result['total_stock_value'] == 1500.0  # 10 * 150
            assert result['cash'] == 98500.0
            assert result['total_portfolio_value'] == 100000.0  # 1500 + 98500
            assert result['total_pnl'] == 0.0  # No change from initial
            assert result['pnl_percent'] == 0.0

    def test_get_risk_free_rate_default(self, app):
        """Test default risk-free rate."""
        from services.analytics_service import AnalyticsService
        from constants import DEFAULT_RISK_FREE_RATE

        with app.app_context():
            service = AnalyticsService(100000)
            rate = service.get_risk_free_rate()
            assert rate == DEFAULT_RISK_FREE_RATE

    def test_get_risk_free_rate_stored(self, app):
        """Test stored risk-free rate."""
        from services.analytics_service import AnalyticsService

        with app.app_context():
            PortfolioConfig.set_value('risk_free_rate', '0.05')

            service = AnalyticsService(100000)
            rate = service.get_risk_free_rate()
            assert rate == 0.05

    def test_get_best_worst_stocks_no_data(self, app):
        """Test best/worst stocks with no data."""
        from services.analytics_service import AnalyticsService

        with app.app_context():
            service = AnalyticsService(100000)
            best, worst = service.get_best_worst_stocks(['AAPL', 'GOOGL'])
            assert best == "N/A"
            assert worst == "N/A"

    def test_get_portfolio_timeline_empty(self, app):
        """Test portfolio timeline with no snapshots."""
        from services.analytics_service import AnalyticsService

        with app.app_context():
            service = AnalyticsService(100000)
            timeline = service.get_portfolio_timeline(days=90)
            assert timeline['dates'] == []
            assert timeline['values'] == []
