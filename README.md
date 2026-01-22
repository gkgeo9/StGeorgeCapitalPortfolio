# 📊 St. George Capital Portfolio Manager

A sophisticated Flask-based portfolio management system for tracking investments, executing trades, and analyzing performance with real-time market data from Alpha Vantage.

## ✨ Features

- **📈 Portfolio Tracking**: Real-time monitoring of stock holdings, cash balance, and total portfolio value
- **💹 Trade Execution**: Buy and sell stocks across multiple exchanges (US, Canada, UK)
- **📊 Performance Analytics**: Track total return, volatility, Sharpe ratio, max drawdown, and win rate
- **🎯 S&P 500 Benchmark**: Compare portfolio performance against SPY (S&P 500 ETF)
- **📉 Interactive Charts**: 90-day historical price movements with Plotly.js visualizations
- **🌓 Dark/Light Themes**: Premium dark mode with glassmorphism effects
- **⚡ Smart Data Management**: Efficient API quota management with local caching and backfilling
- **🔄 Manual Refresh**: User-controlled data updates with cooldown protection

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                   Frontend (Browser)                         │
│  dashboard.html │ dashboard.js │ dashboard.css               │
│  Plotly.js Charts │ Trade Modal │ Theme Toggle               │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP/JSON
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                 Backend (Flask API)                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   routes/    │  │  portfolio_  │  │   models.py  │      │
│  │   api.py     │──│   manager.py │──│   (ORM)      │      │
│  └──────────────┘  └───────┬──────┘  └──────┬───────┘      │
│                            │                 │               │
│                            ▼                 ▼               │
│                  ┌──────────────┐  ┌──────────────┐         │
│                  │  providers/  │  │  SQLAlchemy  │         │
│                  │ alphavantage │  │      DB      │         │
│                  └──────┬───────┘  └──────────────┘         │
└──────────────────────────┼──────────────────────────────────┘
                           │ HTTPS/JSON
                           ▼
                 ┌──────────────────┐
                 │ Alpha Vantage API│
                 │  (Market Data)   │
                 └──────────────────┘
                           │
                           ▼
                 ┌──────────────────┐
                 │ SQLite/PostgreSQL│
                 │   (Persistence)  │
                 └──────────────────┘
