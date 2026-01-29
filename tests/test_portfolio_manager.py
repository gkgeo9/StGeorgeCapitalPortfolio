"""
Tests for PortfolioManager core business logic.
"""

import pytest
from datetime import datetime, timezone, timedelta
from models import db, Price, Trade, PortfolioConfig


class TestTradeValidation:
    """Test trade validation logic."""

    def test_buy_trade_success(self, app, init_database, sample_prices):
        """Test successful buy trade."""
        with app.app_context():
            pm = app.portfolio_manager

            trade = pm.record_trade(
                ticker='AAPL',
                action='BUY',
                quantity=10,
                price=150.0,
                note='Test buy'
            )

            assert trade.ticker == 'AAPL'
            assert trade.action == 'BUY'
            assert trade.quantity == 10
            assert float(trade.price) == 150.0
            assert float(trade.total_cost) == 1500.0
            assert trade.position_after == 10
            assert float(trade.cash_after) == 98500.0

    def test_sell_trade_success(self, app, init_database, sample_prices, sample_trade):
        """Test successful sell trade after buying."""
        with app.app_context():
            pm = app.portfolio_manager

            trade = pm.record_trade(
                ticker='AAPL',
                action='SELL',
                quantity=5,
                price=155.0,
                note='Test sell'
            )

            assert trade.action == 'SELL'
            assert trade.quantity == 5
            assert trade.position_before == 10
            assert trade.position_after == 5
            assert float(trade.cash_after) == 98500.0 + 775.0  # Sold 5 @ 155

    def test_sell_more_than_owned_fails(self, app, init_database, sample_prices, sample_trade):
        """Test that selling more shares than owned raises error."""
        with app.app_context():
            pm = app.portfolio_manager

            with pytest.raises(ValueError, match="position_after cannot be negative"):
                pm.record_trade(
                    ticker='AAPL',
                    action='SELL',
                    quantity=20,  # Only have 10
                    price=150.0
                )

    def test_buy_insufficient_cash_fails(self, app, init_database, sample_prices):
        """Test that buying with insufficient cash raises error."""
        with app.app_context():
            pm = app.portfolio_manager

            with pytest.raises(ValueError, match="cash_after cannot be negative"):
                pm.record_trade(
                    ticker='AAPL',
                    action='BUY',
                    quantity=1000,
                    price=150.0  # Would cost 150,000, only have 100,000
                )

    def test_invalid_action_fails(self, app, init_database):
        """Test that invalid action raises error."""
        with app.app_context():
            pm = app.portfolio_manager

            with pytest.raises(ValueError, match="invalid action"):
                pm.record_trade(
                    ticker='AAPL',
                    action='HOLD',
                    quantity=10,
                    price=150.0
                )

    def test_zero_quantity_fails(self, app, init_database):
        """Test that zero quantity raises error."""
        with app.app_context():
            pm = app.portfolio_manager

            with pytest.raises(ValueError, match="qty must be >0"):
                pm.record_trade(
                    ticker='AAPL',
                    action='BUY',
                    quantity=0,
                    price=150.0
                )

    def test_negative_price_fails(self, app, init_database):
        """Test that negative price raises error."""
        with app.app_context():
            pm = app.portfolio_manager

            with pytest.raises(ValueError):
                pm.record_trade(
                    ticker='AAPL',
                    action='BUY',
                    quantity=10,
                    price=-50.0
                )

    def test_backdated_sell_before_buy_fails(self, app, init_database, sample_prices, sample_trade):
        """Test that selling before first buy date raises error."""
        with app.app_context():
            pm = app.portfolio_manager

            # Sample trade is on 2024-01-01
            with pytest.raises(ValueError, match="Cannot sell before first purchase"):
                pm.record_trade(
                    ticker='AAPL',
                    action='SELL',
                    quantity=5,
                    price=145.0,
                    timestamp=datetime(2023, 12, 31, tzinfo=timezone.utc)
                )


class TestPositionCalculations:
    """Test position and cash balance calculations."""

    def test_initial_positions_empty(self, app, init_database):
        """Test that initial positions are empty."""
        with app.app_context():
            pm = app.portfolio_manager
            positions = pm.get_current_positions()

            # Should be empty dict or all zeros
            assert all(v == 0 for v in positions.values())

    def test_initial_cash_balance(self, app, init_database):
        """Test that initial cash balance is correct."""
        with app.app_context():
            pm = app.portfolio_manager
            cash = pm.get_cash_balance()

            assert cash == 100000.0

    def test_positions_after_buy(self, app, init_database, sample_prices, sample_trade):
        """Test positions after a buy trade."""
        with app.app_context():
            pm = app.portfolio_manager
            positions = pm.get_current_positions()

            assert positions.get('AAPL', 0) == 10

    def test_cash_after_buy(self, app, init_database, sample_prices, sample_trade):
        """Test cash balance after a buy trade."""
        with app.app_context():
            pm = app.portfolio_manager
            cash = pm.get_cash_balance()

            assert cash == 98500.0  # 100000 - 1500

    def test_positions_after_multiple_trades(self, app, init_database, sample_prices):
        """Test positions after multiple trades."""
        with app.app_context():
            pm = app.portfolio_manager

            # Buy 10 AAPL
            pm.record_trade('AAPL', 'BUY', 10, 150.0)
            # Buy 5 more AAPL
            pm.record_trade('AAPL', 'BUY', 5, 152.0)
            # Sell 3 AAPL
            pm.record_trade('AAPL', 'SELL', 3, 155.0)

            positions = pm.get_current_positions()
            assert positions.get('AAPL', 0) == 12  # 10 + 5 - 3


