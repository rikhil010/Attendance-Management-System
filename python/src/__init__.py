"""
GWASOAT - Attendance System
Main Python package initialization
"""

__version__ = "2.1.0"

# Lazy import to avoid circular dependency issues
def get_app():
    from .app import app
    return app

__all__ = ["get_app"]
