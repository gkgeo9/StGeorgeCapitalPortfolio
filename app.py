# app.py

"""Main Flask application entry point."""

import os
import logging
from flask import Flask
from dotenv import load_dotenv
from config import get_config
from models import db
from extensions import csrf, limiter
from portfolio_manager import PortfolioManager
from auth import init_login_manager

load_dotenv()


def create_app(config_name=None):
    app = Flask(__name__)

    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    app.config.from_object(get_config())

    log_level = logging.DEBUG if app.config['DEBUG'] else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    db.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    init_login_manager(app)

    portfolio_manager = PortfolioManager(app)
    app.portfolio_manager = portfolio_manager

    with app.app_context():
        db.create_all()
        portfolio_manager.initialize_portfolio()

    from routes.views import views_bp
    from routes.api import api_bp

    app.register_blueprint(views_bp)
    app.register_blueprint(api_bp, url_prefix='/api')

    csrf.exempt(api_bp)

    logger.info("=" * 50)
    logger.info("St George Capital Portfolio")
    logger.info("=" * 50)
    logger.info(f"Environment: {config_name}")
    logger.info(f"Provider: {portfolio_manager.provider.get_provider_name()}")
    with app.app_context():
        stocks = portfolio_manager.get_tracked_stocks()
        logger.info(f"Stocks: {', '.join(stocks)}")
    logger.info("Refresh: Manual (via UI button)")
    logger.info("=" * 50)

    return app


if __name__ == '__main__':
    app = create_app()
    port = int(os.environ.get('PORT', 5012))
    app.run(host='0.0.0.0', port=port, debug=app.config['DEBUG'])