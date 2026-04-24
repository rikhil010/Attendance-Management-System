"""GWASOAT Python Application - Main Entry Point"""

import sys
import os
import webview
import threading
from flask import Flask

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api import setup_routes

app = Flask(__name__, template_folder='../../web/templates', static_folder='../../web/static')

# Setup all API routes
setup_routes(app)


def run_flask():
    """Run Flask development server."""
    app.run(port=5000, debug=False, use_reloader=False)


def main():
    """Main application entry point."""
    # Start Flask in background thread
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    # Start web view GUI
    webview.create_window(
        'Attendance System Admin',
        'http://127.0.0.1:5000',
        width=1200,
        height=800
    )
    webview.start()


if __name__ == "__main__":
    main()
