# providers/__init__.py
"""
Price data provider using Alpha Vantage API.
"""

import os
from .alphavantage_provider import (
    AlphaVantageProvider,
    AlphaVantageError,
    AlphaVantageQuotaError,
    AlphaVantageInvalidKeyError
)


def create_provider(config):
    """Create Alpha Vantage provider from app config."""
    api_key = os.environ.get('ALPHA_VANTAGE_API_KEY', '')
    if not api_key:
        raise ValueError(
            "ALPHA_VANTAGE_API_KEY environment variable not set. "
            "Get your free key at: https://www.alphavantage.co/support/#api-key"
        )

    is_paid = os.environ.get('ALPHA_VANTAGE_PAID_TIER', 'false').lower() == 'true'

    return AlphaVantageProvider({
        'api_key': api_key,
        'max_retries': config.get('MAX_RETRIES', 3),
        'retry_delay': config.get('RETRY_DELAY', 5),
        'rate_limit_delay': 1 if is_paid else 12,
        'is_paid_tier': is_paid
    })


__all__ = [
    'AlphaVantageProvider',
    'AlphaVantageError',
    'AlphaVantageQuotaError',
    'AlphaVantageInvalidKeyError',
    'create_provider'
]
