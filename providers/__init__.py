# providers/__init__.py
"""
Provider factory and exports.
Automatically selects appropriate provider based on configuration.
"""

import os
from typing import Dict, Optional
from .base_provider import BasePriceProvider
from .yfinance_provider import YFinanceProvider
from .alphavantage_provider import (
    AlphaVantageProvider,
    AlphaVantageError,
    AlphaVantageQuotaError,
    AlphaVantageInvalidKeyError
)


class PriceDataService:
    """
    Factory for creating appropriate price provider.
    Handles provider selection and graceful fallbacks.
    """

    @staticmethod
    def create_provider(config: Dict) -> BasePriceProvider:
        """
        Create price provider based on configuration.

        Priority:
        1. USE_ALPHA_VANTAGE=true → Alpha Vantage
        2. ALPHA_VANTAGE_API_KEY exists → Alpha Vantage
        3. Default → yfinance

        Args:
            config: Application configuration

        Returns:
            Configured provider instance
        """
        # Check environment override
        use_alpha_vantage = os.environ.get('USE_ALPHA_VANTAGE', '').lower() == 'true'
        alpha_vantage_key = os.environ.get('ALPHA_VANTAGE_API_KEY', '')

        # Determine provider
        provider_name = config.get('PRICE_PROVIDER', 'auto')

        if provider_name == 'alphavantage' or use_alpha_vantage:
            if not alpha_vantage_key:
                raise ValueError(
                    "Alpha Vantage selected but ALPHA_VANTAGE_API_KEY not set. "
                    "Please add it to your .env file."
                )
            return PriceDataService._create_alpha_vantage(config, alpha_vantage_key)

        elif provider_name == 'yfinance':
            return PriceDataService._create_yfinance(config)

        else:  # auto
            # Auto-detect: use Alpha Vantage if key exists, else yfinance
            if alpha_vantage_key:
                print("📊 Auto-detected Alpha Vantage API key, using Alpha Vantage provider")
                return PriceDataService._create_alpha_vantage(config, alpha_vantage_key)
            else:
                print("📊 No Alpha Vantage key found, using yfinance provider (local dev mode)")
                return PriceDataService._create_yfinance(config)

    @staticmethod
    def _create_yfinance(config: Dict) -> YFinanceProvider:
        """Create yfinance provider"""
        provider_config = {
            'max_retries': config.get('YFINANCE_MAX_RETRIES', 3),
            'retry_delay': config.get('YFINANCE_RETRY_DELAY', 5),
            'request_delay': config.get('YFINANCE_REQUEST_DELAY', 0.5)
        }
        return YFinanceProvider(provider_config)

    @staticmethod
    def _create_alpha_vantage(config: Dict, api_key: str) -> AlphaVantageProvider:
        """Create Alpha Vantage provider"""
        is_paid = os.environ.get('ALPHA_VANTAGE_PAID_TIER', 'false').lower() == 'true'

        provider_config = {
            'api_key': api_key,
            'max_retries': config.get('YFINANCE_MAX_RETRIES', 3),  # Reuse config
            'retry_delay': config.get('YFINANCE_RETRY_DELAY', 5),
            'rate_limit_delay': 1 if is_paid else 12,  # 75/min vs 5/min
            'is_paid_tier': is_paid
        }
        return AlphaVantageProvider(provider_config)


# Exports
__all__ = [
    'BasePriceProvider',
    'YFinanceProvider',
    'AlphaVantageProvider',
    'AlphaVantageError',
    'AlphaVantageQuotaError',
    'AlphaVantageInvalidKeyError',
    'PriceDataService'
]