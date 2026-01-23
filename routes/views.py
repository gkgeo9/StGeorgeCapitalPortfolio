# routes/views.py
"""
HTML page routes.
Serves the main dashboard page and authentication routes.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from auth import AdminUser

views_bp = Blueprint('views', __name__)


@views_bp.route('/')
def index():
    """Main dashboard page - public read-only access, admin sees controls"""
    return render_template('dashboard.html', is_admin=current_user.is_authenticated)


@views_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Admin login page"""
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
            if next_page:
                return redirect(next_page)
            return redirect(url_for('views.index'))

        flash('Invalid username or password', 'error')

    return render_template('login.html')


@views_bp.route('/logout')
@login_required
def logout():
    """Log out the current user"""
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('views.index'))


@views_bp.route('/health')
def health():
    """Health check endpoint for deployment platforms"""
    return {'status': 'healthy'}, 200