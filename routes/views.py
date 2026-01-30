# routes/views.py

"""HTML page routes for dashboard and authentication."""

from urllib.parse import urlparse
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from auth import AdminUser
from extensions import limiter

views_bp = Blueprint('views', __name__)


def is_safe_redirect_url(target):
    """Check if the redirect URL is safe (internal only)."""
    if not target:
        return False
    # Only allow relative URLs (starting with /)
    if not target.startswith('/'):
        return False
    # Reject URLs with external host
    parsed = urlparse(target)
    return not parsed.netloc


@views_bp.route('/')
def index():
    return render_template('dashboard.html', is_admin=current_user.is_authenticated)


@views_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('views.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        admin_username = current_app.config.get('ADMIN_USERNAME', 'admin')

        if username == admin_username and AdminUser.validate_password(password):
            user = AdminUser(username)
            login_user(user, remember=True)

            next_page = request.args.get('next')
            if next_page and is_safe_redirect_url(next_page):
                return redirect(next_page)
            return redirect(url_for('views.index'))

        flash('Invalid username or password', 'error')

    return render_template('login.html')


@views_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('views.index'))


@views_bp.route('/health')
def health():
    return {'status': 'healthy'}, 200