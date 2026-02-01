# St. George Capital Portfolio

A Flask-based portfolio management system for tracking investments with real-time market data from Alpha Vantage.

## Features

- **Portfolio Tracking**: Monitor stock holdings, cash balance, and total portfolio value
- **Trade Execution**: Buy and sell stocks with full audit trail
- **Performance Analytics**: Sharpe ratio, volatility, and S&P 500 benchmark comparison
- **FRED Integration**: Automatic risk-free rate updates for accurate Sharpe ratio
- **Authentication**: Bcrypt-secured admin login for protected operations
- **Live Ticker**: Simulated real-time price movement during market hours
- **Interactive Charts**: 90-day historical charts with Plotly.js
- **Dark/Light Themes**: Premium UI with glassmorphism effects

## Quick Start

### 1. Clone and Install

```bash
git clone https://github.com/gkgeo9/StGeorgeCapitalPortfolio.git
cd StGeorgeCapitalPortfolio
python -m venv venv
source venv/bin/activate  # Windows: .\venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your values:

```env
# Required
ALPHA_VANTAGE_API_KEY=your_key_here

# Required for admin access (trading, refresh, reset)
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=$2b$12$...  # See below for generation

# Optional (for accurate Sharpe ratio)
FRED_API_KEY=your_fred_key_here
```

**Generate password hash:**

```bash
python -c "import bcrypt; print(bcrypt.hashpw(b'YOUR_PASSWORD', bcrypt.gensalt()).decode())"
```

### 3. Run

```bash
python app.py
```

Open http://localhost:5012

## Authentication

Protected endpoints require admin login at `/login`:

- `/api/trade` - Execute trades
- `/api/refresh` - Refresh price data
- `/api/snapshot` - Take portfolio snapshots
- `/api/reset_db` - Reset database
- `/api/provider-status` - View API quota details
- `/api/stats` - View database statistics

## API Endpoints

### Public (No Login Required)

| Endpoint             | Method | Description                |
| -------------------- | ------ | -------------------------- |
| `/api/portfolio`     | GET    | Current holdings and stats |
| `/api/timeline`      | GET    | Portfolio value over time  |
| `/api/performance`   | GET    | Sharpe ratio, volatility   |
| `/api/trades`        | GET    | Recent trade history       |
| `/api/stocks`        | GET    | Historical stock prices    |
| `/api/market-status` | GET    | Market open/closed status  |
| `/health`            | GET    | Health check               |

### Protected (Login Required)

| Endpoint               | Method | Description                 |
| ---------------------- | ------ | --------------------------- |
| `/api/trade`           | POST   | Execute buy/sell            |
| `/api/refresh`         | POST   | Fetch latest prices         |
| `/api/snapshot`        | POST   | Take portfolio snapshot     |
| `/api/reset_db`        | POST   | Reset database              |
| `/api/provider-status` | GET    | API quota and provider info |
| `/api/stats`           | GET    | Database statistics         |

## Project Structure

```
├── app.py                  # Flask application factory
├── portfolio_manager.py    # Core portfolio facade
├── models.py               # SQLAlchemy models (Price, Trade, Snapshot, PortfolioConfig)
├── config.py               # Configuration management
├── auth.py                 # Authentication module
├── extensions.py           # Flask extensions (CSRF, rate limiting)
├── constants.py            # Application constants and limits
├── cron_refresh.py         # Scheduled data refresh script
├── wsgi.py                 # WSGI entry point for gunicorn
├── routes/
│   ├── api.py              # REST API endpoints
│   └── views.py            # HTML routes
├── services/
│   ├── trade_service.py    # Trade execution and position tracking
│   ├── price_service.py    # Price fetching and caching
│   ├── snapshot_service.py # Portfolio snapshot creation
│   └── analytics_service.py # Performance metrics and analytics
├── providers/
│   └── alphavantage_provider.py  # Alpha Vantage API integration
├── templates/
│   ├── dashboard.html      # Main dashboard
│   └── login.html          # Login page
├── static/
│   ├── js/
│   │   ├── dashboard.js    # Frontend logic
│   │   └── admin.js        # Admin-only trade execution
│   └── css/dashboard.css   # Styling
└── tests/                  # Test suite (99 tests)
```

## Running Tests

```bash
pytest tests/ -v
```

## Environment Variables

| Variable                  | Required | Default                | Description                                     |
| ------------------------- | -------- | ---------------------- | ----------------------------------------------- |
| `ALPHA_VANTAGE_API_KEY`   | Yes      | -                      | Alpha Vantage API key                           |
| `ADMIN_USERNAME`          | Yes      | admin                  | Admin login username                            |
| `ADMIN_PASSWORD_HASH`     | Yes      | -                      | Bcrypt password hash                            |
| `DATABASE_URL`            | No       | sqlite:///portfolio.db | Database connection                             |
| `DATABASE_PUBLIC_URL`     | No       | -                      | Public DB URL for Railway cron jobs             |
| `FRED_API_KEY`            | No       | -                      | FRED API for risk-free rate                     |
| `SECRET_KEY`              | Prod     | auto-generated         | Flask session secret                            |
| `FLASK_ENV`               | No       | development            | Environment mode                                |
| `PORT`                    | No       | 5012                   | Server port                                     |
| `ALPHA_VANTAGE_PAID_TIER` | No       | false                  | Enable paid tier rate limits                    |
| `MANUAL_REFRESH_COOLDOWN` | No       | 60                     | Seconds between refreshes                       |
| `FAKE_LIVE_TICKER`        | No       | false                  | Enable simulated live price updates (demo only) |

## Alpha Vantage API Tiers

| Feature             | Free | Paid ($49.99/mo) |
| ------------------- | ---- | ---------------- |
| Calls/minute        | 5    | 75               |
| Calls/day           | 500  | Unlimited        |
| Delay between calls | 12s  | 1s               |

Set `ALPHA_VANTAGE_PAID_TIER=true` in your `.env` for paid tier.

## FRED Integration

The system fetches the 3-Month Treasury Bill rate (DTB3) weekly for accurate Sharpe ratio calculations.

- Get a free key at: https://fred.stlouisfed.org/docs/api/api_key.html
- Without `FRED_API_KEY`, defaults to 4.5% risk-free rate

## Deployment (Railway)

```bash
# Set environment variables
railway variables set ALPHA_VANTAGE_API_KEY=your_key
railway variables set ADMIN_USERNAME=admin
railway variables set ADMIN_PASSWORD_HASH='$2b$12$...'
railway variables set SECRET_KEY=$(openssl rand -hex 32)
railway variables set FLASK_ENV=production

# Add PostgreSQL database
railway add postgresql
```

The app auto-converts `postgres://` to `postgresql://` for compatibility.

## Cron Job Setup

For automatic data refresh, run `cron_refresh.py` on a schedule:

```bash
# Railway cron: */15 * * * *
python cron_refresh.py
```

The cron job:

- Runs full backfill daily at 9 AM UTC
- Updates risk-free rate from FRED weekly (Mondays)
- Quick price updates on other runs
