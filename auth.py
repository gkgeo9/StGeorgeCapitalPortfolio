# auth.py
"""
Authentication module for admin access control.
Uses Flask-Login with environment variable credentials.
"""

from flask_login import LoginManager, UserMixin
from flask import current_app
import bcrypt

login_manager = LoginManager()


class AdminUser(UserMixin):
    """Simple admin user class - no database needed."""

    def __init__(self, username):
        self.id = username
        self.username = username

    @staticmethod
    def validate_password(password: str) -> bool:
        """Validate password against stored hash."""
        stored_hash = current_app.config.get('ADMIN_PASSWORD_HASH')
        if not stored_hash:
            return False
        try:
            return bcrypt.checkpw(
                password.encode('utf-8'),
                stored_hash.encode('utf-8')
            )
        except Exception:
            return False

    @staticmethod
    def get(user_id):
        """Get user by ID (username)."""
        admin_username = current_app.config.get('ADMIN_USERNAME', 'admin')
        if user_id == admin_username:
            return AdminUser(user_id)
        return None


@login_manager.user_loader
def load_user(user_id):
    """Flask-Login user loader callback."""
    return AdminUser.get(user_id)


@login_manager.unauthorized_handler
def unauthorized():
    """Handle unauthorized access - return JSON for API, redirect for pages."""
    from flask import request, redirect, url_for, jsonify
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Authentication required'}), 401
    return redirect(url_for('views.login'))


def init_login_manager(app):
    """Initialize Flask-Login with the app."""
    login_manager.init_app(app)
    login_manager.login_view = 'views.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
