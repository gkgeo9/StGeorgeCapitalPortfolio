# providers/alphavantage_provider.py
"""
Alpha Vantage price data provider.
Official API with reliable rate limits.
"""

import requests
import pandas as pd
import time
from datetime import datetime, date, timezone, timedelta
from typing import Dict, List, Optional


class AlphaVantageError(Exception):
    """Base exception for Alpha Vantage errors"""
    pass


class AlphaVantageQuotaError(AlphaVantageError):
    """Raised when quota is exceeded"""
    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message)
        self.retry_after = retry_after


class AlphaVantageInvalidKeyError(AlphaVantageError):
    """Raised when API key is invalid"""
    pass


class AlphaVantageProvider:
    """
    Alpha Vantage API price provider.

    Rate Limits:
    - Free: 5 calls/min, 500 calls/day
    - Paid ($49.99/mo): 75 calls/min, unlimited daily
    """

    def __init__(self, config: Dict):
        self.config = config
        self.max_retries = config.get('max_retries', 3)
        self.retry_delay = config.get('retry_delay', 5)

        self.api_key = config.get('api_key')
        if not self.api_key:
            raise ValueError("Alpha Vantage API key is required")

        self.base_url = "https://www.alphavantage.co/query"
        self.rate_limit_delay = config.get('rate_limit_delay', 12)  # 12s = 5 req/min for free tier
        self.is_paid_tier = config.get('is_paid_tier', False)

        # Quota tracking
        self._daily_calls = 0
        self._daily_reset = datetime.now(timezone.utc).date()
        self._minute_calls: List[datetime] = []
        self._last_successful_call: Optional[datetime] = None

        # Set limits based on tier
        if self.is_paid_tier:
            self.rate_limit_delay = 1  # Paid tier: 75 req/min = ~0.8s, use 1s to be safe
            self._daily_limit = float('inf')  # Unlimited
            self._minute_limit = 75
            print(f"  Initialized Alpha Vantage provider (PAID tier, {self.rate_limit_delay}s delay)")
        else:
            self._daily_limit = 500
            self._minute_limit = 5
            print(f"  Initialized Alpha Vantage provider (FREE tier, {self.rate_limit_delay}s delay)")
            print(f"  WARNING: Free tier limited to {self._minute_limit} req/min, {self._daily_limit} req/day")

    def get_provider_name(self) -> str:
        tier = "PAID" if self.is_paid_tier else "FREE"
        return f"Alpha Vantage ({tier} tier)"

    def get_quota_status(self) -> Dict:
        """Get current quota usage status"""
        now = datetime.now(timezone.utc)

        # Reset daily counter at midnight UTC
        if now.date() > self._daily_reset:
            self._daily_calls = 0
            self._daily_reset = now.date()

        # Clean minute window
        one_minute_ago = now - timedelta(minutes=1)
        self._minute_calls = [t for t in self._minute_calls if t > one_minute_ago]

        return {
            'daily_calls': self._daily_calls,
            'daily_limit': self._daily_limit if self._daily_limit != float('inf') else 'unlimited',
            'daily_remaining': max(0, self._daily_limit - self._daily_calls) if self._daily_limit != float('inf') else 'unlimited',
            'minute_calls': len(self._minute_calls),
            'minute_limit': self._minute_limit,
            'minute_remaining': max(0, self._minute_limit - len(self._minute_calls)),
            'is_paid_tier': self.is_paid_tier,
            'last_successful_call': self._last_successful_call.isoformat() if self._last_successful_call else None
        }

    def _check_quota(self) -> None:
        """Check if we're within rate limits. Raises AlphaVantageQuotaError if exceeded."""
        now = datetime.now(timezone.utc)

        # Reset daily counter at midnight UTC
        if now.date() > self._daily_reset:
            self._daily_calls = 0
            self._daily_reset = now.date()

        # Clean minute window
        one_minute_ago = now - timedelta(minutes=1)
        self._minute_calls = [t for t in self._minute_calls if t > one_minute_ago]

        # Check daily limit
        if self._daily_limit != float('inf') and self._daily_calls >= self._daily_limit:
            raise AlphaVantageQuotaError(
                f"Daily quota exceeded ({int(self._daily_limit)} calls). Try again tomorrow.",
                retry_after=86400  # 24 hours
            )

        # Check minute limit
        if len(self._minute_calls) >= self._minute_limit:
            wait_time = 60 - int((now - self._minute_calls[0]).total_seconds())
            raise AlphaVantageQuotaError(
                f"Rate limit exceeded ({self._minute_limit} calls/min). Wait {wait_time}s.",
                retry_after=wait_time
            )

    def _record_call(self) -> None:
        """Record an API call for quota tracking"""
        now = datetime.now(timezone.utc)
        self._daily_calls += 1
        self._minute_calls.append(now)
        self._last_successful_call = now

    def is_market_open(self) -> bool:
        """
        Check market status using Alpha Vantage MARKET_STATUS endpoint.
        Free endpoint, doesn't count against quota.
        """
        try:
            params = {
                'function': 'MARKET_STATUS',
                'apikey': self.api_key
            }

            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Check if US market is open
            if 'markets' in data:
                for market in data['markets']:
                    if market.get('region') == 'United States' and market.get('primary_exchanges'):
                        if market.get('current_status') == 'open':
                            return True

            return False

        except Exception as e:
            print(f"  Warning: Could not check market status: {e}")
            return True  # Assume open if can't check

    def _make_request(self, params: Dict) -> Dict:
        """
        Make API request with rate limiting, quota tracking, and error handling.
        """
        # Check quota before making request
        self._check_quota()

        params['apikey'] = self.api_key

        for attempt in range(self.max_retries):
            try:
                if attempt > 0:
                    wait_time = self.retry_delay * (2 ** attempt)
                    print(f"  Retry attempt {attempt + 1}/{self.max_retries} after {wait_time}s...")
                    time.sleep(wait_time)

                response = requests.get(self.base_url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()

                # Check for API error messages
                if 'Error Message' in data:
                    msg = data['Error Message']
                    if 'Invalid API call' in msg or 'invalid' in msg.lower():
                        raise AlphaVantageError(f"Invalid API call: {msg}")
                    if 'api key' in msg.lower():
                        raise AlphaVantageInvalidKeyError("Invalid Alpha Vantage API key")
                    raise AlphaVantageError(f"API Error: {msg}")

                if 'Note' in data:
                    note = data['Note']
                    # Rate limit message
                    if 'API call frequency' in note:
                        raise AlphaVantageQuotaError(
                            f"Rate limit exceeded (5 calls/minute for free tier)",
                            retry_after=60
                        )
                    elif 'premium' in note.lower() or 'upgrade' in note.lower():
                        raise AlphaVantageQuotaError(
                            "Daily quota exhausted. Upgrade to premium or wait until tomorrow.",
                            retry_after=86400
                        )
                    else:
                        print(f"  API Note: {note}")

                # Record successful call for quota tracking
                self._record_call()

                # Add rate limit delay
                time.sleep(self.rate_limit_delay)

                return data

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    raise AlphaVantageQuotaError(
                        "Alpha Vantage rate limit exceeded (HTTP 429)",
                        retry_after=60
                    )
                else:
                    raise
            except (AlphaVantageQuotaError, AlphaVantageInvalidKeyError):
                # Don't retry quota or auth errors
                raise
            except Exception as e:
                if attempt < self.max_retries - 1:
                    continue
                else:
                    raise

        raise ConnectionError(f"Failed after {self.max_retries} attempts")

    def get_current_prices(self, tickers: List[str]) -> Dict[str, float]:
        """
        Get current prices using GLOBAL_QUOTE endpoint.
        Each ticker requires 1 API call.
        """
        tickers = self._validate_tickers(tickers)
        prices = {}

        print(f"  Fetching {len(tickers)} prices from Alpha Vantage...")

        for ticker in tickers:
            try:
                params = {
                    'function': 'GLOBAL_QUOTE',
                    'symbol': ticker
                }

                data = self._make_request(params)

                if 'Global Quote' in data and data['Global Quote']:
                    quote = data['Global Quote']

                    # Alpha Vantage returns price as string
                    price_str = quote.get('05. price', '0')
                    price = float(price_str)

                    self._assert_price(price, ticker, "get_current_prices")
                    prices[ticker] = price

                    print(f"  ✓ {ticker}: ${price:.2f}")
                else:
                    print(f"  ✗ {ticker}: No quote data returned")
                    prices[ticker] = None

            except Exception as e:
                print(f"  ✗ {ticker}: Error - {e}")
                prices[ticker] = None

        return prices

    def get_historical_prices(
            self,
            ticker: str,
            start_date: date,
            end_date: date
    ) -> pd.DataFrame:
        """
        Get historical daily prices using TIME_SERIES_DAILY endpoint.
        Returns up to 100 days (compact) or 20+ years (full).
        """
        ticker = self._validate_tickers([ticker])[0]

        # Validate dates
        self._assert_date(datetime.combine(start_date, datetime.min.time()), ticker, "start_date")
        self._assert_date(datetime.combine(end_date, datetime.min.time()), ticker, "end_date")

        if start_date > end_date:
            raise ValueError(f"start_date ({start_date}) cannot be after end_date ({end_date})")

        # Determine outputsize
        days_requested = (end_date - start_date).days
        outputsize = 'full' if days_requested > 100 else 'compact'

        print(f"  Fetching {ticker} history ({start_date} to {end_date}, {outputsize})...")

        try:
            params = {
                'function': 'TIME_SERIES_DAILY',
                'symbol': ticker,
                'outputsize': outputsize
            }

            data = self._make_request(params)

            if 'Time Series (Daily)' not in data:
                print(f"  Warning: No time series data for {ticker}")
                return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

            time_series = data['Time Series (Daily)']

            # Convert to DataFrame
            rows = []
            for date_str, values in time_series.items():
                ts = datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)

                # Filter by date range
                if start_date <= ts.date() <= end_date:
                    rows.append({
                        'timestamp': ts,
                        'open': float(values['1. open']),
                        'high': float(values['2. high']),
                        'low': float(values['3. low']),
                        'close': float(values['4. close']),
                        'volume': int(values['5. volume'])
                    })

            if not rows:
                print(f"  Warning: No data in requested date range")
                return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

            df = pd.DataFrame(rows)
            df = df.sort_values('timestamp').reset_index(drop=True)

            # Validate all data
            df = self.validate_price_data(df, ticker)

            print(f"  ✓ Retrieved {len(df)} days of data for {ticker}")

            return df

        except Exception as e:
            print(f"  ✗ Error fetching {ticker}: {e}")
            raise

    # ========================================
    # VALIDATION METHODS
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
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        if dt > now + timedelta(days=1):
            # TODO THIS WILL NEED TO EVENTUALLY BE FIXED TO REMOV ETHE + TIME DELTA FOR NOW IT IS OK I THINK
            raise ValueError(f"[{ticker}] date cannot be in future in {context}")

    def validate_price_data(self, df: pd.DataFrame, ticker: str) -> pd.DataFrame:
        """Validate DataFrame of historical prices"""
        required_cols = ['timestamp', 'close']
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")

        for idx, row in df.iterrows():
            self._assert_date(row['timestamp'], ticker, f"row {idx}")
            self._assert_price(row['close'], ticker, f"row {idx} close")

            if 'open' in df.columns and not pd.isna(row['open']):
                self._assert_price(row['open'], ticker, f"row {idx} open")
            if 'high' in df.columns and not pd.isna(row['high']):
                self._assert_price(row['high'], ticker, f"row {idx} high")
            if 'low' in df.columns and not pd.isna(row['low']):
                self._assert_price(row['low'], ticker, f"row {idx} low")
            if 'volume' in df.columns and not pd.isna(row['volume']):
                self._assert_volume(row['volume'], ticker, f"row {idx}")

        return df

    def __repr__(self):
        return f"<AlphaVantageProvider({self.get_provider_name()})>"