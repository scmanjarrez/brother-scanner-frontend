"""Register HTTP routes for printing, scanning, and scan retrieval.

The endpoints validate request data and translate service errors into JSON.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from flask import Flask, Response, jsonify, render_template, request, send_file

from scanner_app import constants
from scanner_app.messages import MessageCode, MessageError, message_payload
from scanner_app.printing import (
    PrinterError,
    get_printer_status,
    parse_print_settings,
    submit_print_job,
)
from scanner_app.scanning import (
    ScannerError,
    ScanSettings,
    compose_document,
    compose_id_card,
    export_scan,
    list_scanners,
    parse_scan_settings,
    scan_to_png,
)
from scanner_app.settings import AppSettings
from scanner_app.temporary_storage import (
    ScanSession,
    ScanSessionError,
    create_scan_session,
    get_scan_session_directory,
    remove_scan_session,
)

if TYPE_CHECKING:
    from werkzeug.datastructures import FileStorage


@dataclass(frozen=True, slots=True)
class _ScanComposition:
    """Store validated options for combining scan pages.

    Attributes:
        workflow: Document or ID-card composition mode.
        artifact_ids: Scan page identifiers to include in the output.
        resolution: Resolution used for a multi-page PDF.
    """

    workflow: Literal["continuous", "card"]
    artifact_ids: tuple[str, ...]
    resolution: int


@dataclass(frozen=True, slots=True)
class _ScanRequest:
    """Store validated settings for one scan capture.

    Attributes:
        settings: Validated scanner options.
        workflow: Single-page, continuous, or ID-card scan mode.
        card_side: Side being captured in ID-card mode.
    """

    settings: ScanSettings
    workflow: Literal["single", "continuous", "card"]
    card_side: Literal["front", "back"]


@dataclass(frozen=True, slots=True)
class _ScanResult:
    """Store identifiers and an API code for a captured scan page.

    Attributes:
        session: Temporary scan session containing the page files.
        artifact_id: Identifier for the captured image.
        message: English API code describing the capture status.
    """

    session: ScanSession
    artifact_id: str
    message: MessageCode


def register_routes(app: Flask, settings: AppSettings) -> None:
    """Register the page and JSON endpoints on a Flask app.

    Args:
        app: Flask application receiving the route handlers.
        settings: Runtime paths and printer queue configuration.
    """
    _register_page_routes(app, settings)
    _register_print_route(app, settings)
    _register_scan_route(app, settings)
    _register_composition_route(app, settings)
    _register_artifact_routes(app, settings)


def _register_page_routes(app: Flask, settings: AppSettings) -> None:
    """Register the dashboard and device status routes.

    Args:
        app: Flask application receiving the routes.
        settings: Runtime paths and printer queue configuration.
    """

    @app.get("/")
    def home() -> str:
        """Render the print and scan dashboard.

        Returns:
            Rendered dashboard HTML.
        """
        return render_template("index.html")

    @app.get("/api/status")
    def status() -> Response:
        """Return the current CUPS queue and SANE scanner state.

        Returns:
            JSON containing printer and scanner readiness information.
        """
        printer_ready = get_printer_status(settings.printer_queue)
        scanners = list_scanners()
        return jsonify(
            printer_ready=printer_ready,
            scanner_ready=bool(scanners),
            scanner_count=len(scanners),
        )


def _register_print_route(app: Flask, settings: AppSettings) -> None:
    """Register the print submission route.

    Args:
        app: Flask application receiving the route.
        settings: Runtime paths and printer queue configuration.
    """

    @app.post("/api/print")
    def print_document() -> tuple[Response, int]:
        """Validate an upload and send it to the CUPS queue.

        Returns:
            JSON containing the job identifier or a validation error.
        """
        upload: FileStorage | None = request.files.get("file")
        if upload is None:
            error = MessageError(MessageCode.PRINT_FILE_REQUIRED)
            return jsonify(error=error.to_payload()), 400

        try:
            print_settings = parse_print_settings(request.form)
            job_id = submit_print_job(
                upload,
                print_settings,
                settings.printer_queue,
                temporary_root=settings.temporary_dir,
            )
        except PrinterError as err:
            return jsonify(error=err.to_payload()), 503
        except MessageError as err:
            return jsonify(error=err.to_payload()), 400

        message_code = (
            MessageCode.PRINT_JOB_SENT_WITH_ID
            if job_id
            else MessageCode.PRINT_JOB_SENT
        )
        message_params = {"jobId": job_id} if job_id else None
        return jsonify(
            message=message_payload(message_code, message_params),
            job_id=job_id,
        ), 200


def _register_scan_route(app: Flask, settings: AppSettings) -> None:
    """Register the scan capture route.

    Args:
        app: Flask application receiving the route.
        settings: Runtime paths and printer queue configuration.
    """
    app.add_url_rule(
        "/api/scan",
        endpoint="scan",
        view_func=partial(_scan_endpoint, settings),
        methods=["POST"],
    )


def _scan_endpoint(settings: AppSettings) -> tuple[Response, int]:
    """Handle a scan request and return its temporary artifact links.

    Args:
        settings: Runtime paths and printer queue configuration.

    Returns:
        JSON with artifact links, workflow details, or an API code.
    """
    try:
        scan_request = _parse_scan_request(request.form)
    except MessageError as err:
        return jsonify(error=err.to_payload()), 400

    submitted_session_id = request.form.get("scan_session_id")
    new_session = submitted_session_id is None
    try:
        scan_session = _resolve_scan_session(
            settings.temporary_dir,
            submitted_session_id,
        )
    except ScanSessionError as err:
        return jsonify(error=err.to_payload()), 400

    try:
        scan_result = _capture_scan(scan_request, scan_session)
    except ScannerError as err:
        _remove_new_scan_session(
            settings,
            scan_session,
            is_new_session=new_session,
        )
        return jsonify(error=err.to_payload()), 503
    except MessageError as err:
        _remove_new_scan_session(
            settings,
            scan_session,
            is_new_session=new_session,
        )
        return jsonify(error=err.to_payload()), 400

    session_id = scan_result.session.session_id
    artifact_id = scan_result.artifact_id
    return jsonify(
        scan_session_id=session_id,
        artifact_id=artifact_id,
        preview_url=f"/api/preview/{session_id}/{artifact_id}",
        download_url=f"/api/download/{session_id}/{artifact_id}",
        workflow=scan_request.workflow,
        card_side=scan_request.card_side,
        message=message_payload(scan_result.message),
    ), 200


def _parse_scan_request(form: Mapping[str, str]) -> _ScanRequest:
    """Validate scan settings and workflow options from a form.

    Args:
        form: Submitted scan form fields.

    Returns:
        Validated settings for the requested capture.

    Raises:
        MessageError: If scan settings or workflow options are invalid.
    """
    scan_settings = parse_scan_settings(form)
    workflow_value = form.get("workflow")
    if workflow_value == "single":
        workflow: Literal["single", "continuous", "card"] = "single"
    elif workflow_value == "continuous":
        workflow = "continuous"
    elif workflow_value == "card":
        workflow = "card"
    else:
        raise MessageError(MessageCode.SCAN_SELECTION_INVALID)

    card_side_value = form.get("card_side", "front")
    if workflow == "card" and card_side_value not in {"front", "back"}:
        raise MessageError(MessageCode.CARD_SIDE_INVALID)
    if card_side_value == "back":
        card_side: Literal["front", "back"] = "back"
    else:
        card_side = "front"

    return _ScanRequest(
        settings=scan_settings,
        workflow=workflow,
        card_side=card_side,
    )


def _resolve_scan_session(
    temporary_dir: Path,
    submitted_session_id: str | None,
) -> ScanSession:
    """Create or retrieve a temporary scan session.

    Args:
        temporary_dir: Application temporary storage root.
        submitted_session_id: Existing session identifier, if provided.

    Returns:
        A new or existing temporary scan session.

    Raises:
        ScanSessionError: If an existing session is invalid or expired.
        OSError: If a new session cannot be created.
    """
    if submitted_session_id is None:
        return create_scan_session(temporary_dir)
    return ScanSession(
        session_id=submitted_session_id,
        directory=get_scan_session_directory(
            temporary_dir,
            submitted_session_id,
        ),
    )


def _capture_scan(
    scan_request: _ScanRequest,
    scan_session: ScanSession,
) -> _ScanResult:
    """Capture one image and create an export for single-page scans.

    Args:
        scan_request: Validated capture settings and workflow.
        scan_session: Temporary directory receiving scan output.

    Returns:
        Session and identifiers for the captured page.

    Raises:
        MessageError: If scan options are invalid.
        ScannerError: If the scanner or image export fails.
    """
    artifact_id = uuid4().hex
    png_path = scan_session.directory / f"{artifact_id}.png"
    scan_to_png(
        scan_request.settings,
        png_path,
        card_mode=scan_request.workflow == "card",
    )
    message = _scan_result_message(scan_request, png_path)
    return _ScanResult(
        session=scan_session,
        artifact_id=artifact_id,
        message=message,
    )


def _scan_result_message(
    scan_request: _ScanRequest,
    png_path: Path,
) -> MessageCode:
    """Export a single-page scan when needed and describe its result.

    Args:
        scan_request: Validated capture settings and workflow.
        png_path: Temporary PNG created by the scanner.

    Returns:
        English API code describing the resulting scan state.

    Raises:
        ScannerError: If exporting a single-page scan fails.
    """
    if scan_request.workflow == "single":
        export_scan(png_path, scan_request.settings)
        return MessageCode.SCAN_COMPLETE
    if scan_request.workflow == "card":
        if scan_request.card_side == "front":
            return MessageCode.FRONT_CAPTURED
        return MessageCode.BACK_CAPTURED
    return MessageCode.PAGE_ADDED


def _remove_new_scan_session(
    settings: AppSettings,
    scan_session: ScanSession,
    *,
    is_new_session: bool,
) -> None:
    """Remove a session created by a failed scan request.

    Args:
        settings: Runtime paths and printer queue configuration.
        scan_session: Session containing the failed scan attempt.
        is_new_session: Whether this request created the session.
    """
    if is_new_session:
        remove_scan_session(settings.temporary_dir, scan_session.session_id)


def _register_composition_route(app: Flask, settings: AppSettings) -> None:
    """Register the scan document composition route.

    Args:
        app: Flask application receiving the route.
        settings: Runtime paths and printer queue configuration.
    """

    @app.post("/api/scans/compose")
    def compose_scans() -> tuple[Response, int]:
        """Create a PDF from a continuous scan or both card sides.

        Returns:
            JSON with the PDF download link or a validation error.
        """
        try:
            session_id = request.form.get("scan_session_id", "")
            scan_session_dir = get_scan_session_directory(
                settings.temporary_dir,
                session_id,
            )
            composition = _parse_scan_composition(
                request.form.get("workflow", ""),
                request.form.getlist("artifact_ids"),
                request.form.get(
                    "resolution",
                    str(constants.DEFAULT_SCAN_RESOLUTION),
                ),
            )
            output_path = _compose_scan_document(
                composition,
                scan_session_dir,
            )
        except ScannerError as err:
            return jsonify(error=err.to_payload()), 500
        except MessageError as err:
            return jsonify(error=err.to_payload()), 400

        output_id = output_path.stem
        return jsonify(
            scan_session_id=session_id,
            artifact_id=output_id,
            download_url=f"/api/download/{session_id}/{output_id}",
            message=message_payload(MessageCode.PDF_READY),
        ), 200


def _parse_scan_composition(
    workflow_value: str,
    artifact_ids: list[str],
    resolution_value: str,
) -> _ScanComposition:
    """Validate workflow, pages, and resolution for PDF composition.

    Args:
        workflow_value: Submitted document composition mode.
        artifact_ids: Submitted scan page identifiers.
        resolution_value: Submitted PDF resolution.

    Returns:
        Validated composition options.

    Raises:
        MessageError: If the workflow, page count, or resolution is invalid.
    """
    if workflow_value not in {"continuous", "card"}:
        raise MessageError(MessageCode.SCAN_WORKFLOW_INVALID)
    if not artifact_ids or len(artifact_ids) > constants.MAX_SCAN_PAGE_COUNT:
        raise MessageError(
            MessageCode.SCAN_PAGE_COUNT_INVALID,
            {"max": constants.MAX_SCAN_PAGE_COUNT},
        )
    if (
        workflow_value == "card"
        and len(artifact_ids) != constants.ID_CARD_PAGE_COUNT
    ):
        raise MessageError(MessageCode.CARD_SIDES_REQUIRED)

    try:
        resolution = int(resolution_value)
    except ValueError as err:
        raise MessageError(
            MessageCode.INTEGER_REQUIRED,
            {"field": "resolution"},
        ) from err
    if resolution not in constants.SCAN_RESOLUTIONS:
        raise MessageError(MessageCode.RESOLUTION_UNAVAILABLE)

    if workflow_value == "continuous":
        workflow: Literal["continuous", "card"] = "continuous"
    else:
        workflow = "card"
    return _ScanComposition(
        workflow=workflow,
        artifact_ids=tuple(artifact_ids),
        resolution=resolution,
    )


def _compose_scan_document(
    composition: _ScanComposition,
    scan_session_dir: Path,
) -> Path:
    """Compose validated scan pages into a PDF file.

    Args:
        composition: Validated workflow, artifact identifiers, and resolution.
        scan_session_dir: Temporary directory containing the page images.

    Returns:
        Path to the composed PDF file.

    Raises:
        MessageError: If a referenced scan page is missing or invalid.
        ScannerError: If PDF composition fails.
    """
    page_paths = [
        _scan_page_path(scan_session_dir, artifact_id)
        for artifact_id in composition.artifact_ids
    ]
    output_path = scan_session_dir / f"{uuid4().hex}.pdf"
    if composition.workflow == "card":
        return compose_id_card(page_paths[0], page_paths[1], output_path)
    return compose_document(
        page_paths,
        output_path,
        composition.resolution,
    )


def _register_artifact_routes(app: Flask, settings: AppSettings) -> None:
    """Register the scan preview and download routes.

    Args:
        app: Flask application receiving the routes.
        settings: Runtime paths and printer queue configuration.
    """
    app.add_url_rule(
        "/api/scans/sessions/<session_id>",
        endpoint="close_scan_session",
        view_func=partial(_close_scan_session, settings),
        methods=["DELETE", "POST"],
    )
    app.add_url_rule(
        "/api/download/<session_id>/<artifact_id>",
        endpoint="download_scan_artifact",
        view_func=partial(_download_scan_artifact, settings),
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/preview/<session_id>/<artifact_id>",
        endpoint="preview_scan_artifact",
        view_func=partial(_preview_scan_artifact, settings),
        methods=["GET"],
    )


def _close_scan_session(
    settings: AppSettings,
    session_id: str,
) -> tuple[Response, int] | Response:
    """Delete a scan session when the browser closes or resets it.

    Args:
        settings: Runtime paths and printer queue configuration.
        session_id: Random identifier returned by the scan endpoint.

    Returns:
        An empty response when the session has been removed.
    """
    try:
        remove_scan_session(settings.temporary_dir, session_id)
    except ScanSessionError as err:
        return jsonify(error=err.to_payload()), 400
    return Response(status=204)


def _download_scan_artifact(
    settings: AppSettings,
    session_id: str,
    artifact_id: str,
) -> Response | tuple[Response, int]:
    """Send the best available output file for one scan artifact.

    Args:
        settings: Runtime paths and printer queue configuration.
        session_id: Scan session containing the requested file.
        artifact_id: Identifier returned by a scan request.

    Returns:
        The requested file or a JSON 404 response.
    """
    if not constants.UUID_HEX_PATTERN.fullmatch(artifact_id):
        error = MessageError(MessageCode.SCAN_ARTIFACT_NOT_FOUND)
        return jsonify(error=error.to_payload()), 404

    try:
        scan_session_dir = get_scan_session_directory(
            settings.temporary_dir,
            session_id,
        )
    except ScanSessionError:
        error = MessageError(MessageCode.SCAN_ARTIFACT_NOT_FOUND)
        return jsonify(error=error.to_payload()), 404

    for suffix in (".pdf", ".jpg", ".png", ".tif", ".tiff"):
        path = scan_session_dir / f"{artifact_id}{suffix}"
        if path.is_file():
            response = send_file(
                path,
                as_attachment=True,
                download_name=path.name,
            )
            response.headers["Cache-Control"] = "no-store"
            response.call_on_close(
                partial(
                    remove_scan_session,
                    settings.temporary_dir,
                    session_id,
                )
            )
            return response
    error = MessageError(MessageCode.SCAN_ARTIFACT_NOT_FOUND)
    return jsonify(error=error.to_payload()), 404


def _preview_scan_artifact(
    settings: AppSettings,
    session_id: str,
    artifact_id: str,
) -> Response | tuple[Response, int]:
    """Show the PNG preview for a scan artifact in the browser.

    Args:
        settings: Runtime paths and printer queue configuration.
        session_id: Scan session containing the requested image.
        artifact_id: Identifier returned by a scan request.

    Returns:
        An inline PNG response or a JSON 404 response.
    """
    if not constants.UUID_HEX_PATTERN.fullmatch(artifact_id):
        error = MessageError(MessageCode.PREVIEW_NOT_FOUND)
        return jsonify(error=error.to_payload()), 404
    try:
        scan_session_dir = get_scan_session_directory(
            settings.temporary_dir,
            session_id,
        )
    except ScanSessionError:
        error = MessageError(MessageCode.PREVIEW_NOT_FOUND)
        return jsonify(error=error.to_payload()), 404
    path = scan_session_dir / f"{artifact_id}.png"
    if not path.is_file():
        error = MessageError(MessageCode.PREVIEW_NOT_FOUND)
        return jsonify(error=error.to_payload()), 404
    response = send_file(
        path,
        mimetype="image/png",
        as_attachment=False,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _scan_page_path(scan_session_dir: Path, artifact_id: str) -> Path:
    """Return a validated PNG path belonging to a scan artifact.

    Args:
        scan_session_dir: Temporary directory containing scan artifacts.
        artifact_id: Identifier returned by a scan request.

    Returns:
        Path to the existing PNG scan page.

    Raises:
        MessageError: If the identifier is invalid or its image is missing.
    """
    if not constants.UUID_HEX_PATTERN.fullmatch(artifact_id):
        raise MessageError(MessageCode.SCAN_PAGE_UNAVAILABLE)
    path = scan_session_dir / f"{artifact_id}.png"
    if not path.is_file():
        raise MessageError(MessageCode.SCAN_PAGE_UNAVAILABLE)
    return path