class TestPriceManagement:
    """Test price fetching and management."""

    def test_get_prices_from_db(self, app, init_database, sample_prices):
        """Test getting prices from database."""
        with app.app_context():
            pm = app.portfolio_manager
            prices = pm.get_prices_from_db()

            assert 'AAPL' in prices
            assert prices['AAPL'] == 152.0  # Most recent price

    def test_get_prices_missing_stock(self, app, init_database):
        """Test that missing stock returns 0 price with warning."""
        with app.app_context():
            pm = app.portfolio_manager

            # Add a trade for a stock with no price data
            Trade.query.delete()  # Clear any existing
            trade = Trade(
                event_id='test123',
                timestamp=datetime.now(timezone.utc),
                ticker='FAKE',
                action='BUY',
                quantity=1,
                price=100.0,
                total_cost=100.0,
                position_before=0,
                position_after=1,
                cash_before=100000.0,
                cash_after=99900.0
            )
            db.session.add(trade)
            db.session.commit()

            prices = pm.get_prices_from_db()
            assert prices.get('FAKE', 0) == 0.0


class TestPortfolioStats:
    """Test portfolio statistics calculations."""

    def test_calculate_portfolio_stats(self, app, init_database, sample_prices, sample_trade):
        """Test portfolio statistics calculation."""
        with app.app_context():
            pm = app.portfolio_manager
            stats = pm.calculate_portfolio_stats()

            assert 'total_portfolio_value' in stats
            assert 'cash' in stats
            assert 'total_stock_value' in stats
            assert 'total_pnl' in stats

            # 10 shares @ $152 + $98500 cash
            expected_value = 10 * 152.0 + 98500.0
            assert stats['total_portfolio_value'] == expected_value

    def test_portfolio_weights(self, app, init_database, sample_prices, sample_trade):
        """Test portfolio weight calculations."""
        with app.app_context():
            pm = app.portfolio_manager
            stats = pm.calculate_portfolio_stats()

            stock_values = stats['stock_values']
            if 'AAPL' in stock_values and stock_values['AAPL']['shares'] > 0:
                assert stock_values['AAPL']['weight'] > 0


class TestEventIdDeduplication:
    """Test event ID generation and deduplication."""

    def test_price_event_id_unique(self, app, init_database):
        """Test that same price data generates same event ID."""
        with app.app_context():
            ts = datetime(2024, 1, 1, tzinfo=timezone.utc)

            id1 = Price.generate_event_id('AAPL', ts, 150.0)
            id2 = Price.generate_event_id('AAPL', ts, 150.0)
            id3 = Price.generate_event_id('AAPL', ts, 151.0)  # Different price

            assert id1 == id2
            assert id1 != id3

    def test_trade_event_id_unique(self, app, init_database):
        """Test that same trade data generates same event ID."""
        with app.app_context():
            ts = datetime(2024, 1, 1, tzinfo=timezone.utc)

            id1 = Trade.generate_event_id(ts, 'AAPL', 'BUY', 10, 150.0)
            id2 = Trade.generate_event_id(ts, 'AAPL', 'BUY', 10, 150.0)
            id3 = Trade.generate_event_id(ts, 'AAPL', 'SELL', 10, 150.0)  # Different action

            assert id1 == id2
            assert id1 != id3

    def test_duplicate_price_not_inserted(self, app, init_database):
        """Test that duplicate prices are not inserted."""
        with app.app_context():
            ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
            event_id = Price.generate_event_id('TEST', ts, 100.0)

            price1 = Price(
                event_id=event_id,
                ticker='TEST',
                timestamp=ts,
                close=100.0,
                kind='HISTORY',
                price_source='test'
            )
            db.session.add(price1)
            db.session.commit()

            # Try to add duplicate
            price2 = Price(
                event_id=event_id,
                ticker='TEST',
                timestamp=ts,
                close=100.0,
                kind='HISTORY',
                price_source='test'
            )

            with pytest.raises(Exception):  # IntegrityError
                db.session.add(price2)
                db.session.commit()


class TestNoteSanitization:
    """Test CSV injection prevention in notes."""

    def test_sanitize_note_equals(self, app, init_database):
        """Test that notes starting with = are sanitized."""
        with app.app_context():
            pm = app.portfolio_manager

            result = pm._sanitize_note("=SUM(A1:A10)")
            assert result.startswith("'")

    def test_sanitize_note_plus(self, app, init_database):
        """Test that notes starting with + are sanitized."""
        with app.app_context():
            pm = app.portfolio_manager

            result = pm._sanitize_note("+1-555-1234")
            assert result.startswith("'")

    def test_sanitize_note_at(self, app, init_database):
        """Test that notes starting with @ are sanitized."""
        with app.app_context():
            pm = app.portfolio_manager

            result = pm._sanitize_note("@mention")
            assert result.startswith("'")

    def test_sanitize_note_normal(self, app, init_database):
        """Test that normal notes are not modified."""
        with app.app_context():
            pm = app.portfolio_manager

            result = pm._sanitize_note("Normal trade note")
            assert result == "Normal trade note"


class TestRiskFreeRate:
    """Test risk-free rate retrieval."""

    def test_default_risk_free_rate(self, app, init_database):
        """Test default risk-free rate when not set."""
        with app.app_context():
            pm = app.portfolio_manager
            rate = pm.get_risk_free_rate()

            assert rate == 0.045  # 4.5% default

    def test_stored_risk_free_rate(self, app, init_database):
        """Test stored risk-free rate from FRED."""
        with app.app_context():
            pm = app.portfolio_manager

            # Set a custom rate
            PortfolioConfig.set_value('risk_free_rate', '0.052')

            rate = pm.get_risk_free_rate()
            assert rate == 0.052
