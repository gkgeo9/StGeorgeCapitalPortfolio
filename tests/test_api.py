"""
Tests for REST API endpoints.
"""

import pytest
import json
from datetime import datetime, timezone


class TestPortfolioEndpoint:
    """Test /api/portfolio endpoint."""

    def test_get_portfolio_success(self, client, app, init_database, sample_prices, sample_trade):
        """Test getting portfolio data."""
        response = client.get('/api/portfolio')

        assert response.status_code == 200
        data = json.loads(response.data)

        assert 'holdings' in data
        assert 'cash' in data
        assert 'total_value' in data
        assert 'total_pnl' in data

    def test_get_portfolio_empty(self, client, app, init_database):
        """Test getting portfolio when empty."""
        response = client.get('/api/portfolio')

        assert response.status_code == 200
        data = json.loads(response.data)

        assert data['cash'] == 100000.0
        assert data['total_value'] == 100000.0


class TestTradeEndpoint:
    """Test /api/trade endpoint."""

    def test_trade_requires_auth(self, client, app, init_database, sample_prices):
        """Test that trade endpoint requires authentication."""
        response = client.post('/api/trade',
            data=json.dumps({
                'ticker': 'AAPL',
                'action': 'BUY',
                'quantity': 10,
                'price': 150.0
            }),
            content_type='application/json'
        )

        # Should redirect to login or return 401
        assert response.status_code in [401, 302]

    def test_trade_buy_success(self, authenticated_client, app, init_database, sample_prices):
        """Test successful buy trade via API."""
        response = authenticated_client.post('/api/trade',
            data=json.dumps({
                'ticker': 'AAPL',
                'action': 'BUY',
                'quantity': 10,
                'price': 150.0
            }),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = json.loads(response.data)

        assert data['success'] is True
        assert 'trade' in data
        assert data['trade']['ticker'] == 'AAPL'
        assert data['trade']['action'] == 'BUY'

    def test_trade_sell_success(self, authenticated_client, app, init_database, sample_prices, sample_trade):
        """Test successful sell trade via API."""
        response = authenticated_client.post('/api/trade',
            data=json.dumps({
                'ticker': 'AAPL',
                'action': 'SELL',
                'quantity': 5,
                'price': 155.0
            }),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = json.loads(response.data)

        assert data['success'] is True
        assert data['trade']['action'] == 'SELL'
        assert data['trade']['quantity'] == 5

    def test_trade_missing_fields(self, authenticated_client, app, init_database):
        """Test trade with missing required fields."""
        response = authenticated_client.post('/api/trade',
            data=json.dumps({
                'ticker': 'AAPL',
                # Missing action, quantity, price
            }),
            content_type='application/json'
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    def test_trade_invalid_action(self, authenticated_client, app, init_database, sample_prices):
        """Test trade with invalid action."""
        response = authenticated_client.post('/api/trade',
            data=json.dumps({
                'ticker': 'AAPL',
                'action': 'HOLD',
                'quantity': 10,
                'price': 150.0
            }),
            content_type='application/json'
        )

        assert response.status_code == 400

    def test_trade_with_date(self, authenticated_client, app, init_database, sample_prices):
        """Test trade with historical date."""
        response = authenticated_client.post('/api/trade',
            data=json.dumps({
                'ticker': 'AAPL',
                'action': 'BUY',
                'quantity': 10,
                'price': 148.0,
                'date': '2024-01-01'
            }),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True


class TestTimelineEndpoint:
    """Test /api/timeline endpoint."""

    def test_get_timeline_success(self, client, app, init_database):
        """Test getting portfolio timeline."""
        response = client.get('/api/timeline')

        assert response.status_code == 200
        data = json.loads(response.data)

        assert 'dates' in data
        assert 'values' in data

    def test_get_timeline_with_days(self, client, app, init_database):
        """Test getting timeline with custom days."""
        response = client.get('/api/timeline?days=30')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'dates' in data

    def test_get_timeline_with_benchmark(self, client, app, init_database, sample_prices):
        """Test getting timeline with benchmark."""
        response = client.get('/api/timeline?include_benchmark=true')

        assert response.status_code == 200
        data = json.loads(response.data)

        assert 'benchmark_ticker' in data
        assert 'benchmark_pct' in data


class TestPerformanceEndpoint:
    """Test /api/performance endpoint."""

    def test_get_performance_success(self, client, app, init_database):
        """Test getting performance metrics."""
        response = client.get('/api/performance')

        assert response.status_code == 200
        data = json.loads(response.data)

        assert 'volatility' in data
        assert 'sharpe_ratio' in data


class TestTradesListEndpoint:
    """Test /api/trades endpoint."""

    def test_get_trades_empty(self, client, app, init_database):
        """Test getting trades when empty."""
        response = client.get('/api/trades')

        assert response.status_code == 200
        data = json.loads(response.data)

        assert 'trades' in data
        assert len(data['trades']) == 0

    def test_get_trades_with_data(self, client, app, init_database, sample_prices, sample_trade):
        """Test getting trades with data."""
        response = client.get('/api/trades')

        assert response.status_code == 200
        data = json.loads(response.data)

        assert len(data['trades']) == 1
        assert data['trades'][0]['ticker'] == 'AAPL'


class TestMarketStatusEndpoint:
    """Test /api/market-status endpoint (public)."""

    def test_get_market_status_public(self, client, app, init_database):
        """Test that market status is public."""
        response = client.get('/api/market-status')

        assert response.status_code == 200
        data = json.loads(response.data)

        assert 'market_open' in data


class TestProviderStatusEndpoint:
    """Test /api/provider-status endpoint (requires auth)."""

    def test_get_provider_status_requires_auth(self, client, app, init_database):
        """Test that provider status requires authentication."""
        response = client.get('/api/provider-status')

        # Should redirect to login or return 401
        assert response.status_code in [401, 302]

    def test_get_provider_status_authenticated(self, authenticated_client, app, init_database):
        """Test getting provider status when authenticated."""
        response = authenticated_client.get('/api/provider-status')

        assert response.status_code == 200
        data = json.loads(response.data)

        assert 'provider' in data


class TestRefreshEndpoint:
    """Test /api/refresh endpoint."""

    def test_refresh_requires_auth(self, client, app, init_database):
        """Test that refresh endpoint requires authentication."""
        response = client.post('/api/refresh')

        # Should redirect to login or return 401
        assert response.status_code in [401, 302]


class TestSnapshotEndpoint:
    """Test /api/snapshot endpoint."""

    def test_snapshot_requires_auth(self, client, app, init_database):
        """Test that snapshot endpoint requires authentication."""
        response = client.post('/api/snapshot')

        # Should redirect to login or return 401
        assert response.status_code in [401, 302]

    def test_snapshot_success(self, authenticated_client, app, init_database, sample_prices, sample_trade):
        """Test taking a snapshot."""
        response = authenticated_client.post('/api/snapshot',
            data=json.dumps({'note': 'Test snapshot'}),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True


class TestResetDbEndpoint:
    """Test /api/reset_db endpoint."""

    def test_reset_requires_auth(self, client, app, init_database):
        """Test that reset endpoint requires authentication."""
        response = client.post('/api/reset_db')

        # Should redirect to login or return 401
        assert response.status_code in [401, 302]


class TestStocksEndpoint:
    """Test /api/stocks endpoint."""

    def test_get_stocks_prices(self, client, app, init_database, sample_prices):
        """Test getting stock prices."""
        response = client.get('/api/stocks')

        assert response.status_code == 200
        data = json.loads(response.data)

        # Response is a dict with ticker keys, each containing prices and timestamps
        assert 'AAPL' in data or 'stocks' in data

    def test_get_stocks_with_days(self, client, app, init_database, sample_prices):
        """Test getting stock prices with custom days."""
        response = client.get('/api/stocks?days=30')

        assert response.status_code == 200


class TestHealthEndpoint:
    """Test /health endpoint."""

    def test_health_check(self, client, app):
        """Test health check endpoint."""
        response = client.get('/health')

        assert response.status_code == 200
        data = json.loads(response.data)

        assert data['status'] == 'healthy'