```

**Data Flow:**
1. User interacts with dashboard (view portfolio, execute trades, refresh data)
2. Frontend sends HTTP requests to Flask API endpoints
3. PortfolioManager processes business logic and calculations
4. For price data: Queries database cache or calls Alpha Vantage API
5. Database stores trades, prices, snapshots using SQLAlchemy ORM
6. Results formatted as JSON and returned to frontend
7. Charts and UI updated with new data

## 📁 Main Files & Components

### Backend Core

#### [app.py](app.py)
Application factory that initializes the Flask app, database, and portfolio manager.
- Creates Flask application instance
- Loads configuration from environment
- Initializes SQLAlchemy database connection
- Registers API and view blueprints
- Sets up PortfolioManager with data provider

#### [portfolio_manager.py](portfolio_manager.py)
Core business logic for portfolio operations.
- **Trade Execution**: Records buy/sell transactions with validation
- **Portfolio Calculations**: Computes positions, cash balance, total value, and weights
- **Performance Metrics**: Calculates return, volatility, Sharpe ratio, max drawdown, win rate
- **Price Management**: Smart backfilling of historical data (only fetches missing ranges)
- **Snapshot System**: Records portfolio state for timeline analysis
- **Quota Management**: Cooldown protection and rate limiting

#### [models.py](models.py)
SQLAlchemy ORM models defining database schema.
- **Price**: Historical OHLCV data with deduplication (event_id hashing)
- **Trade**: Buy/sell transactions with before/after state tracking
- **Snapshot**: Portfolio state at specific timestamps
- **PortfolioConfig**: System configuration (initial_cash, start_date)

#### [config.py](config.py)
Configuration management for different environments.
- Environment-specific settings (development, production)
- Database connection strings
- Alpha Vantage API configuration
- Retry logic and cooldown parameters

### Routes

#### [routes/api.py](routes/api.py)
REST API endpoints for all portfolio operations.
- `GET /api/portfolio` - Current holdings and statistics
- `POST /api/refresh` - Manual data refresh (calls Alpha Vantage)
- `POST /api/trade` - Execute buy/sell trade
- `GET /api/timeline` - Portfolio value over time with S&P 500 benchmark
- `GET /api/performance` - Performance metrics
- `GET /api/stocks` - Historical stock prices for all holdings
- `GET /api/provider-status` - API quota and market status
- `POST /api/snapshot` - Manual portfolio snapshot

#### [routes/views.py](routes/views.py)
HTML page routing.
- `GET /` - Main dashboard page
- `GET /health` - Health check endpoint

### Data Providers

#### [providers/\_\_init\_\_.py](providers/__init__.py)
Provider factory pattern for data source abstraction.
- `create_provider()` - Initializes Alpha Vantage provider with configuration

#### [providers/alphavantage_provider.py](providers/alphavantage_provider.py)
Alpha Vantage API integration with enterprise-grade reliability.
- **Rate Limiting**: Free tier (5 calls/min) and Paid tier (75 calls/min) support
- **Quota Tracking**: Daily and per-minute call tracking with automatic resets
- **Retry Logic**: Exponential backoff for transient failures (3 attempts max)
- **Data Validation**: Ensures prices > 0, volumes ≥ 0, no future dates
- **Smart Delays**: 12s (free) or 1s (paid) between calls to prevent rate limit hits
- **Market Status**: Free endpoint to check if US market is open

### Frontend

#### [templates/dashboard.html](templates/dashboard.html)
Main dashboard UI structure.
- **Header**: Title, last updated timestamp, refresh button, theme toggle, quota status
- **KPI Cards**: Total return, win rate, volatility, max drawdown, total trades
- **Portfolio Overview**: Total value, cash, stock value with donut chart
- **Holdings Table**: Ticker, shares, price, value, weight for each position
- **Charts**: Portfolio value timeline and stock prices (90-day history)
- **Trade Modal**: Buy/sell form with exchange selection and date picker
- **Floating Action Buttons**: Trade execution ($) and admin reset (🗑️)

#### [static/dashboard.js](static/dashboard.js)
Frontend logic powering the dashboard.
- **Data Fetching**: Parallel API calls with Promise.all() for fast loading
- **Chart Rendering**: Plotly.js integration with responsive layouts
- **Chart Modes**: Toggle between absolute ($) and percentage (%) views
- **Benchmark Comparison**: S&P 500 overlay with unified hover information
- **Trade Execution**: Form validation and modal management
- **Theme Switching**: Dark/light mode with localStorage persistence
- **Error Handling**: Loading states and user-friendly error messages

#### [static/dashboard.css](static/dashboard.css)
Premium styling with dark theme and glassmorphism effects.
- **Dark Theme**: Navy/blue palette with gold accents (#d4af37)
- **Light Theme**: White background with navy headers
- **Glassmorphism**: Backdrop blur effects on cards
- **Typography**: Playfair Display (headings), Inter (body), JetBrains Mono (data)
- **Responsive Design**: Mobile-friendly breakpoints (768px, 480px)
- **Animations**: Smooth transitions, shimmer effects, hover states

## 🔌 API Endpoints Reference

| Method | Endpoint | Purpose | Key Parameters |
|--------|----------|---------|----------------|
| `GET` | `/api/portfolio` | Current holdings and portfolio stats | None |
| `POST` | `/api/refresh` | Manual data refresh (calls Alpha Vantage) | None |
| `POST` | `/api/trade` | Execute buy/sell trade | `ticker`, `action`, `quantity`, `price`, `date` (optional) |
| `GET` | `/api/timeline` | Portfolio value over time | `days` (default: 90), `include_benchmark` (bool) |
| `GET` | `/api/performance` | Performance metrics | None |
| `GET` | `/api/stocks` | Historical prices for all stocks | `days` (default: 90) |
| `GET` | `/api/trades` | Recent trade history | `limit` (default: 20) |
| `GET` | `/api/provider-status` | API quota and market status | None |
| `POST` | `/api/snapshot` | Manual portfolio snapshot | `note` (optional) |
| `POST` | `/api/reset_db` | Reset entire database (admin) | None |

### Example: Execute a Trade

**Request:**
```bash
curl -X POST http://localhost:5012/api/trade \
  -H "Content-Type: application/json" \
  -d '{
    "ticker": "AAPL",
    "action": "BUY",
    "quantity": 10,
    "price": 150.00,
    "date": "2024-01-15",
    "note": "Initial purchase"
  }'
