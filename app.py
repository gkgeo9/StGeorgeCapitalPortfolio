# app.py
"""
Main Flask application entry point.
Initializes app, database, and routes.
"""

import os
from flask import Flask
from dotenv import load_dotenv
from config import get_config
from models import db
from portfolio_manager import PortfolioManager

load_dotenv()


def create_app(config_name=None):
    """Application factory pattern"""
    app = Flask(__name__)

    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    app.config.from_object(get_config())

    db.init_app(app)

    portfolio_manager = PortfolioManager(app)
    app.portfolio_manager = portfolio_manager

    with app.app_context():
        db.create_all()
        portfolio_manager.initialize_portfolio()

    from routes.views import views_bp
    from routes.api import api_bp

    app.register_blueprint(views_bp)
    app.register_blueprint(api_bp, url_prefix='/api')

    print(f"\n{'=' * 50}")
    print(f"St George Capital Portfolio")
    print(f"{'=' * 50}")
    print(f"Environment: {config_name}")
    print(f"Provider: {portfolio_manager.provider.get_provider_name()}")
    with app.app_context():
        stocks = portfolio_manager.get_tracked_stocks()
        print(f"Stocks: {', '.join(stocks)}")
    print(f"Refresh: Manual (via UI button)")
    print(f"{'=' * 50}\n")

    return app


if __name__ == '__main__':
    app = create_app()
    port = int(os.environ.get('PORT', 5012))
    app.run(host='0.0.0.0', port=port, debug=app.config['DEBUG'])