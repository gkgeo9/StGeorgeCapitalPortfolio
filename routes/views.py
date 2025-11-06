# routes/views.py
"""
HTML page routes.
Serves the main dashboard page.
"""

from flask import Blueprint, render_template

views_bp = Blueprint('views', __name__)


@views_bp.route('/')
def index():
    """Main dashboard page"""
    return render_template('dashboard.html')


@views_bp.route('/health')
def health():
    """Health check endpoint for deployment platforms"""
    return {'status': 'healthy'}, 200