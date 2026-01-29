"""
Pytest fixtures for St. George Capital Portfolio tests.
"""

import os
import pytest
from datetime import datetime, timezone

# Set testing environment before importing app
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
        yield application
        db.drop_all()


@pytest.fixture(scope='function')
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture(scope='function')
def runner(app):
    """Create CLI test runner."""
    return app.test_cli_runner()


@pytest.fixture(scope='function')
def init_database(app):
    """Initialize database with test data."""
    with app.app_context():
        # Set initial cash
        PortfolioConfig.set_value('initial_cash', 100000)
        PortfolioConfig.set_value('start_date', datetime.now(timezone.utc).isoformat())

        yield db

        db.session.rollback()


@pytest.fixture(scope='function')
def sample_prices(app, init_database):
    """Add sample price data to database."""
    with app.app_context():
        prices = [
            Price(
                event_id=Price.generate_event_id('AAPL', datetime(2024, 1, 1, tzinfo=timezone.utc), 150.0),
                ticker='AAPL',
                timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
                close=150.0,
                open=149.0,
                high=151.0,
                low=148.0,
                volume=1000000,
                kind='HISTORY',
                price_source='test'
            ),
            Price(
                event_id=Price.generate_event_id('AAPL', datetime(2024, 1, 2, tzinfo=timezone.utc), 152.0),
                ticker='AAPL',
                timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
                close=152.0,
                open=150.0,
                high=153.0,
                low=149.5,
                volume=1100000,
                kind='HISTORY',
                price_source='test'
            ),
            Price(
                event_id=Price.generate_event_id('GOOGL', datetime(2024, 1, 1, tzinfo=timezone.utc), 140.0),
                ticker='GOOGL',
                timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
                close=140.0,
                open=139.0,
                high=141.0,
                low=138.0,
                volume=500000,
                kind='HISTORY',
                price_source='test'
            ),
            Price(
                event_id=Price.generate_event_id('SPY', datetime(2024, 1, 1, tzinfo=timezone.utc), 450.0),
                ticker='SPY',
                timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
                close=450.0,
                open=448.0,
                high=452.0,
                low=447.0,
                volume=10000000,
                kind='HISTORY',
                price_source='test'
            ),
        ]

        for price in prices:
            db.session.add(price)
        db.session.commit()

        yield prices


@pytest.fixture(scope='function')
def sample_trade(app, init_database, sample_prices):
    """Add a sample trade to database."""
    with app.app_context():
        trade = Trade(
            event_id=Trade.generate_event_id(
                datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                'AAPL', 'BUY', 10, 150.0
            ),
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            ticker='AAPL',
            action='BUY',
            quantity=10,
            price=150.0,
            total_cost=1500.0,
            position_before=0,
            position_after=10,
            cash_before=100000.0,
            cash_after=98500.0,
            note='Test trade'
        )
        db.session.add(trade)
        db.session.commit()

        yield trade


@pytest.fixture(scope='function')
def authenticated_client(client, app):
    """Create an authenticated test client."""
    with app.app_context():
        # Set up admin credentials for testing
        app.config['ADMIN_USERNAME'] = 'admin'
        app.config['ADMIN_PASSWORD_HASH'] = '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4qIUj.YD1zQHYN4C'  # 'testpassword'

        with client.session_transaction() as sess:
            sess['_user_id'] = 'admin'
            sess['_fresh'] = True

        yield client
