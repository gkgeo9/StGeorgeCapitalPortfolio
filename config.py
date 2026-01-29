# config.py
"""
Configuration settings for the Flask application.
"""

import os
from datetime import timedelta
from dotenv import load_dotenv

# Load environment variables before Config class is evaluated
load_dotenv()


class Config:
    """Application configuration."""

    # Flask
    DEBUG = os.environ.get('FLASK_ENV') == 'development'

    # Enforce SECRET_KEY in production
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        if DEBUG:
            SECRET_KEY = 'dev-secret-key-change-in-production'
        else:
            raise RuntimeError("SECRET_KEY environment variable must be set in production")

    # Database (PostgreSQL)
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///portfolio.db')
    # Fix for Heroku/Railway postgres:// vs postgresql://
    if SQLALCHEMY_DATABASE_URI.startswith('postgres://'):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace('postgres://', 'postgresql://', 1)

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }

    # Portfolio settings
    DEFAULT_PORTFOLIO_STOCKS = []  # Stocks are dynamically tracked from trades/prices
    INITIAL_CASH = 100000

    # Alpha Vantage rate limiting
    MAX_RETRIES = 3
    RETRY_DELAY = 5
    MANUAL_REFRESH_COOLDOWN = int(os.environ.get('MANUAL_REFRESH_COOLDOWN', 60))

    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)

    # Authentication
    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
    ADMIN_PASSWORD_HASH = os.environ.get('ADMIN_PASSWORD_HASH')

    # Session security
    SESSION_COOKIE_SECURE = os.environ.get('FLASK_ENV') != 'development'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'


class TestingConfig(Config):
    """Testing configuration with in-memory SQLite."""
    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'


def get_config():
    """Get configuration based on environment."""
    if os.environ.get('TESTING'):
        return TestingConfig
    return Config
