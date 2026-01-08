# providers/base_provider.py
"""
Abstract base class for price data providers.
Enforces consistent interface across yfinance, Alpha Vantage, etc.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple
from datetime import datetime, date
import pandas as pd


class BasePriceProvider(ABC):
    """
    Abstract base class for stock price data providers.
    All providers must implement these methods with consistent validation.
    """

    def __init__(self, config: Dict):
        """
        Initialize provider with configuration.

        Args:
            config: Dictionary containing provider-specific settings
        """
        self.config = config
        self.max_retries = config.get('max_retries', 3)
        self.retry_delay = config.get('retry_delay', 5)

    # ========================================
    # VALIDATION METHODS (from CSV logger)
    # ========================================

    def _validate_tickers(self, tickers: List[str]) -> List[str]:
        """Validate and clean ticker list"""
        if not isinstance(tickers, list) or not tickers:
            raise ValueError("tickers must be a non-empty list")
        clean = []
        for t in tickers:
            if not isinstance(t, str) or not t.strip():
                raise ValueError(f"Invalid ticker: {t!r}")
            clean.append(t.strip().upper())
        # Remove duplicates, preserve order
        return list(dict.fromkeys(clean))

    def _assert_price(self, price: float, ticker: str, context: str) -> None:
        """Validate stock price"""
        if pd.isna(price):
            raise ValueError(f"[{ticker}] price is NaN in {context}")
        try:
            p = float(price)
        except Exception:
            raise ValueError(f"[{ticker}] invalid price in {context}")
        if p <= 0:
            raise ValueError(f"[{ticker}] price must be > 0 in {context}")

    def _assert_volume(self, volume: int, ticker: str, context: str) -> None:
        """Validate trading volume"""
        if pd.isna(volume):
            raise ValueError(f"[{ticker}] volume is NaN in {context}")
        try:
            v = int(volume)
        except Exception:
            raise ValueError(f"[{ticker}] invalid volume in {context}")
        if v < 0:
            raise ValueError(f"[{ticker}] volume cannot be negative in {context}")

    def _assert_date(self, dt: datetime, ticker: str, context: str) -> None:
        """Validate date/timestamp"""
        if not isinstance(dt, (datetime, date)):
            raise ValueError(f"[{ticker}] invalid date type in {context}")
        if dt > datetime.now():
            raise ValueError(f"[{ticker}] date cannot be in future in {context}")

    # ========================================
    # ABSTRACT METHODS (must be implemented)
    # ========================================

    @abstractmethod
    def get_current_prices(self, tickers: List[str]) -> Dict[str, float]:
        """
        Get current/latest prices for given tickers.

        Args:
            tickers: List of stock symbols

        Returns:
            Dict mapping ticker -> current price

        Raises:
            ValueError: If tickers invalid or prices cannot be validated
            ConnectionError: If provider unavailable
        """
        pass

    @abstractmethod
    def get_historical_prices(
            self,
            ticker: str,
            start_date: date,
            end_date: date
    ) -> pd.DataFrame:
        """
        Get historical OHLCV data for a single ticker.

        Args:
            ticker: Stock symbol
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
            All prices validated to be > 0

        Raises:
            ValueError: If dates invalid or data cannot be validated
            ConnectionError: If provider unavailable
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return human-readable provider name"""
        pass

    @abstractmethod
    def is_market_open(self) -> bool:
        """
        Check if market is currently open.
        Optional implementation - return True if unknown.
        """
        pass

    # ========================================
    # COMMON HELPER METHODS
    # ========================================

    def validate_price_data(self, df: pd.DataFrame, ticker: str) -> pd.DataFrame:
        """
        Validate DataFrame of historical prices.
        Ensures all required columns exist and data is valid.
        """
        required_cols = ['timestamp', 'close']
        optional_cols = ['open', 'high', 'low', 'volume']

        # Check required columns
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")

        # Validate each row
        for idx, row in df.iterrows():
            # Validate timestamp
            self._assert_date(row['timestamp'], ticker, f"row {idx}")

            # Validate close price (required)
            self._assert_price(row['close'], ticker, f"row {idx} close")

            # Validate optional OHLC prices
            if 'open' in df.columns and not pd.isna(row['open']):
                self._assert_price(row['open'], ticker, f"row {idx} open")
            if 'high' in df.columns and not pd.isna(row['high']):
                self._assert_price(row['high'], ticker, f"row {idx} high")
            if 'low' in df.columns and not pd.isna(row['low']):
                self._assert_price(row['low'], ticker, f"row {idx} low")

            # Validate volume
            if 'volume' in df.columns and not pd.isna(row['volume']):
                self._assert_volume(row['volume'], ticker, f"row {idx}")

            # Validate OHLC relationships
            if all(col in df.columns for col in ['open', 'high', 'low', 'close']):
                if not pd.isna(row['high']) and not pd.isna(row['low']):
                    if row['high'] < row['low']:
                        raise ValueError(
                            f"[{ticker}] row {idx}: high ({row['high']}) < low ({row['low']})"
                        )

                # High should be >= close and open
                if not pd.isna(row['high']):
                    if not pd.isna(row['close']) and row['high'] < row['close']:
                        raise ValueError(
                            f"[{ticker}] row {idx}: high ({row['high']}) < close ({row['close']})"
                        )
                    if not pd.isna(row['open']) and row['high'] < row['open']:
                        raise ValueError(
                            f"[{ticker}] row {idx}: high ({row['high']}) < open ({row['open']})"
                        )

                # Low should be <= close and open
                if not pd.isna(row['low']):
                    if not pd.isna(row['close']) and row['low'] > row['close']:
                        raise ValueError(
                            f"[{ticker}] row {idx}: low ({row['low']}) > close ({row['close']})"
                        )
                    if not pd.isna(row['open']) and row['low'] > row['open']:
                        raise ValueError(
                            f"[{ticker}] row {idx}: low ({row['low']}) > open ({row['open']})"
                        )

        return df

    def __repr__(self):
        return f"<{self.__class__.__name__}(provider={self.get_provider_name()})>"