# constants.py
"""
Application constants and limits.
These are hardcoded values that control application behavior.
Modify these values directly if you need to change limits.
"""

# =============================================================================
# API LIMITS
# =============================================================================

# Maximum days allowed for timeline/price queries (prevents huge DB queries)
MAX_TIMELINE_DAYS = 3650  # 10 years

# Default number of days for timeline queries
DEFAULT_TIMELINE_DAYS = 90

# Default number of trades returned by /api/trades
DEFAULT_TRADE_LIMIT = 20

# Maximum trades that can be requested
MAX_TRADE_LIMIT = 1000

# =============================================================================
# PORTFOLIO DEFAULTS
# =============================================================================

# Default lookback period for historical data backfill
DEFAULT_LOOKBACK_DAYS = 365

# Default benchmark ticker for comparison charts
DEFAULT_BENCHMARK_TICKER = 'SPY'

# Default risk-free rate (annual) when not available from FRED
DEFAULT_RISK_FREE_RATE = 0.045  # 4.5%

# =============================================================================
# VALIDATION LIMITS
# =============================================================================

# Maximum length for stock ticker symbols
MAX_TICKER_LENGTH = 10

# Maximum length for trade notes
MAX_NOTE_LENGTH = 1000

# =============================================================================
# RATE LIMITING
# =============================================================================

# Public API rate limit (requests per minute)
PUBLIC_API_RATE_LIMIT = "60 per minute"

# Authenticated API rate limit
AUTH_API_RATE_LIMIT = "120 per minute"
