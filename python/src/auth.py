"""
Authentication module for GWASOAT.
Handles login, sessions, and role-based access control.
"""

import functools
import os
import json
from flask import session, request, jsonify, redirect, url_for
from models import get_db, hash_password

REMEMBER_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'data', '.remember')


def _save_remember(user_id):
    """Save user ID to file for persistent login."""
    try:
        os.makedirs(os.path.dirname(REMEMBER_FILE), exist_ok=True)
        with open(REMEMBER_FILE, 'w') as f:
            json.dump({'user_id': user_id}, f)
    except Exception:
        pass


def _load_remember():
    """Load saved user ID from file."""
    try:
        if os.path.exists(REMEMBER_FILE):
            with open(REMEMBER_FILE, 'r') as f:
                data = json.load(f)
                return data.get('user_id')
    except Exception:
        pass
    return None


def _clear_remember():
    """Delete the remember file."""
    try:
        if os.path.exists(REMEMBER_FILE):
            os.remove(REMEMBER_FILE)
    except Exception:
        pass


def login_user(email, password):
    """Attempt login. Returns user dict or None."""
    db = get_db()
    user = db.execute(
        "SELECT id, name, email, role FROM users WHERE email = ? AND password = ?",
        (email, hash_password(password))
    ).fetchone()
    db.close()
    if user:
        return dict(user)
    return None


def get_current_user():
    """Get current logged-in user from session."""
    user_id = session.get('user_id')
    if not user_id:
        return None
    db = get_db()
    user = db.execute(
        "SELECT id, name, email, role FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    db.close()
    return dict(user) if user else None


def login_required(f):
    """Decorator: requires login for API endpoints."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'status': 'error', 'message': 'Login required'}), 401
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """Decorator: requires admin role."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user or user['role'] != 'admin':
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'status': 'error', 'message': 'Admin access required'}), 403
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated


def setup_auth_routes(app):
    """Register authentication routes."""

    @app.route('/login', methods=['GET'])
    def login_page():
        if session.get('user_id'):
            return redirect('/home')
        return app.send_static_file('../templates/login.html') if False else \
            render_login_page()

    @app.route('/auth/login', methods=['POST'])
    def do_login():
        data = request.get_json() if request.is_json else request.form
        email = data.get('email', '').strip()
        password = data.get('password', '')
        remember = data.get('remember', False)

        user = login_user(email, password)
        if not user:
            return jsonify({'status': 'error', 'message': 'Invalid email or password'}), 401

        session['user_id'] = user['id']
        session['user_name'] = user['name']
        session['user_role'] = user['role']
        session.permanent = True

        # Save to file for persistence across app restarts
        if remember:
            _save_remember(user['id'])
        else:
            _clear_remember()

        return jsonify({'status': 'success', 'user': user})

    @app.route('/auth/logout')
    def do_logout():
        session.clear()
        _clear_remember()
        return redirect('/login')

    # Auto-login from saved remember file on page load
    @app.before_request
    def auto_login():
        if not session.get('user_id'):
            uid = _load_remember()
            if uid:
                db = get_db()
                user = db.execute("SELECT id, name, email, role FROM users WHERE id=?", (uid,)).fetchone()
                db.close()
                if user:
                    session['user_id'] = user['id']
                    session['user_name'] = user['name']
                    session['user_role'] = user['role']
                    session.permanent = True

    @app.route('/auth/me')
    @login_required
    def get_me():
        user = get_current_user()
        return jsonify(user)


def render_login_page():
    """Return inline login HTML."""
    from flask import render_template_string
    return render_template_string(LOGIN_HTML)


LOGIN_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GWASOAT - Login</title>
    <link href="/static/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background: #1a1a2e; min-height: 100vh; display: flex; align-items: center; justify-content: center; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; }
        .login-card { background: #ffffff; border: 1px solid #d1d9e0; border-radius: 6px; padding: 40px; width: 100%; max-width: 400px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .login-card h2 { color: #24292e; margin-bottom: 30px; text-align: center; }
        .form-control { border-radius: 6px; }
        .btn-primary { background-color: #0366d6; border-color: #0366d6; width: 100%; padding: 10px; font-size: 15px; }
        .btn-primary:hover { background-color: #0256cc; border-color: #0256cc; }
        .alert { font-size: 14px; }
    </style>
</head>
<body>
    <div class="login-card">
        <h2>GWASOAT</h2>
        <div id="error" class="alert alert-danger d-none"></div>
        <form id="loginForm">
            <div class="mb-3">
                <label class="form-label">Email</label>
                <input type="email" class="form-control" id="email" required>
            </div>
            <div class="mb-3">
                <label class="form-label">Password</label>
                <input type="password" class="form-control" id="password" required>
            </div>
            <div class="mb-3 form-check">
                <input type="checkbox" class="form-check-input" id="remember">
                <label class="form-check-label">Remember me</label>
            </div>
            <button type="submit" class="btn btn-primary">Login</button>
        </form>
    </div>
    <script src="/static/js/jquery-3.6.0.min.js"></script>
    <script>
    $('#loginForm').submit(function(e) {
        e.preventDefault();
        $('#error').addClass('d-none');
        $.ajax({
            url: '/auth/login',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({
                email: $('#email').val(),
                password: $('#password').val(),
                remember: $('#remember').is(':checked')
            }),
            success: function(data) {
                window.location.href = '/home';
            },
            error: function(xhr) {
                var msg = xhr.responseJSON ? xhr.responseJSON.message : 'Login failed';
                $('#error').text(msg).removeClass('d-none');
            }
        });
    });
    </script>
</body>
</html>'''
