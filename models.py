# models.py
"""
Database models for portfolio tracking system.
Defines tables: prices, trades, snapshots, portfolio_config
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Index

db = SQLAlchemy()


class Price(db.Model):
    """Historical stock prices from yfinance"""
    __tablename__ = 'prices'

    id = db.Column(db.Integer, primary_key=True)
    ticker = db.Column(db.String(10), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, nullable=False, index=True)
    close = db.Column(db.Numeric(10, 2), nullable=False)
    open = db.Column(db.Numeric(10, 2))
    high = db.Column(db.Numeric(10, 2))
    low = db.Column(db.Numeric(10, 2))
    volume = db.Column(db.BigInteger)
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Unique constraint: one price per ticker per timestamp
    __table_args__ = (
        db.UniqueConstraint('ticker', 'timestamp', name='uix_ticker_timestamp'),
        Index('idx_ticker_timestamp', 'ticker', 'timestamp'),
    )

    def __repr__(self):
        return f'<Price {self.ticker} @ {self.timestamp}: ${self.close}>'

    def to_dict(self):
        return {
            'id': self.id,
            'ticker': self.ticker,
            'timestamp': self.timestamp.isoformat(),
            'close': float(self.close),
            'open': float(self.open) if self.open else None,
            'high': float(self.high) if self.high else None,
            'low': float(self.low) if self.low else None,
            'volume': self.volume,
            'note': self.note
        }


class Trade(db.Model):
    """Buy/Sell transactions"""
    __tablename__ = 'trades'

    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False, index=True)
    ticker = db.Column(db.String(10), nullable=False, index=True)
    action = db.Column(db.String(10), nullable=False)  # BUY, SELL
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    total_cost = db.Column(db.Numeric(12, 2), nullable=False)
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_timestamp', 'timestamp'),
        Index('idx_ticker', 'ticker'),
    )

    def __repr__(self):
        return f'<Trade {self.action} {self.quantity} {self.ticker} @ ${self.price}>'

    def to_dict(self):
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat(),
            'ticker': self.ticker,
            'action': self.action,
            'quantity': self.quantity,
            'price': float(self.price),
            'total_cost': float(self.total_cost),
            'note': self.note
        }


class Snapshot(db.Model):
    """Portfolio state snapshots (taken periodically)"""
    __tablename__ = 'snapshots'

    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False, index=True)
    ticker = db.Column(db.String(10), nullable=False, index=True)
    position = db.Column(db.Integer, nullable=False, default=0)  # shares held
    cash_balance = db.Column(db.Numeric(12, 2))  # cash at this moment
    portfolio_value = db.Column(db.Numeric(12, 2))  # total value at this moment
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_snapshot_timestamp', 'timestamp'),
        Index('idx_snapshot_ticker_timestamp', 'ticker', 'timestamp'),
    )

    def __repr__(self):
        return f'<Snapshot {self.ticker} @ {self.timestamp}: {self.position} shares>'

    def to_dict(self):
        return {
            'id': self.id,
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
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
            config.updated_at = datetime.utcnow()
        else:
            config = PortfolioConfig(key=key, value=str(value))
            db.session.add(config)
        db.session.commit()
        return config