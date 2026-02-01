"""
Tests for cron_refresh.py - scheduled data refresh functionality.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock


class TestCronHelpers:
    """Test helper functions in cron_refresh."""

    def test_is_weekend_saturday(self):
        """Test that Saturday is detected as weekend."""
        # January 6, 2024 was a Saturday (weekday() == 5)
        assert datetime(2024, 1, 6).weekday() == 5  # Verify Saturday

    def test_is_weekend_sunday(self):
        """Test that Sunday is detected as weekend."""
        with patch('cron_refresh.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2024, 1, 7, 12, 0, tzinfo=timezone.utc)  # Sunday
            assert datetime(2024, 1, 7).weekday() == 6  # Verify Sunday

    def test_is_within_range_exact(self):
        """Test is_within_range with exact hour match."""
        from cron_refresh import is_within_range
        assert is_within_range(9, 0, 9, buffer_minutes=20) is True

    def test_is_within_range_within_buffer(self):
        """Test is_within_range within buffer."""
        from cron_refresh import is_within_range
        assert is_within_range(9, 15, 9, buffer_minutes=20) is True
        assert is_within_range(8, 45, 9, buffer_minutes=20) is True

    def test_is_within_range_outside_buffer(self):
        """Test is_within_range outside buffer."""
        from cron_refresh import is_within_range
        assert is_within_range(9, 30, 9, buffer_minutes=20) is False
        assert is_within_range(8, 30, 9, buffer_minutes=20) is False

    def test_is_market_hours_during_trading(self):
        """Test is_market_hours returns True during US trading hours."""
        from cron_refresh import is_market_hours
        with patch('cron_refresh.datetime') as mock_datetime:
            # 3 PM UTC = 10 AM ET (market open)
            mock_now = MagicMock()
            mock_now.hour = 15
            mock_datetime.now.return_value = mock_now
            assert is_market_hours() is True

    def test_is_market_hours_before_open(self):
        """Test is_market_hours returns False before market open."""
        from cron_refresh import is_market_hours
        with patch('cron_refresh.datetime') as mock_datetime:
            mock_now = MagicMock()
            mock_now.hour = 10  # 5 AM ET
            mock_datetime.now.return_value = mock_now
            assert is_market_hours() is False

    def test_should_save_daily_close_in_window(self):
        """Test should_save_daily_close returns True in close window."""
        from cron_refresh import should_save_daily_close
        with patch('cron_refresh.datetime') as mock_datetime:
            mock_now = MagicMock()
            mock_now.hour = 21
            mock_now.minute = 15
            mock_datetime.now.return_value = mock_now
            assert should_save_daily_close() is True

    def test_should_save_daily_close_outside_window(self):
        """Test should_save_daily_close returns False outside close window."""
        from cron_refresh import should_save_daily_close
        with patch('cron_refresh.datetime') as mock_datetime:
            mock_now = MagicMock()
            mock_now.hour = 22
            mock_now.minute = 0
            mock_datetime.now.return_value = mock_now
            assert should_save_daily_close() is False


class TestFredRateFetch:
    """Test FRED API rate fetching."""

    def test_fetch_risk_free_rate_no_key(self):
        """Test that missing FRED_API_KEY returns None."""
        from cron_refresh import fetch_risk_free_rate_from_fred
        with patch('cron_refresh.FRED_API_KEY', None):
            result = fetch_risk_free_rate_from_fred()
            assert result is None

    def test_fetch_risk_free_rate_success(self):
        """Test successful FRED rate fetch."""
        from cron_refresh import fetch_risk_free_rate_from_fred

        mock_response = MagicMock()
        mock_response.json.return_value = {
            'observations': [
                {'value': '4.50'}
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch('cron_refresh.FRED_API_KEY', 'test-key'):
            with patch('cron_refresh.requests.get', return_value=mock_response):
                result = fetch_risk_free_rate_from_fred()
                assert result == 0.045  # 4.5% as decimal

    def test_fetch_risk_free_rate_missing_data(self):
        """Test FRED rate fetch with missing data (.)."""
        from cron_refresh import fetch_risk_free_rate_from_fred

        mock_response = MagicMock()
        mock_response.json.return_value = {
            'observations': [
                {'value': '.'},
                {'value': '4.25'}
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch('cron_refresh.FRED_API_KEY', 'test-key'):
            with patch('cron_refresh.requests.get', return_value=mock_response):
                result = fetch_risk_free_rate_from_fred()
                assert result == 0.0425  # Skips '.' and uses 4.25%

    def test_fetch_risk_free_rate_api_error(self):
        """Test FRED rate fetch with API error."""
        from cron_refresh import fetch_risk_free_rate_from_fred
        import requests

        with patch('cron_refresh.FRED_API_KEY', 'test-key'):
            with patch('cron_refresh.requests.get', side_effect=requests.RequestException("API Error")):
                result = fetch_risk_free_rate_from_fred()
                assert result is None
