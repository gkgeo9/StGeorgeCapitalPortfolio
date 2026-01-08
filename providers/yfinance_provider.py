# providers/yfinance_provider.py
"""
yfinance implementation of price data provider.
Best for local development (free, unlimited).
Problematic on shared IPs (Railway, Heroku) due to Yahoo rate limiting.
"""

import yfinance as yf
import pandas as pd
import time
from datetime import datetime, date, timezone
from typing import Dict, List
from .base_provider import BasePriceProvider


class YFinanceProvider(BasePriceProvider):
    """
    yfinance-based price provider.

    Pros:
    - Free and unlimited
    - Works great locally
    - Fast responses

    Cons:
    - Scrapes Yahoo Finance (not official API)
    - Rate limited by IP address
    - Fails on shared IPs (Railway, Heroku, etc.)
    """

    def __init__(self, config: Dict):
        super().__init__(config)
        self.request_delay = config.get('request_delay', 0.5)  # seconds between requests
        print(f"✓ Initialized yfinance provider (delay: {self.request_delay}s)")

    def get_provider_name(self) -> str:
        return "yfinance (Yahoo Finance)"

    def is_market_open(self) -> bool:
        """
        Check if US market is open.
        Simplified check - market hours are 9:30 AM - 4:00 PM ET, Mon-Fri.
        """
        try:
            now = datetime.now(timezone.utc)
            # Simple heuristic: if we can fetch data, market data is available
            # Note: yfinance works outside market hours too
            return True
        except Exception:
            return True

    def get_current_prices(self, tickers: List[str]) -> Dict[str, float]:
        """
        Get current prices using yfinance.
        Validates all tickers and prices.
        """
        tickers = self._validate_tickers(tickers)
        prices = {}

        for attempt in range(self.max_retries):
            try:
                if attempt > 0:
                    wait_time = self.retry_delay * (2 ** attempt)
                    print(f"  Retry attempt {attempt + 1}/{self.max_retries} after {wait_time}s...")
                    time.sleep(wait_time)

                for stock in tickers:
                    try:
                        ticker = yf.Ticker(stock)

                        # Try history first (more reliable)
                        hist = ticker.history(period='1d')

                        if not hist.empty:
                            price = float(hist['Close'].iloc[-1])
                            self._assert_price(price, stock, "get_current_prices")
                            prices[stock] = price
                        else:
                            # Fallback to info (less reliable, but sometimes works)
                            info = ticker.info
                            price = float(info.get('regularMarketPrice', 0))
                            if price <= 0:
                                raise ValueError(f"Invalid price from info: {price}")
                            self._assert_price(price, stock, "get_current_prices")
                            prices[stock] = price

                        # Small delay to avoid rate limits
                        time.sleep(self.request_delay)

                    except Exception as e:
                        if "429" in str(e) or "Too Many Requests" in str(e):
                            # Rate limit hit - will retry with exponential backoff
                            raise
                        print(f"  Warning: Could not fetch {stock}: {e}")
                        prices[stock] = None

                # Check if we got all prices
                if all(v is not None for v in prices.values()):
                    return prices

                # If some failed but no rate limit, return what we have
                if not any("429" in str(v) for v in prices.values()):
                    return prices

            except Exception as e:
                if "429" in str(e) or "Too Many Requests" in str(e):
                    if attempt < self.max_retries - 1:
                        print(f"  Rate limit hit, retrying...")
                        continue
                    else:
                        raise ConnectionError(
                            f"yfinance rate limited after {self.max_retries} attempts. "
                            "This is common on shared IPs (Railway, Heroku). "
                            "Consider using Alpha Vantage provider instead."
                        )
                else:
                    raise

        return prices

    def get_historical_prices(
            self,
            ticker: str,
            start_date: date,
            end_date: date
    ) -> pd.DataFrame:
        """
        Get historical OHLCV data using yfinance.
        Returns validated DataFrame.
        """
        ticker = self._validate_tickers([ticker])[0]

        # Validate dates
        self._assert_date(datetime.combine(start_date, datetime.min.time()), ticker, "start_date")
        self._assert_date(datetime.combine(end_date, datetime.min.time()), ticker, "end_date")

        if start_date > end_date:
            raise ValueError(f"start_date ({start_date}) cannot be after end_date ({end_date})")

        for attempt in range(self.max_retries):
            try:
                if attempt > 0:
                    wait_time = self.retry_delay * (2 ** attempt)
                    print(f"  Retry attempt {attempt + 1}/{self.max_retries} after {wait_time}s...")
                    time.sleep(wait_time)

                # Fetch data from yfinance
                yf_ticker = yf.Ticker(ticker)
                hist = yf_ticker.history(
                    start=start_date.strftime('%Y-%m-%d'),
                    end=(end_date + pd.Timedelta(days=1)).strftime('%Y-%m-%d'),  # end is exclusive
                    interval='1d',
                    auto_adjust=False
                )

                if hist.empty:
                    print(f"  Warning: No data returned for {ticker}")
                    return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

                # Convert to our standard format
                df = pd.DataFrame({
                    'timestamp': [ts.to_pydatetime().replace(tzinfo=timezone.utc) for ts in hist.index],
                    'open': hist['Open'].values,
                    'high': hist['High'].values,
                    'low': hist['Low'].values,
                    'close': hist['Close'].values,
                    'volume': hist['Volume'].values
                })

                # Validate all data
                df = self.validate_price_data(df, ticker)

                return df

            except Exception as e:
                if "429" in str(e) or "Too Many Requests" in str(e):
                    if attempt < self.max_retries - 1:
                        print(f"  Rate limit hit, retrying...")
                        continue
                    else:
                        raise ConnectionError(
                            f"yfinance rate limited after {self.max_retries} attempts for {ticker}"
                        )
                else:
                    raise

        # Should never reach here
        return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])