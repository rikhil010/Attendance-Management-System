"""
Authentication module for GWASOAT.
Handles login, sessions, and role-based access control.
"""

import functools
import os
import json
from flask import session, request, jsonify, redirect, url_for
from models import get_db, hash_password, _fetchone, has_permission, get_role_permissions

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
    user = _fetchone(db,
        "SELECT id, name, email, role, student_id FROM users WHERE email = %s AND password = %s",
        (email, hash_password(password)))
    db.close()
    return dict(user) if user else None


def get_current_user():
    """Get current logged-in user from session (includes role permissions)."""
    user_id = session.get('user_id')
    if not user_id:
        return None
    db = get_db()
    user = _fetchone(db,
        "SELECT id, name, email, role, student_id FROM users WHERE id = %s", (user_id,))
    db.close()
    if not user:
        return None
    user = dict(user)
    user['permissions'] = sorted(get_role_permissions(user['role']))
    return user


def home_for_role(role):
    """Return the landing page path for a given role."""
    return '/student' if role == 'student' else '/home'


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


def _deny(message, code):
    """Return an error response appropriate for the request type."""
    if request.is_json or request.path.startswith('/api/'):
        return jsonify({'status': 'error', 'message': message}), code
    return redirect('/login')


def role_required(*roles):
    """Decorator: requires the current user to have one of the given roles."""
    def wrapper(f):
        @functools.wraps(f)
        def decorated(*args, **kwargs):
            user = get_current_user()
            if not user:
                return _deny('Login required', 401)
            if user['role'] not in roles:
                return _deny('You do not have access to this resource', 403)
            return f(*args, **kwargs)
        return decorated
    return wrapper


def student_required(f):
    """Decorator: requires student role."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return _deny('Login required', 401)
        if user['role'] != 'student':
            return _deny('Student access required', 403)
        return f(*args, **kwargs)
    return decorated


def staff_required(f):
    """Decorator: requires admin or teacher (i.e. not a student)."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return _deny('Login required', 401)
        if user['role'] not in ('admin', 'teacher'):
            return _deny('Staff access required', 403)
        return f(*args, **kwargs)
    return decorated


def permission_required(permission):
    """Decorator: requires the current user's role to grant the given permission."""
    def wrapper(f):
        @functools.wraps(f)
        def decorated(*args, **kwargs):
            user = get_current_user()
            if not user:
                return _deny('Login required', 401)
            if not has_permission(user['role'], permission):
                return _deny('Permission denied', 403)
            return f(*args, **kwargs)
        return decorated
    return wrapper


def can_manage_course(user, course_row):
    """Ownership rule: admin manages any course; a teacher only courses they teach."""
    if not user or not course_row:
        return False
    if user.get('role') == 'admin':
        return True
    return user.get('role') == 'teacher' and course_row.get('teacher_id') == user.get('id')


def check_course_access(user, course_id):
    """Return None if the user may manage the course, else an error (response, code) tuple."""
    db = get_db()
    course = _fetchone(db, "SELECT id, teacher_id FROM courses WHERE id=%s", (course_id,))
    db.close()
    if not course:
        return _deny('Course not found', 404)
    if not can_manage_course(user, course):
        return _deny('You do not have access to this course', 403)
    return None


