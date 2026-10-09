# Brother Document Station — Flask Application

This package provides the Python web application for Brother Document
Station, a self-hosted print and scan service for the Brother DCP-1610W.
Flask handles the web interface and API, CUPS submits print jobs, and SANE
captures scans through Brother's Linux drivers.

The browser interface, templates, and static assets live in the repository
root. The container build combines them with this Python package.

## Architecture

- `src/scanner_app/app.py` creates the Flask application and registers
  application-wide handlers.
- `src/scanner_app/routes.py` renders the interface and handles the print,
  scan, preview, and download endpoints.
- `src/scanner_app/printing.py` validates print options, prepares uploads,
  and submits print jobs to CUPS.
- `src/scanner_app/scanning.py` discovers the scanner, captures pages, and
  creates PDF, PNG, or JPEG output.
- `src/scanner_app/temporary_storage.py` manages private, expiring scan
  sessions.
- `src/scanner_app/processes.py` runs system commands with bounded timeouts.
- `src/scanner_app/settings.py` reads runtime settings from the environment.
- `src/scanner_app/constants.py` defines documented device options, defaults,
  limits, dimensions, and command timeouts.
- `src/scanner_app/messages.py` defines stable English API message codes.
  The browser resolves these codes through its selected locale catalog.

Uploaded and scanned documents are kept only for their active print or scan
transaction. Scan data is stored in the container's temporary filesystem and
removed when a session closes or expires; it is not stored in a Docker volume.

## Requirements

- Python 3.12 or later
- [uv](https://docs.astral.sh/uv/)
- CUPS and SANE, with the Brother DCP-1610W Linux drivers installed

For local device access, the host must have a configured CUPS queue and SANE
scanner. The Docker image installs and configures these system dependencies.

## Development

From the repository root, install the locked Python dependencies with `uv`:

```sh
uv sync --project scanner-app
```

Run the Flask application through Gunicorn:

```sh
uv run --project scanner-app gunicorn 'scanner_app:create_app()'
```

Python dependency versions are declared in `pyproject.toml` and locked in
`uv.lock`. Update the lock file with:

```sh
uv lock --project scanner-app
```

The root-level `Dockerfile` builds the frontend assets and this package into
the application image. See the repository's [main README](../README.md) for
container setup, printer configuration, API routes, and frontend build
instructions.
