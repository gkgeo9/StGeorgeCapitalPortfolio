# app.py
"""
Main Flask application entry point.
Initializes app, database, routes, and scheduler.
"""

import os
from flask import Flask
from config import get_config
from models import db
from portfolio_manager import PortfolioManager
from scheduler import start_scheduler


def create_app(config_name=None):
    """Application factory pattern"""

    app = Flask(__name__)

    # Load configuration
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    app.config.from_object(get_config())

    # Initialize database
    db.init_app(app)

    # Initialize portfolio manager
    portfolio_manager = PortfolioManager(app)
    app.portfolio_manager = portfolio_manager

    # Create tables and initialize portfolio
    with app.app_context():
        db.create_all()
        portfolio_manager.initialize_portfolio()

        # Initial backfill on first startup
        from models import Price
        if Price.query.count() == 0:
            print("\n🚀 First startup detected - running initial backfill...")
            portfolio_manager.backfill_prices(days=365)
            portfolio_manager.take_snapshot(note="initial startup")

    # Register blueprints
    from routes.views import views_bp
    from routes.api import api_bp

    app.register_blueprint(views_bp)
    app.register_blueprint(api_bp, url_prefix='/api')

    # Start background scheduler
    scheduler = start_scheduler(app)
    app.scheduler = scheduler

    print("\n" + "=" * 60)
    print("✓ FLASK APP INITIALIZED")
    print("=" * 60)
    print(f"Environment: {config_name}")
    print(f"Database: {app.config['SQLALCHEMY_DATABASE_URI']}")
    print(f"Stocks tracked: {', '.join(app.config['PORTFOLIO_STOCKS'])}")
    print("=" * 60 + "\n")

    return app
#adding nothing tbh

if __name__ == '__main__':
    app = create_app()

    # Get port from environment variable (for Railway/Render)
    port = int(os.environ.get('PORT', 5012))

    app.run(
        host='0.0.0.0',
        port=port,
        debug=app.config['DEBUG']
    )