def course_owner_required(f):
    """Decorator: the route's course_id must belong to the current user (admin: any)."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return _deny('Login required', 401)
        error = check_course_access(user, kwargs.get('course_id'))
        if error:
            return error
        return f(*args, **kwargs)
    return decorated


def setup_auth_routes(app):
    """Register authentication routes."""

    @app.route('/login', methods=['GET'])
    def login_page():
        if session.get('user_id'):
            return redirect(home_for_role(session.get('user_role', 'teacher')))
        return render_login_page()

    @app.route('/auth/login', methods=['POST'])
    def do_login():
        data = request.get_json() if request.is_json else request.form
        email = data.get('email', '').strip()
        password = data.get('password', '')
        remember = data.get('remember', False)

        user = login_user(email, password)
        if not user:
            return jsonify({'status': 'error', 'message': 'Invalid email or password'}), 401

        # Optional role hint from the login page selector. Enforce it so a user
        # cannot sign in through the wrong portal.
        requested_role = (data.get('role') or '').strip().lower()
        if requested_role and requested_role != user['role']:
            return jsonify({'status': 'error',
                            'message': f'This account is not a {requested_role} account'}), 403

        session['user_id'] = user['id']
        session['user_name'] = user['name']
        session['user_role'] = user['role']
        session['student_id'] = user.get('student_id')
        session.permanent = True

        # Save to file for persistence across app restarts
        if remember:
            _save_remember(user['id'])
        else:
            _clear_remember()

        return jsonify({'status': 'success', 'user': user, 'redirect': home_for_role(user['role'])})

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
                user = _fetchone(db,
                    "SELECT id, name, email, role, student_id FROM users WHERE id=%s", (uid,))
                db.close()
                if user:
                    session['user_id'] = user['id']
                    session['user_name'] = user['name']
                    session['user_role'] = user['role']
                    session['student_id'] = user['student_id']
                    session.permanent = True

    # Containment guard: students may only reach student-facing + shared paths.
    # This hardens every staff route (admin + teacher) against a logged-in student,
    # on top of the per-route decorators.
    STUDENT_ALLOWED_PREFIXES = (
        '/student', '/api/student', '/auth', '/login', '/profile',
        '/api/profile', '/api/me', '/static', '/favicon',
    )

    @app.before_request
    def restrict_students():
        if session.get('user_role') != 'student':
            return
        path = request.path
        if path == '/':
            return redirect('/student')
        if any(path == p or path.startswith(p + '/') for p in STUDENT_ALLOWED_PREFIXES):
            return
        if request.is_json or path.startswith('/api/'):
            return jsonify({'status': 'error', 'message': 'Students cannot access this resource'}), 403
        return redirect('/student')

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
    <link href="/static/css/app.css" rel="stylesheet">
    <style>
        body {
            min-height: 100vh; display: flex; align-items: center; justify-content: center;
            background: linear-gradient(135deg, #eef3f9 0%, #f6f8fa 60%, #eaf1fb 100%);
        }
        .login-wrap { width: 100%; max-width: 400px; padding: 16px; }
        .login-brand { text-align: center; margin-bottom: 22px; }
        .login-logo {
            width: 56px; height: 56px; border-radius: 14px; margin: 0 auto 12px;
            background: linear-gradient(135deg, #0366d6, #0a4fa0);
            display: flex; align-items: center; justify-content: center;
            color: #fff; font-size: 24px; font-weight: 700; letter-spacing: .5px;
            box-shadow: 0 6px 18px rgba(3,102,214,0.35);
        }
        .login-brand h1 { font-size: 22px; font-weight: 700; color: #24292e; margin: 0; }
        .login-brand p { font-size: 13px; color: #586069; margin: 4px 0 0; }
        .login-card {
            background: #fff; border: 1px solid #d1d9e0; border-radius: 10px;
            padding: 28px 26px; box-shadow: 0 1px 3px rgba(27,31,36,0.08), 0 12px 30px rgba(27,31,36,0.06);
        }
        .login-card .form-label { font-size: 13px; font-weight: 600; color: #24292e; }
        .pw-field { position: relative; }
        .pw-toggle {
            position: absolute; right: 8px; top: 50%; transform: translateY(-50%);
            border: 0; background: transparent; color: #586069; font-size: 12px; cursor: pointer; padding: 4px 6px;
        }
        .pw-toggle:hover { color: #24292e; }
        .btn-login { background-color: #0366d6; border-color: #0366d6; width: 100%; padding: 9px; font-size: 15px; font-weight: 500; }
        .btn-login:hover { background-color: #0256cc; border-color: #0256cc; }
        .login-foot { text-align: center; font-size: 12px; color: #8b949e; margin-top: 18px; }
        .role-tabs { display: flex; gap: 8px; margin-bottom: 20px; }
        .role-tab {
            flex: 1; text-align: center; padding: 10px 6px; border: 1px solid #d1d9e0;
            border-radius: 8px; background: #f6f8fa; color: #586069; cursor: pointer;
            font-size: 13px; font-weight: 600; user-select: none; transition: all .12s;
        }
        .role-tab .role-ico { display: block; font-size: 18px; margin-bottom: 3px; }
        .role-tab:hover { border-color: #0366d6; color: #24292e; }
        .role-tab.active {
            background: linear-gradient(135deg, #0366d6, #0a4fa0); color: #fff;
            border-color: #0366d6; box-shadow: 0 4px 12px rgba(3,102,214,0.3);
        }
        .role-hint { font-size: 12px; color: #8b949e; text-align: center; margin: -8px 0 14px; }
    </style>
</head>
<body>
    <div class="login-wrap">
        <div class="login-brand">
            <div class="login-logo">GW</div>
            <h1>GWASOAT</h1>
            <p>Fingerprint Attendance System</p>
        </div>
        <div class="login-card">
            <div class="role-tabs" id="roleTabs">
                <div class="role-tab active" data-role="admin">
                    <span class="role-ico">&#9733;</span>Admin
                </div>
                <div class="role-tab" data-role="teacher">
                    <span class="role-ico">&#9998;</span>Teacher
                </div>
                <div class="role-tab" data-role="student">
                    <span class="role-ico">&#127891;</span>Student
                </div>
            </div>
            <p class="role-hint" id="roleHint">Sign in to the administrator portal</p>
            <form id="loginForm" autocomplete="on">
                <input type="hidden" id="role" value="admin">
                <div class="mb-3">
                    <label class="form-label" for="email">Email</label>
                    <input type="email" class="form-control" id="email" placeholder="you@school.edu" required autofocus>
                </div>
                <div class="mb-3">
                    <label class="form-label" for="password">Password</label>
                    <div class="pw-field">
                        <input type="password" class="form-control" id="password" placeholder="Enter your password" required>
                        <button type="button" class="pw-toggle" id="pwToggle" tabindex="-1">Show</button>
                    </div>
                </div>
                <div class="mb-3 form-check">
                    <input type="checkbox" class="form-check-input" id="remember" checked>
                    <label class="form-check-label" for="remember">Keep me signed in</label>
                </div>
                <button type="submit" class="btn btn-primary btn-login" id="loginBtn">Sign in</button>
            </form>
        </div>
        <div class="login-foot">&copy; GWASOAT &middot; Secure local sign-in</div>
    </div>
    <script src="/static/js/jquery-3.6.0.min.js"></script>
    <script src="/static/js/app.js"></script>
    <script>
    var ROLE_HINTS = {
        admin:   'Sign in to the administrator portal',
        teacher: 'Sign in to the teacher portal',
        student: 'Sign in to the student portal'
    };
    var ROLE_PLACEHOLDER = {
        admin:   'admin@gwasoat.local',
        teacher: 'you@school.edu',
        student: 'student123@gwasoat.local'
    };

    $('#roleTabs').on('click', '.role-tab', function() {
        var role = $(this).data('role');
        $('.role-tab').removeClass('active');
        $(this).addClass('active');
        $('#role').val(role);
        $('#roleHint').text(ROLE_HINTS[role] || '');
        $('#email').attr('placeholder', ROLE_PLACEHOLDER[role] || '');
    });

    $('#pwToggle').on('click', function() {
        var f = $('#password');
        var show = f.attr('type') === 'password';
        f.attr('type', show ? 'text' : 'password');
        $(this).text(show ? 'Hide' : 'Show');
    });

    $('#loginForm').submit(function(e) {
        e.preventDefault();
        var email = $('#email').val().trim();
        var password = $('#password').val();
        var role = $('#role').val();
        if (!email || !password) { GW.toast('Enter your email and password', 'warning'); return; }
        GW.btnLoading('#loginBtn', true, 'Signing in...');
        $.ajax({
            url: '/auth/login',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ email: email, password: password, role: role, remember: $('#remember').is(':checked') }),
            success: function(resp) {
                GW.toast('Signed in. Loading your dashboard...', 'success', {duration: 1500});
                var dest = (resp && resp.redirect) ? resp.redirect : '/home';
                setTimeout(function() { window.location.href = dest; }, 400);
            },
            error: function(xhr) {
                GW.btnLoading('#loginBtn', false);
                var msg = xhr.responseJSON ? xhr.responseJSON.message : 'Login failed';
                GW.toast(msg, 'danger');
                $('#password').val('').focus();
            }
        });
    });
    </script>
</body>
</html>'''
