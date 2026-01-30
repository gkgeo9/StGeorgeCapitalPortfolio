# routes/api.py

import logging
from functools import wraps
from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required
from sqlalchemy import desc
from models import db, Price, Trade, Snapshot
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)
api_bp = Blueprint('api', __name__)


def api_error_handler(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.exception(f"Error in {f.__name__}")
            return jsonify({'error': 'An error occurred'}), 500
    return wrapper


@api_bp.route('/portfolio')
@api_error_handler
def get_portfolio():
    pm = current_app.portfolio_manager
    stats = pm.calculate_portfolio_stats()

    holdings = []
    for ticker, data in stats['stock_values'].items():
        if data['shares'] > 0:
            holdings.append({
                'ticker': ticker,
                'shares': data['shares'],
                'price': round(data['price'], 2),
                'value': round(data['value'], 2),
                'weight': round(data['weight'], 1)
            })

    return jsonify({
        'total_value': round(stats['total_portfolio_value'], 2),
        'cash': round(stats['cash'], 2),
        'stock_value': round(stats['total_stock_value'], 2),
        'total_pnl': round(stats['total_pnl'], 2),
        'pnl_percent': round(stats['pnl_percent'], 2),
        'holdings': holdings,
        'timestamp': datetime.now(timezone.utc).isoformat()
    })


@api_bp.route('/refresh', methods=['POST'])
@login_required
@api_error_handler
def manual_refresh():
    pm = current_app.portfolio_manager
    success, message = pm.manual_backfill(default_lookback_days=30)

    if not success and "Cooldown" in message:
        return jsonify({'success': False, 'message': message}), 429

    snapshot_result = pm.take_snapshot(note="manual refresh")

    return jsonify({
        'success': True,
        'message': message,
        'portfolio_value': round(snapshot_result['portfolio_value'], 2),
        'timestamp': datetime.now(timezone.utc).isoformat()
    })


@api_bp.route('/snapshot', methods=['POST'])
@login_required
@api_error_handler
def take_snapshot():
    pm = current_app.portfolio_manager
    note = request.json.get('note', 'manual snapshot') if request.json else 'manual snapshot'
    result = pm.take_snapshot(note=note)

    return jsonify({
        'success': True,
        'message': 'Snapshot saved successfully',
        'portfolio_value': round(result['portfolio_value'], 2),
        'timestamp': datetime.now(timezone.utc).isoformat()
    })


@api_bp.route('/trade', methods=['POST'])
@login_required
@api_error_handler
def execute_trade():
    data = request.get_json()

    required_fields = ['ticker', 'action', 'quantity', 'price']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400

    ticker = data['ticker'].upper()
    action = data['action'].upper()
    quantity = int(data['quantity'])
    price = float(data['price'])
    note = data.get('note', '')[:1000]

    trade_date = None
    if 'date' in data and data['date']:
        try:
            dt = datetime.strptime(data['date'], '%Y-%m-%d')
            trade_date = dt.replace(hour=12, minute=0, second=0, tzinfo=timezone.utc)
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    if not ticker or len(ticker) > 12:
        return jsonify({'error': f'Invalid ticker format: {ticker}'}), 400

    if action not in ['BUY', 'SELL']:
        return jsonify({'error': f'Invalid action: {action}. Must be BUY or SELL'}), 400

    if quantity <= 0:
        return jsonify({'error': 'Quantity must be positive'}), 400

    if price <= 0:
        return jsonify({'error': 'Price must be positive'}), 400

    pm = current_app.portfolio_manager

    if action == 'SELL':
        positions = pm.get_current_positions()
        if positions.get(ticker, 0) < quantity:
            return jsonify({
                'error': f'Insufficient shares. You have {positions.get(ticker, 0)} shares of {ticker}'
            }), 400

    if action == 'BUY':
        cash = pm.get_cash_balance()
        total_cost = quantity * price
        if cash < total_cost:
            return jsonify({
                'error': f'Insufficient cash. You have ${cash:,.2f} but need ${total_cost:,.2f}'
            }), 400

    trade = pm.record_trade(
        ticker=ticker,
        action=action,
        quantity=quantity,
        price=price,
        note=note,
        timestamp=trade_date
    )

    return jsonify({
        'success': True,
        'trade': trade.to_dict(),
        'message': f'Successfully executed {action} of {quantity} {ticker} @ ${price:.2f}'
    })


@api_bp.route('/trades')
@api_error_handler
def get_trades():
    limit = request.args.get('limit', 20, type=int)
    trades = Trade.query.order_by(desc(Trade.timestamp)).limit(limit).all()
    return jsonify({'trades': [trade.to_dict() for trade in trades], 'count': len(trades)})


@api_bp.route('/timeline')
@api_error_handler
def get_timeline():
    days = request.args.get('days', 90, type=int)
    include_benchmark = request.args.get('include_benchmark', 'false').lower() == 'true'
    pm = current_app.portfolio_manager

    if include_benchmark:
        timeline = pm.get_portfolio_timeline_with_benchmark(days=days)
    else:
        timeline = pm.get_portfolio_timeline(days=days)

    return jsonify(timeline)


@api_bp.route('/performance')
@api_error_handler
def get_performance():
    pm = current_app.portfolio_manager
    metrics = pm.calculate_performance_metrics()
    best_stock, worst_stock = pm.get_best_worst_stocks()
    stats = pm.calculate_portfolio_stats()

    return jsonify({
        'total_return': round(stats['pnl_percent'], 2),
        'volatility': round(metrics['volatility'], 1),
        'sharpe_ratio': round(metrics['sharpe_ratio'], 2),
        'best_stock': best_stock,
        'worst_stock': worst_stock,
        'total_trades': Trade.query.count()
    })


@api_bp.route('/prices/<ticker>')
@api_error_handler
def get_stock_prices(ticker):
    days = request.args.get('days', 90, type=int)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    prices = Price.query.filter(
        Price.ticker == ticker.upper(),
        Price.timestamp >= cutoff
    ).order_by(Price.timestamp).all()

    return jsonify({
        'ticker': ticker.upper(),
        'prices': [p.to_dict() for p in prices],
        'count': len(prices)
    })


@api_bp.route('/stocks')
@api_error_handler
def get_all_stocks():
    days = request.args.get('days', 90, type=int)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    stocks_data = {}

    for ticker in current_app.portfolio_manager.get_tracked_stocks():
        prices = Price.query.filter(
            Price.ticker == ticker,
            Price.timestamp >= cutoff
        ).order_by(Price.timestamp).all()

        stocks_data[ticker] = {
            'timestamps': [p.timestamp.isoformat() for p in prices],
            'prices': [float(p.close) for p in prices]
        }

    return jsonify(stocks_data)


@api_bp.route('/stats')
@login_required
@api_error_handler
def get_stats():
    pm = current_app.portfolio_manager
    cash = pm.get_cash_balance()
    positions = pm.get_current_positions()

    oldest_price = Price.query.order_by(Price.timestamp).first()
    latest_price = Price.query.order_by(desc(Price.timestamp)).first()

    return jsonify({
        'total_prices': Price.query.count(),
        'total_trades': Trade.query.count(),
        'total_snapshots': Snapshot.query.count(),
        'stocks_tracked': len(pm.get_tracked_stocks()),
        'current_cash': round(cash, 2),
        'current_positions': positions,
        'oldest_price': oldest_price.timestamp.isoformat() if oldest_price else None,
        'latest_price': latest_price.timestamp.isoformat() if latest_price else None
    })


@api_bp.route('/market-status')
@api_error_handler
def get_market_status():
    pm = current_app.portfolio_manager
    market_open = None
    try:
        market_open = pm.provider.is_market_open()
    except Exception:
        pass
    return jsonify({'market_open': market_open})


@api_bp.route('/provider-status')
@login_required
@api_error_handler
def get_provider_status():
    pm = current_app.portfolio_manager
    provider = pm.provider

    status = {
        'provider': provider.get_provider_name(),
        'is_healthy': True,
        'cooldown_seconds': pm._cooldown_seconds,
    }

    if hasattr(provider, 'get_quota_status'):
        status['quota'] = provider.get_quota_status()

    try:
        status['market_open'] = provider.is_market_open()
    except Exception:
        status['market_open'] = None

    return jsonify(status)


@api_bp.route('/reset_db', methods=['POST'])
@login_required
@api_error_handler
def reset_database():
    db.drop_all()
    db.create_all()
    pm = current_app.portfolio_manager
    pm.initialize_portfolio()
    return jsonify({'success': True, 'message': 'Database reset successfully'})


@api_bp.route('/health')
def health_check():
    return jsonify({'status': 'ok', 'timestamp': datetime.now(timezone.utc).isoformat()})


@api_bp.route('/settings')
def get_settings():
    import os
    fake_ticker = os.environ.get('FAKE_LIVE_TICKER', 'false').lower() == 'true'
    return jsonify({'fake_live_ticker': fake_ticker})