```

**Response:**
```json
{
  "success": true,
  "trade": {
    "id": 1,
    "ticker": "AAPL",
    "action": "BUY",
    "quantity": 10,
    "price": 150.00,
    "total_cost": 1500.00,
    "timestamp": "2024-01-15T00:00:00Z",
    "position_after": 10,
    "cash_after": 98500.00
  },
  "message": "Trade executed successfully"
}
```

### Example: Get Portfolio Timeline with Benchmark

**Request:**
```bash
curl "http://localhost:5012/api/timeline?days=90&include_benchmark=true"
```

**Response:**
```json
{
  "dates": ["2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z", ...],
  "values": [100000.00, 100250.00, ...],
  "portfolio_pct": [0.0, 0.25, ...],
  "benchmark_values": [450.00, 451.50, ...],
  "benchmark_pct": [0.0, 0.33, ...],
  "benchmark_ticker": "SPY"
}
```

## 🗄️ Database Schema

### `prices` Table
Historical OHLCV (Open, High, Low, Close, Volume) price data.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `event_id` | VARCHAR(16) | SHA256 hash for deduplication (unique) |
| `ticker` | VARCHAR(10) | Stock symbol |
| `timestamp` | DATETIME | Market close date (UTC) |
| `open` | NUMERIC(10,2) | Opening price |
| `high` | NUMERIC(10,2) | Daily high |
| `low` | NUMERIC(10,2) | Daily low |
| `close` | NUMERIC(10,2) | Closing price (required) |
| `volume` | BIGINT | Trading volume |
| `kind` | VARCHAR(20) | Data source: HISTORY, SNAPSHOT, TRADE |
| `price_source` | VARCHAR(50) | Provider: "AlphaVantage (FREE/PAID)" |
| `out_of_order` | BOOLEAN | Flag for chronological issues |
| `note` | TEXT | Audit notes |
| `created_at` | DATETIME | Record creation timestamp |

**Indexes**: `(ticker, timestamp)`, `(event_id)`

### `trades` Table
Buy and sell transactions with audit trail.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `event_id` | VARCHAR(16) | SHA256 hash (unique) |
| `timestamp` | DATETIME | Trade execution time |
| `ticker` | VARCHAR(10) | Stock symbol |
| `action` | VARCHAR(10) | BUY or SELL |
| `quantity` | INTEGER | Number of shares |
| `price` | NUMERIC(10,2) | Price per share |
| `total_cost` | NUMERIC(12,2) | Total transaction amount |
| `position_before` | INTEGER | Shares held before trade |
| `position_after` | INTEGER | Shares held after trade |
| `cash_before` | NUMERIC(12,2) | Cash balance before trade |
| `cash_after` | NUMERIC(12,2) | Cash balance after trade |
| `note` | TEXT | Optional trade note |
| `created_at` | DATETIME | Record creation timestamp |

**Indexes**: `(timestamp)`, `(ticker)`

### `snapshots` Table
Portfolio state at specific points in time.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `event_id` | VARCHAR(16) | SHA256 hash (unique) |
| `timestamp` | DATETIME | Snapshot time |
| `ticker` | VARCHAR(10) | Stock symbol |
| `position` | INTEGER | Shares held |
| `cash_balance` | NUMERIC(12,2) | Cash balance |
| `portfolio_value` | NUMERIC(12,2) | Total portfolio value |
| `note` | TEXT | Optional snapshot note |
| `created_at` | DATETIME | Record creation timestamp |

**Indexes**: `(timestamp)`, `(ticker, timestamp)`

### `portfolio_config` Table
System configuration key-value store.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `key` | VARCHAR(50) | Configuration key (unique) |
| `value` | TEXT | Configuration value (JSON-serializable) |
| `updated_at` | DATETIME | Last update timestamp |

**Stored Keys**: `initial_cash`, `start_date`

## 📡 Data Provider System

### Alpha Vantage Integration

**Provider**: [Alpha Vantage](https://www.alphavantage.co/) - Real-time and historical stock market data API

**Tier Comparison**:

| Feature | Free Tier | Paid Tier ($49.99/mo) |
|---------|-----------|------------------------|
| API Calls/Minute | 5 | 75 |
| API Calls/Day | 500 | Unlimited |
| Rate Limit Delay | 12 seconds | 1 second |
| Use Case | Development, Small portfolios | Production, Active trading |

**API Endpoints Used**:
- `TIME_SERIES_DAILY` - Historical OHLCV data (1 call per stock)
- `GLOBAL_QUOTE` - Current stock price (1 call per stock)
- `MARKET_STATUS` - US market open/closed (free, no quota)

### Rate Limiting Strategy

**Quota Tracking**:
- Tracks calls per minute (sliding 60-second window)
- Tracks daily calls (resets at midnight UTC)
- Raises `AlphaVantageQuotaError` if limits exceeded

**Smart Delays**:
```python
# Free Tier: 12-second delay between calls
# Ensures: 60s / 12s = 5 calls/min (within 5 req/min limit)

# Paid Tier: 1-second delay between calls
# Ensures: 60s / 1s = 60 calls/min (well under 75 req/min limit)
```

**Retry Logic**:
- Exponential backoff: `delay * 2^attempt`
- Max retries: 3 attempts (configurable)
- Non-retryable errors: Quota exceeded, invalid API key

### Price Data Validation

All fetched data undergoes strict validation:
- ✅ Prices must be > 0
- ✅ Volumes must be ≥ 0
- ✅ Dates cannot be in the future
- ✅ Required columns (close, timestamp) must exist
- ❌ Invalid data rejected with detailed error messages

### Historical Data Backfilling

**Smart Backfilling Logic**:
1. Query database for existing price range per stock
2. Determine backfill needs:
   - **No data**: Fetch 365 days (1 year)
   - **Stale data** (>1 day old): Update to today
   - **Insufficient history**: Extend backward to 1 year
3. Call Alpha Vantage API only for missing date ranges
4. Deduplicate using SHA256 event_id (prevents duplicate inserts)
5. Store validated prices in database
6. Take snapshot of portfolio state

**Example Flow**:
```
User clicks "Refresh" button
  ↓
Check cooldown (60 seconds since last refresh)
  ↓
For each tracked stock (AAPL, GOOGL, MSFT, SPY):
  - DB has AAPL prices up to 2024-01-20
  - Today is 2024-01-22
  - Fetch AAPL prices from 2024-01-21 to 2024-01-22 (2 days)
  ↓
