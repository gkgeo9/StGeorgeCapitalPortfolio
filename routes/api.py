# routes/api.py
"""
API endpoints for portfolio data.
Returns JSON responses for frontend consumption.
Now includes manual refresh/backfill endpoints.
"""

from flask import Blueprint, jsonify, request, current_app
from sqlalchemy import desc
from models import db, Price, Trade, Snapshot
from datetime import datetime, timedelta

api_bp = Blueprint('api', __name__)


@api_bp.route('/portfolio')
def get_portfolio():
    """Get current portfolio statistics and holdings"""
    try:
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
            'timestamp': datetime.utcnow().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/refresh', methods=['POST'])
def manual_refresh():
    """
    Manual refresh endpoint - THE ONLY PLACE that calls Alpha Vantage API.
    Backfills price data and takes snapshot.
    """
    try:
        pm = current_app.portfolio_manager

        # Run manual backfill (with cooldown protection)
        # Default is 365 days for initial backfill, incremental thereafter
        success, message = pm.manual_backfill(default_lookback_days=365)

        if not success and "Cooldown" in message:
            return jsonify({
                'success': False,
                'message': message
            }), 429  # Too Many Requests

        # Take a snapshot after backfill (uses DB prices, no API call)
        snapshot_result = pm.take_snapshot(note="manual refresh")

        return jsonify({
            'success': True,
            'message': message,
            'portfolio_value': round(snapshot_result['portfolio_value'], 2),
            'timestamp': datetime.utcnow().isoformat()
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/snapshot', methods=['POST'])
def take_snapshot():
    """Take a manual snapshot of current portfolio state"""
    try:
        pm = current_app.portfolio_manager
        note = request.json.get('note', 'manual snapshot') if request.json else 'manual snapshot'

        result = pm.take_snapshot(note=note)

        return jsonify({
            'success': True,
            'message': 'Snapshot saved successfully',
            'portfolio_value': round(result['portfolio_value'], 2),
            'timestamp': datetime.utcnow().isoformat()
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/trade', methods=['POST'])
def execute_trade():
    """Execute a buy or sell trade"""
    try:
        data = request.get_json()

        # Validate required fields
        required_fields = ['ticker', 'action', 'quantity', 'price']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400

        ticker = data['ticker'].upper()
        action = data['action'].upper()
        quantity = int(data['quantity'])
        price = float(data['price'])
        note = data.get('note', '')

        # Validate ticker (basic check)
        if not ticker or len(ticker) > 5:
            return jsonify({'error': f'Invalid ticker format: {ticker}'}), 400

        # Validate action
        if action not in ['BUY', 'SELL']:
            return jsonify({'error': f'Invalid action: {action}. Must be BUY or SELL'}), 400

        # Validate quantity
        if quantity <= 0:
            return jsonify({'error': 'Quantity must be positive'}), 400

        # Validate price
        if price <= 0:
            return jsonify({'error': 'Price must be positive'}), 400

        # Check if we have enough shares to sell
        if action == 'SELL':
            pm = current_app.portfolio_manager
            positions = pm.get_current_positions()

            if positions[ticker] < quantity:
                return jsonify({
                    'error': f'Insufficient shares. You have {positions[ticker]} shares of {ticker}'
                }), 400

        # Check if we have enough cash to buy
        if action == 'BUY':
            pm = current_app.portfolio_manager
            cash = pm.get_cash_balance()
            total_cost = quantity * price

            if cash < total_cost:
                return jsonify({
                    'error': f'Insufficient cash. You have ${cash:,.2f} but need ${total_cost:,.2f}'
                }), 400

        # Execute trade
        pm = current_app.portfolio_manager
        trade = pm.record_trade(
            ticker=ticker,
            action=action,
            quantity=quantity,
            price=price,
            note=note
        )

        # NO automatic snapshot - no API calls on trade
        # User must click Refresh button to update prices

        return jsonify({
            'success': True,
            'trade': trade.to_dict(),
            'message': f'Successfully executed {action} of {quantity} {ticker} @ ${price:.2f}'
        })

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/trades')
def get_trades():
    """Get recent trades"""
    try:
        limit = request.args.get('limit', 20, type=int)

        trades = Trade.query.order_by(desc(Trade.timestamp)).limit(limit).all()

        return jsonify({
            'trades': [trade.to_dict() for trade in trades],
            'count': len(trades)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/timeline')
def get_timeline():
    """Get portfolio value over time"""
    try:
        days = request.args.get('days', 90, type=int)
        pm = current_app.portfolio_manager

        timeline = pm.get_portfolio_timeline(days=days)

        return jsonify(timeline)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/performance')
def get_performance():
    """Get performance metrics"""
    try:
        pm = current_app.portfolio_manager

        metrics = pm.calculate_performance_metrics()
        best_stock, worst_stock = pm.get_best_worst_stocks()

        stats = pm.calculate_portfolio_stats()

        return jsonify({
            'total_return': round(stats['pnl_percent'], 2),
            'volatility': round(metrics['volatility'], 1),
            'sharpe_ratio': round(metrics['sharpe_ratio'], 2),
            'max_drawdown': round(metrics['max_drawdown'], 1),
            'win_rate': round(metrics['win_rate'], 1),
            'best_stock': best_stock,
            'worst_stock': worst_stock,
            'total_trades': Trade.query.count()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/prices/<ticker>')
def get_stock_prices(ticker):
    """Get price history for a specific stock"""
    try:
        days = request.args.get('days', 90, type=int)
        cutoff = datetime.utcnow() - timedelta(days=days)

        prices = Price.query.filter(
            Price.ticker == ticker.upper(),
            Price.timestamp >= cutoff
        ).order_by(Price.timestamp).all()

        return jsonify({
            'ticker': ticker.upper(),
            'prices': [p.to_dict() for p in prices],
            'count': len(prices)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/stocks')
def get_all_stocks():
    """Get price history for all tracked stocks"""
    try:
        days = request.args.get('days', 90, type=int)
        cutoff = datetime.utcnow() - timedelta(days=days)

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

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/stats')
def get_stats():
    """Get database statistics"""
    try:
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

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/provider-status')
def get_provider_status():
    """Get current price provider status and quota info"""
    try:
        pm = current_app.portfolio_manager
        provider = pm.provider

        status = {
            'provider': provider.get_provider_name(),
            'is_healthy': True,
            'cooldown_seconds': pm._cooldown_seconds,
        }

        # Add quota info if provider supports it (Alpha Vantage)
        if hasattr(provider, 'get_quota_status'):
            status['quota'] = provider.get_quota_status()

        # Check if market is open
        try:
            status['market_open'] = provider.is_market_open()
        except Exception:
            status['market_open'] = None

        return jsonify(status)

    except Exception as e:
        return jsonify({
            'provider': 'unknown',
            'is_healthy': False,
            'error': str(e)
        }), 500