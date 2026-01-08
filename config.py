# config.py
"""
Configuration settings for the Flask application.
Handles database connections, secret keys, and price provider selection.
"""

import os
from datetime import timedelta


class Config:
    """Base configuration"""

    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'

    # Database settings
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///portfolio.db'

    # Fix for Heroku/Railway postgres:// vs postgresql://
    if SQLALCHEMY_DATABASE_URI and SQLALCHEMY_DATABASE_URI.startswith('postgres://'):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace('postgres://', 'postgresql://', 1)

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'pool_size': 5,
        'max_overflow': 10,
        'pool_timeout': 30,
    }

    # Portfolio settings
    PORTFOLIO_STOCKS = ['NVDA', 'MSFT', 'AAPL', 'JPM', 'UNH']
    INITIAL_CASH = 100000
    SHARES_PER_TRADE = 100

    # Scheduler settings (all disabled for manual mode)
    SCHEDULER_API_ENABLED = False
    BACKFILL_INTERVAL_HOURS = None  # Disabled
    SNAPSHOT_INTERVAL_HOURS = None  # Disabled

    # ========================================
    # PRICE PROVIDER CONFIGURATION
    # ========================================

    # Provider selection:
    # - 'auto': Use Alpha Vantage if ALPHA_VANTAGE_API_KEY exists, else yfinance
    # - 'yfinance': Force yfinance (good for local dev)
    # - 'alphavantage': Force Alpha Vantage (good for production)
    PRICE_PROVIDER = os.environ.get('PRICE_PROVIDER', 'auto')

    # yfinance settings (used when yfinance is selected)
    YFINANCE_MAX_RETRIES = 3
    YFINANCE_RETRY_DELAY = 5  # seconds
    YFINANCE_REQUEST_DELAY = 0.5  # seconds between requests
    YFINANCE_BACKFILL_DAYS = 7  # Default lookback for manual refresh

    # Alpha Vantage settings (used when Alpha Vantage is selected)
    # API key comes from environment variable: ALPHA_VANTAGE_API_KEY
    # Set ALPHA_VANTAGE_PAID_TIER=true if you have paid subscription

    # Manual refresh cooldown (seconds between refresh button clicks)
    MANUAL_REFRESH_COOLDOWN = int(os.environ.get('MANUAL_REFRESH_COOLDOWN', 60))

    # Session settings
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False
    # Force yfinance for local development (works fine locally)
    PRICE_PROVIDER = 'yfinance'


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False
    # Auto-detect provider (will use Alpha Vantage if key exists)
    PRICE_PROVIDER = 'auto'


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    PRICE_PROVIDER = 'yfinance'  # Use yfinance for tests


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}


def get_config():
    """Get configuration based on FLASK_ENV environment variable"""
    env = os.environ.get('FLASK_ENV', 'development')
    return config.get(env, config['default'])