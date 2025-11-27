# config.py
"""
Configuration settings for the Flask application.
Handles database connections, secret keys, and environment-specific settings.
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

    # yfinance settings
    YFINANCE_MAX_RETRIES = 3
    YFINANCE_RETRY_DELAY = 5  # seconds
    YFINANCE_BACKFILL_DAYS = 7  # Default lookback for manual refresh

    # Session settings
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'


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