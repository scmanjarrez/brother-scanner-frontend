"""Create the Flask application and register application-wide handlers.

This module assembles settings, routes, and shared HTTP error responses.
"""

import os
from pathlib import Path

from flask import Flask, Response, jsonify
from werkzeug.exceptions import RequestEntityTooLarge

from scanner_app import constants
from scanner_app.messages import MessageCode, MessageError
from scanner_app.routes import register_routes
from scanner_app.settings import AppSettings
from scanner_app.temporary_storage import cleanup_expired_scan_sessions


def create_app() -> Flask:
    """Build and configure the Flask application.

    Creates the temporary root before registering routes and handlers.

    Returns:
        The configured Flask application.

    Raises:
        ValueError: If MAX_UPLOAD_MB is not an integer.
        OSError: If temporary storage cannot be initialized.
    """
    settings = AppSettings.from_environment()
    settings.temporary_dir.mkdir(
        parents=True,
        exist_ok=True,
        mode=constants.PRIVATE_DIRECTORY_MODE,
    )
    cleanup_expired_scan_sessions(settings.temporary_dir)
    app_root = Path(os.environ.get("APP_ROOT", str(Path.cwd())))

    app = Flask(
        __name__,
        template_folder=str(app_root / "templates"),
        static_folder=str(app_root / "static"),
    )
    app.config["MAX_CONTENT_LENGTH"] = settings.max_upload_bytes
    register_routes(app, settings)
    _register_scan_session_cleanup(app, settings)
    _register_upload_error_handler(app)
    return app


def _register_scan_session_cleanup(
    app: Flask,
    settings: AppSettings,
) -> None:
    """Register cleanup for inactive scan sessions before each request.

    Args:
        app: Flask application receiving the request hook.
        settings: Runtime paths and printer queue configuration.
    """

    @app.before_request
    def cleanup_inactive_sessions() -> None:
        """Remove scan sessions that have been inactive too long."""
        cleanup_expired_scan_sessions(settings.temporary_dir)


def _register_upload_error_handler(app: Flask) -> None:
    """Register a JSON response for requests exceeding the upload limit.

    Args:
        app: Flask application receiving the error handler.
    """

    @app.errorhandler(RequestEntityTooLarge)
    def upload_too_large(
        _error: RequestEntityTooLarge,
    ) -> tuple[Response, int]:
        """Return a clear response when an upload exceeds the limit.

        Args:
            _error: Werkzeug exception raised for an oversized request.

        Returns:
            A JSON response and the HTTP 413 status code.
        """
        error = MessageError(MessageCode.FILE_TOO_LARGE)
        return jsonify(error=error.to_payload()), 413