Store new prices in database
  ↓
Take snapshot (calculate portfolio value from DB prices)
  ↓
Return success response
```

**Benefits**:
- Minimizes API calls (only fetches what's needed)
- Idempotent (can safely re-run without duplicates)
- Cumulative (can extend history at any time)
- Efficient (no wasted API quota)

## 🎨 Frontend Features

### Dashboard Layout

**Header Section**:
- **Title**: "St. George Capital Portfolio" with shimmer animation
- **Last Updated**: Timestamp of most recent data refresh
- **Refresh Button**: Manual data update with cooldown indicator
- **Theme Toggle**: Switch between dark/light modes
- **Quota Status**: Remaining API calls or "Paid tier (unlimited)"

**KPI Cards** (Color-coded metrics):
- **Total Return**: Portfolio gain/loss percentage (green/red)
- **Win Rate**: % of profitable trades
- **Volatility**: Annualized standard deviation of returns
- **Max Drawdown**: Largest peak-to-trough decline
- **Total Trades**: Number of executed trades

**Portfolio Overview**:
- **Total Value**: Portfolio value in large font
- **Cash Balance**: Available cash for trading
- **Stock Value**: Total value of all holdings
- **Donut Chart**: Visual breakdown of cash vs stocks

**Holdings Table**:
- Lists all current positions with columns:
  - Ticker symbol
  - Number of shares
  - Current price
  - Total value
  - Portfolio weight (%)

**Interactive Charts**:

1. **Portfolio Value Over Time**:
   - 90-day historical timeline
   - Toggle modes: Absolute ($) or Percentage (%)
   - Optional S&P 500 benchmark overlay (dotted amber line)
   - Unified hover tooltips with date and values
   - Reference lines: 0% baseline (percentage mode) or initial value (absolute mode)

2. **Stock Prices Chart**:
   - Individual stock performance (90-day history)
   - Toggle modes: Absolute ($) or Percentage (%)
   - Multi-line chart with distinct colors per stock
   - Hover tooltips showing price and date

**Trade Modal**:
- **Exchange Selection**: US (NYSE/NASDAQ), Canada (TSX/TSX-V), UK (LSE)
- **Ticker Input**: Stock symbol (auto-validated)
- **Quantity Input**: Number of shares (integer > 0)
- **Price Input**: Price per share (numeric > 0)
- **Date Picker**: Optional historical trade date
- **Note Field**: Optional transaction note
- **Action Buttons**: BUY (green) or SELL (red)

**Floating Action Buttons**:
- **$ Button** (green): Opens trade execution modal
- **🗑️ Button** (red): Admin database reset (hidden by default)

### Theme System

**Dark Mode** (Default):
- Background: Navy blue (#0a1929, #1a2332)
- Accent: Gold (#d4af37)
- Text: White (#ffffff) and light gray (#b0b0b0)
- Cards: Semi-transparent with backdrop blur (glassmorphism)
- Charts: Blue/cyan color scheme

**Light Mode**:
- Background: White (#ffffff)
- Accent: Gold (#d4af37)
- Text: Navy (#1a2332) and dark gray (#505050)
- Cards: White with subtle shadows
- Charts: Darker color scheme for visibility

**Persistence**: Theme preference stored in `localStorage`

### Chart Interactions

**Mode Toggling**:
- Click "$ (Absolute)" to view dollar values
- Click "% (Percentage)" to view percentage changes
- Mode applies to both portfolio and stock charts
- Cached data ensures instant toggling (no API calls)

**Benchmark Comparison**:
- Checkbox to show/hide S&P 500 (SPY) performance
- Normalized to start at same point as portfolio
- Dotted amber line distinguishes benchmark from portfolio
- Hover shows both portfolio and benchmark values simultaneously

**Responsive Design**:
- Charts resize automatically with window
- Mobile-friendly layouts below 768px width
- Stacked cards on small screens (480px breakpoint)

## 🚀 Setup & Installation

### Prerequisites

- **Python 3.11+** (Python 3.9+ may work but 3.11 recommended)
- **Alpha Vantage API Key** - Get free key at [alphavantage.co/support/#api-key](https://www.alphavantage.co/support/#api-key)
- **Virtual Environment** - For dependency isolation

### Installation Steps

1. **Clone the repository**:
   ```bash
   git clone https://github.com/yourusername/StGeorgeCapitalPortfolio.git
   cd StGeorgeCapitalPortfolio
   ```

2. **Create and activate virtual environment**:

   **Windows (PowerShell)**:
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

   **Linux/Mac**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**:

   Create a `.env` file in the project root:
   ```env
   # Required
   ALPHA_VANTAGE_API_KEY=your_api_key_here

   # Optional
   ALPHA_VANTAGE_PAID_TIER=false
   DATABASE_URL=sqlite:///portfolio.db
   FLASK_ENV=development
   SECRET_KEY=your-secret-key-here
   MANUAL_REFRESH_COOLDOWN=60
   ```

5. **Run the application**:

   **Windows (PowerShell)**:
   ```powershell
   $env:FLASK_APP="app.py"
   python -m flask run --port 5012
   ```

   **Linux/Mac**:
   ```bash
   export FLASK_APP=app.py
   python -m flask run --port 5012
   ```

6. **Access the dashboard**:
   - Open browser to [http://localhost:5012](http://localhost:5012)
   - Click "Refresh" button to fetch initial price data
   - Execute your first trade using the "$" button

### Environment Variables

| Variable | Description | Required | Default | Example |
|----------|-------------|----------|---------|---------|
| `ALPHA_VANTAGE_API_KEY` | Alpha Vantage API key | ✅ Yes | None | `ABC123XYZ456` |
| `ALPHA_VANTAGE_PAID_TIER` | Use paid tier rate limits | ❌ No | `false` | `true` |
| `DATABASE_URL` | Database connection string | ❌ No | `sqlite:///portfolio.db` | `postgresql://user:pass@host/db` |
| `FLASK_ENV` | Flask environment mode | ❌ No | `development` | `production` |
| `SECRET_KEY` | Flask session secret key | ❌ No | Generated | `your-secret-key` |
| `MANUAL_REFRESH_COOLDOWN` | Seconds between refreshes | ❌ No | `60` | `120` |
| `PORT` | Server port number | ❌ No | `5012` | `8080` |

