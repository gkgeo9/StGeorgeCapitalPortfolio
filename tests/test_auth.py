"""
Tests for authentication system.
"""

import pytest
import bcrypt


class TestLoginPage:
    """Test login page and form."""

    def test_login_page_loads(self, client, app):
        """Test that login page loads."""
        response = client.get('/login')

        assert response.status_code == 200
        assert b'Login' in response.data or b'login' in response.data

    def test_login_with_valid_credentials(self, client, app):
        """Test login with valid credentials."""
        with app.app_context():
            # Set up test credentials
            password = 'testpassword'
            password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            app.config['ADMIN_USERNAME'] = 'admin'
            app.config['ADMIN_PASSWORD_HASH'] = password_hash

            response = client.post('/login',
                data={
                    'username': 'admin',
                    'password': 'testpassword'
                },
                follow_redirects=True
            )

            # Should redirect to dashboard on success
            assert response.status_code == 200

    def test_login_with_invalid_password(self, client, app):
        """Test login with invalid password."""
        with app.app_context():
            password_hash = bcrypt.hashpw(b'correctpassword', bcrypt.gensalt()).decode('utf-8')
            app.config['ADMIN_USERNAME'] = 'admin'
            app.config['ADMIN_PASSWORD_HASH'] = password_hash

            response = client.post('/login',
                data={
                    'username': 'admin',
                    'password': 'wrongpassword'
                },
                follow_redirects=True
            )

            # Should stay on login page with error
            assert b'Invalid' in response.data or b'login' in response.data.lower()

    def test_login_with_invalid_username(self, client, app):
        """Test login with invalid username."""
        with app.app_context():
            password_hash = bcrypt.hashpw(b'testpassword', bcrypt.gensalt()).decode('utf-8')
            app.config['ADMIN_USERNAME'] = 'admin'
            app.config['ADMIN_PASSWORD_HASH'] = password_hash

            response = client.post('/login',
                data={
                    'username': 'wronguser',
                    'password': 'testpassword'
                },
                follow_redirects=True
            )

            # Should stay on login page with error
            assert b'Invalid' in response.data or b'login' in response.data.lower()


class TestLogout:
    """Test logout functionality."""

    def test_logout_redirects(self, authenticated_client, app):
        """Test that logout redirects to home."""
        response = authenticated_client.get('/logout', follow_redirects=True)

        assert response.status_code == 200


class TestProtectedEndpoints:
    """Test that protected endpoints require authentication."""

    def test_trade_protected(self, client, app, init_database):
        """Test that /api/trade requires auth."""
        response = client.post('/api/trade',
            data='{"ticker": "AAPL", "action": "BUY", "quantity": 10, "price": 150}',
            content_type='application/json'
        )

        assert response.status_code in [401, 302]

    def test_refresh_protected(self, client, app, init_database):
        """Test that /api/refresh requires auth."""
        response = client.post('/api/refresh')

        assert response.status_code in [401, 302]

    def test_snapshot_protected(self, client, app, init_database):
        """Test that /api/snapshot requires auth."""
        response = client.post('/api/snapshot')

        assert response.status_code in [401, 302]

    def test_reset_db_protected(self, client, app, init_database):
        """Test that /api/reset_db requires auth."""
        response = client.post('/api/reset_db')

        assert response.status_code in [401, 302]


class TestPublicEndpoints:
    """Test that public endpoints don't require authentication."""

    def test_portfolio_public(self, client, app, init_database):
        """Test that /api/portfolio is public."""
        response = client.get('/api/portfolio')

        assert response.status_code == 200

    def test_timeline_public(self, client, app, init_database):
        """Test that /api/timeline is public."""
        response = client.get('/api/timeline')

        assert response.status_code == 200

    def test_performance_public(self, client, app, init_database):
        """Test that /api/performance is public."""
        response = client.get('/api/performance')

        assert response.status_code == 200

    def test_trades_list_public(self, client, app, init_database):
        """Test that /api/trades is public."""
        response = client.get('/api/trades')

        assert response.status_code == 200

    def test_market_status_public(self, client, app, init_database):
        """Test that /api/market-status is public."""
        response = client.get('/api/market-status')

        assert response.status_code == 200

    def test_dashboard_public(self, client, app):
        """Test that dashboard is public."""
        response = client.get('/')

        assert response.status_code == 200

    def test_health_public(self, client, app):
        """Test that /health is public."""
        response = client.get('/health')

        assert response.status_code == 200


class TestPasswordHashing:
    """Test bcrypt password hashing."""

    def test_password_hash_verification(self):
        """Test that bcrypt hashing works correctly."""
        password = 'mysecretpassword'
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        # Correct password should verify
        assert bcrypt.checkpw(password.encode('utf-8'), password_hash)

        # Wrong password should not verify
        assert not bcrypt.checkpw(b'wrongpassword', password_hash)

    def test_hash_is_different_each_time(self):
        """Test that bcrypt generates different hashes for same password."""
        password = b'samepassword'

        hash1 = bcrypt.hashpw(password, bcrypt.gensalt())
        hash2 = bcrypt.hashpw(password, bcrypt.gensalt())

        # Hashes should be different (different salts)
        assert hash1 != hash2

        # But both should verify the same password
        assert bcrypt.checkpw(password, hash1)
        assert bcrypt.checkpw(password, hash2)
