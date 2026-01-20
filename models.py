# models.py
"""
Database models for portfolio tracking system.
Enhanced with audit fields and validation from CSV logger approach.
"""

from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Index
import hashlib

db = SQLAlchemy()


class Price(db.Model):
    """Historical stock prices with audit trail"""
    __tablename__ = 'prices'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.String(16), unique=True, nullable=False, index=True)
    ticker = db.Column(db.String(10), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, nullable=False, index=True)
    close = db.Column(db.Numeric(10, 2), nullable=False)
    open = db.Column(db.Numeric(10, 2))
    high = db.Column(db.Numeric(10, 2))
    low = db.Column(db.Numeric(10, 2))
    volume = db.Column(db.BigInteger)

    # Audit fields from Daniel's CSV logger
    kind = db.Column(db.String(20), default='HISTORY')  # HISTORY, SNAPSHOT, TRADE
    price_source = db.Column(db.String(20), default='yfinance')  # yfinance, user, alpha_vantage
    out_of_order = db.Column(db.Boolean, default=False)
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('idx_ticker_timestamp', 'ticker', 'timestamp'),
        Index('idx_event_id', 'event_id'),
    )

    @staticmethod
    def generate_event_id(ticker, timestamp, close, kind='HISTORY', note=''):
        """Generate unique event ID for deduplication"""
        key = f"{timestamp.isoformat()}|{ticker}|{kind}|{float(close)}|{note}"
        return hashlib.sha256(key.encode('utf-8')).hexdigest()[:16]

    def __repr__(self):
        return f'<Price {self.ticker} @ {self.timestamp}: ${self.close}>'

    def to_dict(self):
        return {
            'id': self.id,
            'event_id': self.event_id,
            'ticker': self.ticker,
            'timestamp': self.timestamp.isoformat(),
            'close': float(self.close),
            'open': float(self.open) if self.open else None,
            'high': float(self.high) if self.high else None,
            'low': float(self.low) if self.low else None,
            'volume': self.volume,
            'kind': self.kind,
            'price_source': self.price_source,
            'out_of_order': self.out_of_order,
            'note': self.note
        }


class Trade(db.Model):
    """Buy/Sell transactions with audit trail"""
    __tablename__ = 'trades'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.String(16), unique=True, nullable=False, index=True)
    timestamp = db.Column(db.DateTime, nullable=False, index=True)
    ticker = db.Column(db.String(10), nullable=False, index=True)
    action = db.Column(db.String(10), nullable=False)  # BUY, SELL
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    total_cost = db.Column(db.Numeric(12, 2), nullable=False)

    # Audit fields
    position_before = db.Column(db.Integer)
    position_after = db.Column(db.Integer, nullable=False)
    cash_before = db.Column(db.Numeric(12, 2))
    cash_after = db.Column(db.Numeric(12, 2), nullable=False)
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('idx_timestamp', 'timestamp'),
        Index('idx_ticker', 'ticker'),
    )

    @staticmethod
    def generate_event_id(timestamp, ticker, action, quantity, price):
        """Generate unique event ID for deduplication"""
        key = f"{timestamp.isoformat()}|{ticker}|{action}|{quantity}|{float(price)}"
        return hashlib.sha256(key.encode('utf-8')).hexdigest()[:16]

    def __repr__(self):
        return f'<Trade {self.action} {self.quantity} {self.ticker} @ ${self.price}>'

    def to_dict(self):
        return {
            'id': self.id,
            'event_id': self.event_id,
            'timestamp': self.timestamp.isoformat(),
            'ticker': self.ticker,
            'action': self.action,
            'quantity': self.quantity,
            'price': float(self.price),
            'total_cost': float(self.total_cost),
            'position_before': self.position_before,
            'position_after': self.position_after,
            'cash_before': float(self.cash_before) if self.cash_before else None,
            'cash_after': float(self.cash_after) if self.cash_after else None,
            'note': self.note
        }


class Snapshot(db.Model):
    """Portfolio state snapshots (taken manually or after trades)"""
    __tablename__ = 'snapshots'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.String(16), unique=True, nullable=False, index=True)
    timestamp = db.Column(db.DateTime, nullable=False, index=True)
    ticker = db.Column(db.String(10), nullable=False, index=True)
    position = db.Column(db.Integer, nullable=False, default=0)
    cash_balance = db.Column(db.Numeric(12, 2))
    portfolio_value = db.Column(db.Numeric(12, 2))
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('idx_snapshot_timestamp', 'timestamp'),
        Index('idx_snapshot_ticker_timestamp', 'ticker', 'timestamp'),
    )

    @staticmethod
    def generate_event_id(timestamp, ticker, position):
        """Generate unique event ID for deduplication"""
        key = f"{timestamp.isoformat()}|{ticker}|SNAPSHOT|{position}"
        return hashlib.sha256(key.encode('utf-8')).hexdigest()[:16]

    def __repr__(self):
        return f'<Snapshot {self.ticker} @ {self.timestamp}: {self.position} shares>'

    def to_dict(self):
        return {
            'id': self.id,
            'event_id': self.event_id,
            'timestamp': self.timestamp.isoformat(),
            'ticker': self.ticker,
            'position': self.position,
            'cash_balance': float(self.cash_balance) if self.cash_balance else None,
            'portfolio_value': float(self.portfolio_value) if self.portfolio_value else None,
            'note': self.note
        }


class PortfolioConfig(db.Model):
    """System configuration (key-value store)"""
    __tablename__ = 'portfolio_config'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<Config {self.key}={self.value}>'

    def to_dict(self):
        return {
            'key': self.key,
            'value': self.value,
            'updated_at': self.updated_at.isoformat()
        }

    @staticmethod
    def get_value(key, default=None):
        """Get config value by key"""
        config = PortfolioConfig.query.filter_by(key=key).first()
        return config.value if config else default

    @staticmethod
    def set_value(key, value):
        """Set config value (create or update)"""
        config = PortfolioConfig.query.filter_by(key=key).first()
        if config:
            config.value = str(value)
            config.updated_at = datetime.now(timezone.utc)
        else:
            config = PortfolioConfig(key=key, value=str(value))
            db.session.add(config)
        db.session.commit()
        return config