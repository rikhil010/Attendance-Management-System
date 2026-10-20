"""GWASOAT Python Application - Main Entry Point (Multi-user)"""

import sys
import os
import webview
import threading
from datetime import timedelta
from flask import Flask

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import initialize_new_schema
from auth import setup_auth_routes
from routes_new import setup_new_routes
from routes_features import setup_feature_routes
from routes_student import setup_student_routes
from api import setup_routes as setup_legacy_routes

app = Flask(__name__,
            template_folder='../../web/templates',
            static_folder='../../web/static')
app.secret_key = 'gwasoat-secret-key-2026'
app.permanent_session_lifetime = timedelta(days=30)

# Initialize database schema
initialize_new_schema()

# Register routes
setup_auth_routes(app)
setup_new_routes(app)
setup_feature_routes(app)
setup_student_routes(app)
setup_legacy_routes(app)  # Keep legacy /api/ routes for ESP32 communication


def run_flask():
    """Run Flask development server."""
    app.run(port=5000, debug=False, use_reloader=False)


def main():
    """Main application entry point."""
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    webview.create_window(
        'GWASOAT Attendance System',
        'http://127.0.0.1:5000',
        width=1280,
        height=800
    )
    webview.start(debug=True)  # debug=True enables Ctrl+R reload and dev tools


if __name__ == "__main__":
    main()
