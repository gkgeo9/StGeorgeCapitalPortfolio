# app.py
"""
Main Flask application entry point.
Initializes app, database, routes, and scheduler (manual mode).
"""

import os
from flask import Flask
from dotenv import load_dotenv  # Add this
from config import get_config
from models import db
from portfolio_manager import PortfolioManager
from scheduler import start_scheduler

# Load environment variables from .env file
load_dotenv()


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

        # NO automatic backfill on startup
        # Users will manually refresh via the UI button
        print("\n⚠️  Automatic backfill DISABLED")
        print("📌 Use the 'Refresh Data' button in the UI to update prices\n")

    # Register blueprints
    from routes.views import views_bp
    from routes.api import api_bp

    app.register_blueprint(views_bp)
    app.register_blueprint(api_bp, url_prefix='/api')

    # Start background scheduler (in manual mode - no automatic jobs)
    scheduler = start_scheduler(app)
    app.scheduler = scheduler

    print("\n" + "=" * 60)
    print("✓ FLASK APP INITIALIZED")
    print("=" * 60)
    print(f"Environment: {config_name}")
    print(f"Database: {app.config['SQLALCHEMY_DATABASE_URI'][:50]}...")  # Don't print full connection string
    print(f"Stocks tracked: {', '.join(app.config['PORTFOLIO_STOCKS'])}")
    print("Update mode: MANUAL (via UI button)")
    print("=" * 60 + "\n")

    return app


if __name__ == '__main__':
    app = create_app()

    # Get port from environment variable (for Railway/Render)
    port = int(os.environ.get('PORT', 5012))

    app.run(
        host='0.0.0.0',
        port=port,
        debug=app.config['DEBUG']
    )