## 📖 Usage Guide

### First-Time Setup

1. **Initial Data Fetch**:
   - Access dashboard at [http://localhost:5012](http://localhost:5012)
   - Click the "🔄 Refresh" button in the header
   - Wait for data backfill (fetches 90-365 days of historical prices)
   - Dashboard will populate with charts and metrics

2. **Execute Your First Trade**:
   - Click the green "$" floating action button (bottom right)
   - Select exchange: US (NYSE/NASDAQ), Canada (TSX/TSX-V), or UK (LSE)
   - Enter ticker symbol (e.g., `AAPL` for Apple)
   - Enter quantity (e.g., `10` shares)
   - Enter price (e.g., `150.00` per share)
   - Optionally set a historical date
   - Click "BUY" button
   - Trade appears in "Recent Activity" section

3. **View Performance**:
   - KPI cards at top show key metrics
   - Portfolio value chart shows 90-day timeline
   - Enable "Show S&P 500" checkbox to compare against benchmark
   - Toggle between "$" (absolute) and "%" (percentage) views

### Trading

**Buy Stocks**:
1. Click green "$" button
2. Select exchange from dropdown
3. Enter ticker, quantity, price
4. Optionally set historical date
5. Click "BUY"
6. Confirm sufficient cash available

**Sell Stocks**:
1. Click green "$" button
2. Enter ticker, quantity, price
3. Click "SELL"
4. Confirm sufficient shares owned

**Validation Rules**:
- ✅ Cannot sell more shares than owned
- ✅ Cannot buy with insufficient cash
- ✅ Price must be > 0
- ✅ Quantity must be integer > 0
- ✅ Cannot sell before first purchase (historical trades)

### Refreshing Data

**Manual Refresh** (Recommended):
- Click "🔄 Refresh" button in header
- Fetches latest prices for all tracked stocks
- Backfills missing historical data (smart delta updates)
- Also fetches SPY data for benchmark comparison
- Cooldown: 60 seconds between refreshes (prevents API quota exhaustion)

**What Gets Updated**:
- Latest closing prices for all holdings
- Historical data gaps filled (if any)
- S&P 500 benchmark data (SPY)
- Portfolio value snapshot taken
- Charts and metrics recalculated

### Viewing Performance

**KPI Metrics**:
- **Total Return**: Overall portfolio gain/loss since inception
- **Win Rate**: Percentage of buy trades currently profitable
- **Volatility**: Annualized standard deviation (252 trading days)
- **Max Drawdown**: Worst peak-to-trough decline
- **Total Trades**: Number of executed transactions

**Portfolio Value Chart**:
- Shows 90-day portfolio value timeline
- **Absolute Mode ($)**: Dollar values with initial value reference line
- **Percentage Mode (%)**: Percentage change from start with 0% baseline
- **Benchmark Overlay**: Dotted amber line shows S&P 500 performance
- **Hover Tooltip**: Displays date, portfolio value, benchmark value

**Stock Prices Chart**:
- Shows individual stock performance (90 days)
- Multi-line chart with distinct colors per holding
- Toggle between $ (absolute prices) and % (percentage change from start)
- Hover to see precise values and dates

**Holdings Table**:
- Current positions with shares, price, value, weight
- Weight shows each holding as % of total portfolio
- Sorted by ticker alphabetically

## ⚙️ Configuration Details

### Default Settings

| Setting | Value | Description |
|---------|-------|-------------|
| `INITIAL_CASH` | $100,000 | Starting portfolio cash balance |
| `MAX_RETRIES` | 3 | API retry attempts for transient failures |
| `RETRY_DELAY` | 5 seconds | Base delay between retry attempts |
| `MANUAL_REFRESH_COOLDOWN` | 60 seconds | Minimum time between refresh clicks |

### Database Configuration

**Development**:
- SQLite database: `portfolio.db` (created automatically)
- File-based, no setup required
- Suitable for single-user deployments

**Production**:
- PostgreSQL recommended (set `DATABASE_URL` environment variable)
- Example: `postgresql://user:password@localhost:5432/portfolio`
- Heroku auto-configures with `postgres://` (auto-converted to `postgresql://`)

**Connection Pooling**:
```python
SQLALCHEMY_ENGINE_OPTIONS = {
    'pool_pre_ping': True,    # Test connections before using
    'pool_recycle': 300       # Recycle connections every 5 minutes
}
```

### Alpha Vantage API Configuration

**Free Tier** (Default):
- Rate limits: 5 calls/min, 500 calls/day
- Delay between calls: 12 seconds
- Cost: Free
- Best for: Development, small portfolios, infrequent refreshes

**Paid Tier** ($49.99/month):
- Rate limits: 75 calls/min, unlimited daily
- Delay between calls: 1 second
- Cost: $49.99/month (billed by Alpha Vantage)
- Best for: Production, active trading, large portfolios
- Activation: Set `ALPHA_VANTAGE_PAID_TIER=true` in environment

**Quota Management**:
- Dashboard header shows remaining daily calls (free tier)
- Paid tier shows "Paid tier (unlimited)"
- Quota resets daily at midnight UTC
- Per-minute quota resets in rolling 60-second window

## 🔧 Technical Implementation Details

### Price Data Management

**Deduplication Strategy**:
- Each price record generates SHA256 `event_id` hash
- Hash includes: `ticker | timestamp | close | note | kind`
- Unique constraint prevents duplicate inserts
- Idempotent backfilling (safe to re-run)

**Smart Backfilling Algorithm**:
```python
1. Query DB for existing price range per ticker
2. Determine missing date ranges:
   - Case A: No data → Fetch 1 year (365 days)
   - Case B: Stale (>1 day old) → Update to today
   - Case C: Insufficient history → Extend backward to 1 year
3. Call Alpha Vantage API ONLY for missing ranges
4. Validate each price record (price > 0, volume ≥ 0, no future dates)
5. Generate event_id and check for existing record
6. Insert if new, skip if duplicate
```

**Data Validation**:
```python
✅ Price > 0
✅ Volume ≥ 0
✅ Date not in future
✅ Required columns present (close, timestamp)
❌ Invalid → AlphaVantageError with detailed message
```

### Portfolio Calculations

**Current Positions**:
```python
# Calculated from all trades (cumulative buy/sell)
positions = {}
for trade in all_trades:
    if trade.action == 'BUY':
        positions[ticker] += quantity
    elif trade.action == 'SELL':
        positions[ticker] -= quantity
```

**Cash Balance**:
```python
# Tracked with before/after state in each trade
cash = initial_cash
for trade in all_trades:
    if trade.action == 'BUY':
        cash -= (quantity * price)
    elif trade.action == 'SELL':
        cash += (quantity * price)
```

**Portfolio Value**:
```python
stock_value = sum(shares * latest_price for ticker, shares in positions)
total_value = cash + stock_value
```

**Position Weights**:
```python
weight = (shares * price) / total_value * 100
```

### Performance Metrics

**Total Return**:
```python
total_return = ((current_value - initial_cash) / initial_cash) * 100
```

**Volatility** (Annualized Standard Deviation):
```python
daily_returns = portfolio_values.pct_change()
volatility = daily_returns.std() * np.sqrt(252) * 100  # 252 trading days
```

**Sharpe Ratio** (Risk-Adjusted Return):
```python
risk_free_rate = 5.0  # 5% annually (configurable)
daily_rf_rate = risk_free_rate / 252 / 100
excess_returns = daily_returns - daily_rf_rate
sharpe_ratio = (excess_returns.mean() / excess_returns.std()) * np.sqrt(252)
```

**Max Drawdown** (Largest Peak-to-Trough Decline):
```python
cumulative_max = portfolio_values.cummax()
drawdowns = (portfolio_values - cumulative_max) / cumulative_max * 100
max_drawdown = drawdowns.min()
```

**Win Rate** (% of Profitable Trades):
```python
for buy_trade in buy_trades:
    current_price = get_latest_price(ticker)
    if current_price > buy_trade.price:
        winning_trades += 1
win_rate = (winning_trades / total_buy_trades) * 100
```

### S&P 500 Benchmark

**Implementation**:
- Uses **SPY** (SPDR S&P 500 ETF Trust) as proxy for S&P 500 index
- Fetched automatically during manual refresh
- Stored in same `prices` table as other stocks

**Calculation**:
```python
# Align dates with portfolio timeline
spy_aligned = spy_prices.reindex(portfolio_dates, method='ffill')

# Calculate percentage change from start
spy_start = spy_aligned.iloc[0]
spy_pct = ((spy_aligned - spy_start) / spy_start) * 100

# Chart shows portfolio_pct vs spy_pct (both starting at 0%)
```

**Chart Display**:
- Portfolio: Solid blue line
- S&P 500: Dotted amber line (distinct style)
- Unified hover tooltip shows both values
- Toggle on/off with "Show S&P 500" checkbox

### Rate Limiting Strategy

**Free Tier Protection**:
```python
rate_limit_delay = 12  # seconds
# Ensures: 60s / 12s = 5 calls/min (within 5 req/min limit)
```

**Paid Tier Optimization**:
```python
rate_limit_delay = 1  # second
# Ensures: 60s / 1s = 60 calls/min (under 75 req/min limit, safe buffer)
```

**Quota Tracking**:
```python
class AlphaVantageProvider:
    def __init__(self):
        self.daily_calls = 0
        self.daily_limit = 500  # or "unlimited" for paid
        self.minute_calls = []  # List of timestamps
        self.minute_limit = 5  # or 75 for paid

    def _check_quota(self):
        # Remove calls older than 1 minute
        now = datetime.now()
        self.minute_calls = [t for t in self.minute_calls
                             if (now - t).seconds < 60]

        # Check limits
        if len(self.minute_calls) >= self.minute_limit:
            raise AlphaVantageQuotaError("Per-minute limit exceeded")
        if self.daily_calls >= self.daily_limit:
            raise AlphaVantageQuotaError("Daily limit exceeded")
```

**Exponential Backoff**:
```python
for attempt in range(max_retries):
    try:
        return make_api_call()
    except TransientError:
        if attempt < max_retries - 1:
            delay = retry_delay * (2 ** attempt)
            time.sleep(delay)
        else:
            raise
```

## 🐛 Troubleshooting

### Common Issues

**"Quota exceeded" Error**:
- **Cause**: Hit Alpha Vantage rate limit (5 calls/min or 500 calls/day on free tier)
- **Solution**: Wait 60 seconds for cooldown, then try again
- **Prevention**: Avoid rapid refresh clicks, consider paid tier for production

**Missing Price Data**:
- **Cause**: Database empty or stale (no historical data)
- **Solution**: Click "🔄 Refresh" button to backfill prices
- **Note**: First refresh may take longer (fetching 90-365 days of data)

**"Insufficient shares to sell" Error**:
- **Cause**: Trying to sell more shares than currently owned
- **Solution**: Check "Current Holdings" table for actual position
- **Note**: Cannot sell shares not yet purchased (for historical trades)

**"Insufficient cash" Error**:
- **Cause**: Buy order cost exceeds available cash balance
- **Solution**: Check "Portfolio Overview" for current cash, reduce quantity or price

**Port Already in Use**:
- **Cause**: Another application using port 5012
- **Solution**: Change port with `--port 8080` flag or kill existing process
- **Windows**: `netstat -ano | findstr :5012` then `taskkill /PID <pid> /F`
- **Linux/Mac**: `lsof -ti:5012 | xargs kill -9`

**ModuleNotFoundError**:
- **Cause**: Dependencies not installed or wrong virtual environment
- **Solution**:
  ```bash
  # Activate virtual environment
  source venv/bin/activate  # Linux/Mac
  .\venv\Scripts\Activate.ps1  # Windows

  # Reinstall dependencies
  pip install -r requirements.txt
  ```

**Charts Not Loading**:
- **Cause**: JavaScript error or Plotly.js not loaded
- **Solution**: Check browser console (F12), ensure internet connection for CDN
- **Fallback**: Download Plotly.js locally and update script src in dashboard.html

**"Invalid API Key" Error**:
- **Cause**: Missing or incorrect `ALPHA_VANTAGE_API_KEY` environment variable
- **Solution**: Verify `.env` file contains valid API key from Alpha Vantage
- **Get Key**: [alphavantage.co/support/#api-key](https://www.alphavantage.co/support/#api-key)

### API Quota Management

**Free Tier Limits**:
- **Per-Minute**: 5 API calls
- **Daily**: 500 API calls
- **Reset**: Daily quota resets at midnight UTC

**Tracking Quota Usage**:
- Dashboard header shows: "Quota: XXX/500 remaining"
- Provider status endpoint: `GET /api/provider-status`

**Best Practices**:
- Use manual refresh sparingly (not automatic polling)
- Leverage 60-second cooldown to prevent rapid refreshes
- Consider paid tier ($49.99/mo) for:
  - Production deployments
  - Large portfolios (>10 stocks)
  - Frequent data updates
  - Active trading strategies

**Paid Tier Benefits**:
- 75 calls/minute (15x faster)
- Unlimited daily calls
- 1-second delay between calls (vs 12 seconds)
- Set `ALPHA_VANTAGE_PAID_TIER=true` to activate

## 🏗️ Development

### Project Structure

```
StGeorgeCapitalPortfolio/
├── app.py                          # Application entry point (Flask factory)
├── wsgi.py                         # Production WSGI entry point
├── portfolio_manager.py            # Core business logic
├── models.py                       # SQLAlchemy database models
├── config.py                       # Configuration management
├── requirements.txt                # Python dependencies
├── .env                            # Environment variables (gitignored)
├── .gitignore                      # Git ignore rules
├── README.md                       # This file
├── routes/
│   ├── __init__.py
│   ├── api.py                      # REST API endpoints
│   └── views.py                    # HTML routes
├── providers/
│   ├── __init__.py                 # Provider factory
│   └── alphavantage_provider.py    # Alpha Vantage integration
├── templates/
│   └── dashboard.html              # Main dashboard UI
├── static/
│   ├── dashboard.js                # Frontend logic
│   └── dashboard.css               # Styling
└── portfolio.db                    # SQLite database (gitignored)
```

### Adding New Features

**Add a Database Model**:
1. Define model in [models.py](models.py) inheriting from `db.Model`
2. Add columns, constraints, indexes
3. Run migration (database recreated on restart in dev mode)

**Add an API Endpoint**:
1. Add route function in [routes/api.py](routes/api.py)
2. Implement business logic in [portfolio_manager.py](portfolio_manager.py)
3. Return JSON response with `jsonify()`
4. Test with curl or Postman

**Add a UI Component**:
1. Update HTML structure in [templates/dashboard.html](templates/dashboard.html)
2. Add JavaScript logic in [static/dashboard.js](static/dashboard.js)
3. Style with CSS in [static/dashboard.css](static/dashboard.css)
4. Test responsiveness at different screen sizes

**Add a Data Provider**:
1. Create new provider class in `providers/` folder
2. Implement required methods: `get_historical_prices()`, `get_current_prices()`
3. Update `create_provider()` factory in [providers/\_\_init\_\_.py](providers/__init__.py)
4. Add provider selection logic

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-cov

# Run all tests
pytest

# Run with coverage report
pytest --cov=. --cov-report=html

# Open coverage report
open htmlcov/index.html
```

### Code Style

**Python**:
- PEP 8 style guide
- Type hints for function signatures
- Docstrings for modules, classes, and public methods

**JavaScript**:
- ES6+ syntax
- Consistent indentation (2 spaces)
- Descriptive variable names

**CSS**:
- BEM naming convention (Block__Element--Modifier)
- CSS custom properties (variables) for theming
- Mobile-first responsive design

## 🚀 Deployment

### Heroku Deployment

1. **Create Heroku app**:
   ```bash
   heroku create your-portfolio-app
   ```

2. **Set environment variables**:
   ```bash
   heroku config:set ALPHA_VANTAGE_API_KEY=your_key_here
   heroku config:set ALPHA_VANTAGE_PAID_TIER=false
   heroku config:set FLASK_ENV=production
   heroku config:set SECRET_KEY=$(openssl rand -hex 32)
   ```

3. **Add PostgreSQL addon**:
   ```bash
   heroku addons:create heroku-postgresql:mini
   ```

4. **Deploy**:
   ```bash
   git push heroku main
   ```

5. **Open app**:
   ```bash
   heroku open
   ```

### Docker Deployment (Future Support)

```dockerfile
# Dockerfile (example - not yet implemented)
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5012", "wsgi:app"]
```

### Production Considerations

**Security**:
- Use strong `SECRET_KEY` (generate with `openssl rand -hex 32`)
- Enable HTTPS (Heroku provides automatic SSL)
- Set `FLASK_ENV=production` to disable debug mode
- Consider adding authentication for multi-user deployments

**Performance**:
- Use PostgreSQL instead of SQLite for production
- Enable database connection pooling
- Use WSGI server (Gunicorn, uWSGI) instead of Flask dev server
- Consider Redis for caching API responses

**Monitoring**:
- Set up error logging (Sentry, Rollbar)
- Monitor API quota usage
- Track response times and errors
- Set up health check endpoint (`/health`)

## 🤝 Contributing

Contributions are welcome! Please follow these guidelines:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature-name`
3. Make your changes with clear commit messages
4. Add tests for new features
5. Ensure all tests pass: `pytest`
6. Submit a pull request with detailed description

**Contribution Ideas**:
- Add more data providers (Yahoo Finance, IEX Cloud, Finnhub)
- Implement user authentication and multi-portfolio support
- Add dividend tracking
- Export portfolio to CSV/Excel
- Real-time WebSocket price updates
- Tax reporting and cost basis tracking
- Advanced charting (candlestick, Bollinger Bands, RSI)
- Mobile app (React Native, Flutter)

## 📄 License

This project is licensed under the MIT License. See [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **[Alpha Vantage](https://www.alphavantage.co/)** - Reliable market data API
- **[Plotly.js](https://plotly.com/javascript/)** - Interactive charting library
- **[Flask](https://flask.palletsprojects.com/)** - Lightweight Python web framework
- **[SQLAlchemy](https://www.sqlalchemy.org/)** - Powerful ORM for database management
- **Google Fonts** - Playfair Display, Inter, JetBrains Mono typography

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/StGeorgeCapitalPortfolio/issues)
- **Email**: your.email@example.com
- **Documentation**: This README

---

**Built with ❤️ by St. George Capital Team**
