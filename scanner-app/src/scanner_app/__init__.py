"""Expose the Flask application factory for WSGI servers."""

from scanner_app.app import create_app

__all__ = ["create_app"]
