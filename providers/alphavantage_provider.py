# providers/alphavantage_provider.py

import json
import logging
import requests
import pandas as pd
import time
from datetime import datetime, date, timezone, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class AlphaVantageError(Exception):
    pass


class AlphaVantageQuotaError(AlphaVantageError):
    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message)
        self.retry_after = retry_after


class AlphaVantageInvalidKeyError(AlphaVantageError):
    pass


class AlphaVantageProvider:
    def __init__(self, config: Dict):
        self.config = config
        self.max_retries = config.get('max_retries', 3)
        self.retry_delay = config.get('retry_delay', 5)

        self.api_key = config.get('api_key')
        if not self.api_key:
            raise ValueError("Alpha Vantage API key is required")

        self.base_url = "https://www.alphavantage.co/query"
        self.rate_limit_delay = config.get('rate_limit_delay', 12)
        self.is_paid_tier = config.get('is_paid_tier', False)

        self._daily_calls = 0
        self._daily_reset = datetime.now(timezone.utc).date()
        self._minute_calls: List[datetime] = []
        self._last_successful_call: Optional[datetime] = None

        if self.is_paid_tier:
            self.rate_limit_delay = 1
            self._daily_limit = float('inf')
            self._minute_limit = 75
            logger.info(f"Alpha Vantage provider initialized (PAID tier)")
        else:
            self._daily_limit = 500
            self._minute_limit = 5
            logger.info(f"Alpha Vantage provider initialized (FREE tier)")

    def get_provider_name(self) -> str:
        tier = "PAID" if self.is_paid_tier else "FREE"
        return f"AlphaVantage ({tier})"

    def get_quota_status(self) -> Dict:
        now = datetime.now(timezone.utc)

        if now.date() > self._daily_reset:
            self._daily_calls = 0
            self._daily_reset = now.date()

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
        now = datetime.now(timezone.utc)

        if now.date() > self._daily_reset:
            self._daily_calls = 0
            self._daily_reset = now.date()

        one_minute_ago = now - timedelta(minutes=1)
        self._minute_calls = [t for t in self._minute_calls if t > one_minute_ago]

        if self._daily_limit != float('inf') and self._daily_calls >= self._daily_limit:
            raise AlphaVantageQuotaError(
                f"Daily quota exceeded ({int(self._daily_limit)} calls)",
                retry_after=86400
            )

        if len(self._minute_calls) >= self._minute_limit:
            wait_time = 60 - int((now - self._minute_calls[0]).total_seconds())
            raise AlphaVantageQuotaError(
                f"Rate limit exceeded ({self._minute_limit} calls/min). Wait {wait_time}s.",
                retry_after=wait_time
            )

    def _record_call(self) -> None:
        now = datetime.now(timezone.utc)
        self._daily_calls += 1
        self._minute_calls.append(now)
        self._last_successful_call = now

    def is_market_open(self) -> bool:
        try:
            params = {'function': 'MARKET_STATUS', 'apikey': self.api_key}
            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if 'markets' in data:
                for market in data['markets']:
                    if market.get('region') == 'United States' and market.get('primary_exchanges'):
                        if market.get('current_status') == 'open':
                            return True
            return False
        except Exception as e:
            logger.warning(f"Could not check market status: {e}")
            return True

    def _make_request(self, params: Dict) -> Dict:
        self._check_quota()
        params['apikey'] = self.api_key

        for attempt in range(self.max_retries):
            try:
                if attempt > 0:
                    wait_time = self.retry_delay * (2 ** attempt)
                    logger.info(f"Retry {attempt + 1}/{self.max_retries} after {wait_time}s...")
                    time.sleep(wait_time)

                response = requests.get(self.base_url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()

                if 'Error Message' in data:
                    msg = data['Error Message']
                    if 'api key' in msg.lower():
                        raise AlphaVantageInvalidKeyError("Invalid Alpha Vantage API key")
                    raise AlphaVantageError(f"API Error: {msg}")

                if 'Note' in data:
                    note = data['Note']
                    if 'API call frequency' in note:
                        raise AlphaVantageQuotaError("Rate limit exceeded", retry_after=60)
                    elif 'premium' in note.lower() or 'upgrade' in note.lower():
                        raise AlphaVantageQuotaError("Daily quota exhausted", retry_after=86400)

                self._record_call()
                time.sleep(self.rate_limit_delay)
                return data

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    raise AlphaVantageQuotaError("HTTP 429 rate limit", retry_after=60)
                raise
            except (AlphaVantageQuotaError, AlphaVantageInvalidKeyError):
                raise
            except (requests.RequestException, ValueError, KeyError, json.JSONDecodeError) as e:
                logger.warning(f"Request failed (attempt {attempt + 1}): {e}")
                if attempt >= self.max_retries - 1:
                    raise

        raise ConnectionError(f"Failed after {self.max_retries} attempts")

    def get_current_prices(self, tickers: List[str]) -> Dict[str, float]:
        tickers = self._validate_tickers(tickers)
        prices = {}

        logger.info(f"Fetching {len(tickers)} prices from Alpha Vantage...")

        for ticker in tickers:
            try:
                data = self._make_request({'function': 'GLOBAL_QUOTE', 'symbol': ticker})

                if 'Global Quote' in data and data['Global Quote']:
                    quote = data['Global Quote']
                    price = float(quote.get('05. price', '0'))
                    self._assert_price(price, ticker, "get_current_prices")
                    prices[ticker] = price
                    logger.debug(f"{ticker}: ${price:.2f}")
                else:
                    logger.warning(f"{ticker}: No quote data")
                    prices[ticker] = None

            except Exception as e:
                logger.error(f"{ticker}: Error - {e}")
                prices[ticker] = None

        return prices

    def get_historical_prices(self, ticker: str, start_date: date, end_date: date) -> pd.DataFrame:
        ticker = self._validate_tickers([ticker])[0]

        self._assert_date(datetime.combine(start_date, datetime.min.time()), ticker, "start_date")
        self._assert_date(datetime.combine(end_date, datetime.min.time()), ticker, "end_date")

        if start_date > end_date:
            raise ValueError(f"start_date ({start_date}) after end_date ({end_date})")

        days_requested = (end_date - start_date).days
        outputsize = 'full' if days_requested > 100 else 'compact'

        logger.info(f"Fetching {ticker} history ({start_date} to {end_date}, {outputsize})...")

        try:
            data = self._make_request({
                'function': 'TIME_SERIES_DAILY',
                'symbol': ticker,
                'outputsize': outputsize
            })

            if 'Time Series (Daily)' not in data:
                logger.warning(f"No time series data for {ticker}")
                return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

            time_series = data['Time Series (Daily)']
            rows = []

            for date_str, values in time_series.items():
                ts = datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
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
                logger.warning("No data in requested date range")
                return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

            df = pd.DataFrame(rows).sort_values('timestamp').reset_index(drop=True)
            df = self.validate_price_data(df, ticker)

            logger.info(f"Retrieved {len(df)} days of data for {ticker}")
            return df

        except Exception as e:
            logger.error(f"Error fetching {ticker}: {e}")
            raise

    def _validate_tickers(self, tickers: List[str]) -> List[str]:
        if not isinstance(tickers, list) or not tickers:
            raise ValueError("tickers must be a non-empty list")
        clean = []
        for t in tickers:
            if not isinstance(t, str) or not t.strip():
                raise ValueError(f"Invalid ticker: {t!r}")
            clean.append(t.strip().upper())
        return list(dict.fromkeys(clean))

    def _assert_price(self, price: float, ticker: str, context: str) -> None:
        if pd.isna(price):
            raise ValueError(f"[{ticker}] price is NaN in {context}")
        try:
            p = float(price)
        except Exception:
            raise ValueError(f"[{ticker}] invalid price in {context}")
        if p <= 0:
            raise ValueError(f"[{ticker}] price must be > 0 in {context}")

    def _assert_volume(self, volume: int, ticker: str, context: str) -> None:
        if pd.isna(volume):
            raise ValueError(f"[{ticker}] volume is NaN in {context}")
        try:
            v = int(volume)
        except Exception:
            raise ValueError(f"[{ticker}] invalid volume in {context}")
        if v < 0:
            raise ValueError(f"[{ticker}] volume cannot be negative in {context}")

    def _assert_date(self, dt: datetime, ticker: str, context: str) -> None:
        if not isinstance(dt, (datetime, date)):
            raise ValueError(f"[{ticker}] invalid date type in {context}")
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        if dt > now + timedelta(days=1):
            raise ValueError(f"[{ticker}] date cannot be in future in {context}")

    def validate_price_data(self, df: pd.DataFrame, ticker: str) -> pd.DataFrame:
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
