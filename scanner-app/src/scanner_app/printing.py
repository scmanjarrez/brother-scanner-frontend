"""Validate print requests and submit jobs to CUPS.

This module maps web form options to the Brother printer driver and prepares
optional PDF overlays before submitting uploads.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from PIL import Image, ImageSequence
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from reportlab.lib import colors
from reportlab.pdfgen.canvas import Canvas
from werkzeug.datastructures import FileStorage

from scanner_app import constants
from scanner_app.messages import MessageCode, MessageError
from scanner_app.processes import (
    ProcessResult,
    ProcessTimeoutError,
    run_process,
)


class PrinterError(MessageError):
    """Report a printer queue or print job failure.

    The exception carries an English API code for the web client.
    """


class _CanvasAdapter:
    """Expose ReportLab operations through Python-style method names.

    The adapter keeps ReportLab's camelCase API behind typed methods.

    Attributes:
        _canvas: ReportLab canvas wrapped by this adapter.
    """

    _canvas: Canvas

    def __init__(self, canvas: Canvas) -> None:
        """Store the ReportLab canvas to wrap.

        Args:
            canvas: ReportLab canvas instance used to draw an overlay.
        """
        self._canvas = canvas

    def save_state(self) -> None:
        """Save the current graphics state.

        Delegates the operation to the wrapped ReportLab canvas.
        """
        self._canvas.saveState()

    def set_fill_alpha(self, alpha: float) -> None:
        """Set fill transparency for later drawing operations.

        Args:
            alpha: Fill opacity between zero and one.
        """
        self._canvas.setFillAlpha(alpha)

    def set_fill_color(self, color: colors.Color) -> None:
        """Set the fill color for later drawing operations.

        Args:
            color: ReportLab color used for the overlay text.
        """
        self._canvas.setFillColor(color)

    def set_font(self, font_name: str, size: float) -> None:
        """Set the font and size for later drawing operations.

        Args:
            font_name: Built-in PDF font name.
            size: Font size in points.
        """
        self._canvas.setFont(font_name, size)

    def translate(self, dx: float, dy: float) -> None:
        """Move the PDF canvas origin.

        Args:
            dx: Horizontal movement in points.
            dy: Vertical movement in points.
        """
        self._canvas.translate(dx, dy)

    def rotate(self, degrees: float) -> None:
        """Rotate the PDF canvas origin.

        Args:
            degrees: Clockwise rotation angle in degrees.
        """
        self._canvas.rotate(degrees)

    def draw_centered_string(self, x: float, y: float, text: str) -> None:
        """Draw text centered at the supplied coordinates.

        Args:
            x: Horizontal center in points.
            y: Baseline position in points.
            text: Text to draw.
        """
        self._canvas.drawCentredString(x, y, text)

    def draw_string(self, x: float, y: float, text: str) -> None:
        """Draw text from the supplied baseline coordinates.

        Args:
            x: Left position in points.
            y: Baseline position in points.
            text: Text to draw.
        """
        self._canvas.drawString(x, y, text)

    def draw_right_string(self, x: float, y: float, text: str) -> None:
        """Draw text right-aligned at the supplied coordinates.

        Args:
            x: Right position in points.
            y: Baseline position in points.
            text: Text to draw.
        """
        self._canvas.drawRightString(x, y, text)

    def restore_state(self) -> None:
        """Restore the graphics state saved by save_state.

        Delegates the operation to the wrapped ReportLab canvas.
        """
        self._canvas.restoreState()

    def save(self) -> None:
        """Write the completed PDF to its destination.

        Delegates the operation to the wrapped ReportLab canvas.
        """
        self._canvas.save()


@dataclass(frozen=True, slots=True)
class PrintSettings:
    """Validated print options supported by the Brother CUPS driver.

    Each field contains a normalized value that can be passed to CUPS.

    Attributes:
        paper_size: CUPS paper name.
        orientation: Page orientation requested by the user.
        copies: Number of copies to print.
        collate: Whether to collate multiple copies.
        media_type: Paper stock setting exposed by the Brother PPD.
        resolution: Printer resolution in dots per inch.
        print_quality: Driver optimization for text or graphics.
        pages_per_sheet: Number of input pages placed on one paper sheet.
        page_order: Reading order used when multiple pages share a sheet.
        page_border: Border style between reduced pages.
        scale_mode: Whether to keep scale, fit to paper, or use a percentage.
        scale_percent: Manual scale percentage when scale_mode is custom.
        reverse_order: Whether to print pages in reverse order.
        toner_save: Whether to request the driver's toner-saving mode.
        watermark_text: Optional watermark printed across each page.
        header_footer: Whether to add filename, date, and page numbers.
    """

    paper_size: str
    orientation: str
    copies: int
    collate: bool
    media_type: str
    resolution: int
    print_quality: str
    pages_per_sheet: int
    page_order: str
    page_border: str
    scale_mode: str
    scale_percent: int
    reverse_order: bool
    toner_save: bool
    watermark_text: str
    header_footer: bool


@dataclass(frozen=True, slots=True)
class _OverlaySettings:
    """Store values needed to draw one PDF page overlay.

    Attributes:
        page_width: Width of the source page in points.
        page_height: Height of the source page in points.
        page_number: One-based page number within the document.
        page_count: Total number of pages in the document.
        document_name: Filename displayed in the page header.
        watermark_text: Watermark text, or an empty string to omit it.
        header_footer: Whether to add the filename, date, and page count.
    """

    page_width: float
    page_height: float
    page_number: int
    page_count: int
    document_name: str
    watermark_text: str
    header_footer: bool


def parse_print_settings(form: Mapping[str, str]) -> PrintSettings:
    """Validate the print form and return normalized settings.

    Args:
        form: Submitted print options from the web request.

    Returns:
        Validated settings ready for CUPS submission.

    Raises:
        MessageError: If a print option is unsupported or out of range.
    """
    paper_size = _choice(
        form.get("paper_size"),
        constants.PRINT_PAPER_SIZES,
        constants.DEFAULT_PRINT_PAPER_SIZE,
    )
    orientation = _choice(
        form.get("orientation"),
        constants.PRINT_ORIENTATIONS,
        constants.DEFAULT_PRINT_ORIENTATION,
    )
    media_type = _choice(
        form.get("media_type"),
        constants.PRINT_MEDIA_TYPES,
        constants.DEFAULT_PRINT_MEDIA_TYPE,
    )
    resolution = _integer_choice(
        form.get("resolution"),
        constants.PRINT_RESOLUTIONS,
        constants.DEFAULT_PRINT_RESOLUTION,
        "resolution",
    )
    print_quality = _choice(
        form.get("print_quality"),
        constants.PRINT_QUALITIES,
        constants.DEFAULT_PRINT_QUALITY,
    )
    pages_per_sheet = _integer_choice(
        form.get("pages_per_sheet"),
        constants.PRINT_PAGES_PER_SHEET,
        constants.DEFAULT_PRINT_PAGES_PER_SHEET,
        "pagesPerSheet",
    )
    page_order = _choice(
        form.get("page_order"),
        constants.PRINT_PAGE_ORDERS,
        constants.DEFAULT_PRINT_PAGE_ORDER,
    )
    page_border = _choice(
        form.get("page_border"),
        constants.PRINT_PAGE_BORDERS,
        constants.DEFAULT_PRINT_PAGE_BORDER,
    )
    scale_mode = _choice(
        form.get("scale_mode"),
        constants.PRINT_SCALE_MODES,
        constants.DEFAULT_PRINT_SCALE_MODE,
    )
    scale_percent = _integer(
        form.get("scale_percent"),
        constants.DEFAULT_PRINT_SCALE_PERCENT,
        "scale",
    )
    if not (
        constants.MIN_PRINT_SCALE_PERCENT
        <= scale_percent
        <= constants.MAX_PRINT_SCALE_PERCENT
    ):
        raise MessageError(
            MessageCode.SCALE_RANGE,
            {
                "min": constants.MIN_PRINT_SCALE_PERCENT,
                "max": constants.MAX_PRINT_SCALE_PERCENT,
            },
        )

    copies = _integer(
        form.get("copies"),
        constants.DEFAULT_PRINT_COPIES,
        "copies",
    )
    if not (
        constants.MIN_PRINT_COPIES <= copies <= constants.MAX_PRINT_COPIES
    ):
        raise MessageError(
            MessageCode.COPIES_RANGE,
            {
                "min": constants.MIN_PRINT_COPIES,
                "max": constants.MAX_PRINT_COPIES,
            },
        )

    watermark_text = (form.get("watermark_text") or "").strip()
    if len(watermark_text) > constants.MAX_WATERMARK_LENGTH:
        raise MessageError(
            MessageCode.WATERMARK_LENGTH,
            {"max": constants.MAX_WATERMARK_LENGTH},
        )
    if _checked(form.get("watermark")) and not watermark_text:
        raise MessageError(MessageCode.WATERMARK_REQUIRED)

    return PrintSettings(
        paper_size=paper_size,
        orientation=orientation,
        copies=copies,
        collate=_checked(form.get("collate")),
        media_type=media_type,
        resolution=resolution,
        print_quality=print_quality,
        pages_per_sheet=pages_per_sheet,
        page_order=page_order,
        page_border=page_border,
        scale_mode=scale_mode,
        scale_percent=scale_percent,
        reverse_order=_checked(form.get("reverse_order")),
        toner_save=_checked(form.get("toner_save")),
        watermark_text=(
            watermark_text if _checked(form.get("watermark")) else ""
        ),
        header_footer=_checked(form.get("header_footer")),
    )


def submit_print_job(
    upload: FileStorage,
    settings: PrintSettings,
    queue: str,
    *,
    temporary_root: Path,
) -> str:
    """Submit an uploaded document to the configured CUPS queue.

    Converts supported raster files to PDF when overlays are requested, then
    removes temporary files after CUPS accepts or rejects the job.

    Args:
        upload: Uploaded PDF or raster document.
        settings: Validated print options.
        queue: CUPS destination queue name.
        temporary_root: Private application temporary directory.

    Returns:
        The CUPS job identifier, or an empty string if unavailable.

    Raises:
        MessageError: If the upload is missing or has an unsupported format.
        PrinterError: If the file cannot be prepared or CUPS rejects the job.
    """
    original_name = upload.filename
    if not original_name:
        raise MessageError(MessageCode.PRINT_FILE_REQUIRED)

    suffix = Path(original_name).suffix.lower()
    if suffix not in constants.PRINT_ALLOWED_SUFFIXES:
        raise MessageError(MessageCode.UNSUPPORTED_PRINT_FORMAT)

    try:
        with TemporaryDirectory(
            prefix="brother-print-",
            dir=temporary_root,
        ) as directory_name:
            temporary_dir = Path(directory_name)
            temporary_path = temporary_dir / f"{uuid4().hex}{suffix}"
            upload.save(temporary_path)
            prepared_path = _prepare_upload_overlay(
                temporary_path,
                temporary_dir,
                Path(original_name).name,
                settings,
            )
            print_path = prepared_path or temporary_path
            result = _submit_cups_job(queue, settings, print_path)
    except OSError as err:
        raise PrinterError(MessageCode.PRINT_PREPARATION_FAILED) from err

    if result.return_code != 0:
        raise PrinterError(MessageCode.CUPS_REJECTED_JOB)

    match = re.search(
        r"request id is\s+(\S+)",
        result.stdout,
        re.IGNORECASE,
    )
    return match.group(1) if match else ""


def _prepare_upload_overlay(
    source_path: Path,
    upload_dir: Path,
    document_name: str,
    settings: PrintSettings,
) -> Path | None:
    """Prepare an upload when print overlays are requested.

    Args:
        source_path: Original upload saved to the temporary directory.
        upload_dir: Directory where the prepared PDF should be written.
        document_name: Original filename shown in the page header.
        settings: Validated print options.

    Returns:
        The prepared PDF path, or None when no overlay is requested.
    """
    if not settings.watermark_text and not settings.header_footer:
        return None
    output_path = upload_dir / f"{uuid4().hex}-ready.pdf"
    return _prepare_print_file(
        source_path,
        output_path,
        document_name,
        settings.watermark_text,
        header_footer=settings.header_footer,
    )


def _build_print_command(
    queue: str,
    settings: PrintSettings,
    print_path: Path,
) -> list[str]:
    """Build arguments for one CUPS print job.

    Args:
        queue: CUPS destination queue name.
        settings: Validated print options.
        print_path: PDF or raster file sent to CUPS.

    Returns:
        Arguments passed separately to the fixed CUPS executable.
    """
    orientation_code = 3 if settings.orientation == "portrait" else 4
    options = [
        f"PageSize={settings.paper_size}",
        f"orientation-requested={orientation_code}",
        f"BRMediaType={settings.media_type}",
        f"BRResolution={settings.resolution}dpi",
        f"BRPrintQuality={settings.print_quality}",
        f"number-up={settings.pages_per_sheet}",
        f"number-up-layout={settings.page_order}",
        f"page-border={settings.page_border}",
        f"Collate={'True' if settings.collate else 'False'}",
    ]
    if settings.scale_mode == "fit":
        options.append("fit-to-page")
    elif settings.scale_mode == "custom":
        options.append(f"scaling={settings.scale_percent}")
    if settings.reverse_order:
        options.append("outputorder=reverse")
    if settings.toner_save:
        options.append("TonerSave=On")

    command = ["-d", queue, "-n", str(settings.copies)]
    for option in options:
        command.extend(["-o", option])
    command.append(str(print_path))
    return command


def _submit_cups_job(
    queue: str,
    settings: PrintSettings,
    print_path: Path,
) -> ProcessResult:
    """Run one CUPS print command and translate process failures.

    Args:
        queue: CUPS destination queue name.
        settings: Validated print options.
        print_path: PDF or raster file sent to CUPS.

    Returns:
        Exit status and captured CUPS output.

    Raises:
        PrinterError: If CUPS is unavailable or times out.
    """
    arguments = _build_print_command(queue, settings, print_path)
    try:
        result = run_process(
            constants.LP_EXECUTABLE,
            arguments,
            timeout_seconds=constants.PRINT_JOB_TIMEOUT_SECONDS,
        )
    except ProcessTimeoutError as err:
        raise PrinterError(MessageCode.CUPS_TIMEOUT) from err
    except FileNotFoundError as err:
        raise PrinterError(MessageCode.CUPS_LP_MISSING) from err
    except OSError as err:
        raise PrinterError(MessageCode.PRINT_JOB_FAILED) from err
    return result


def _prepare_print_file(
    source_path: Path,
    output_path: Path,
    document_name: str,
    watermark_text: str,
    *,
    header_footer: bool,
) -> Path:
    """Convert an upload and apply requested page overlays.

    Args:
        source_path: Original PDF or raster document path.
        output_path: Destination path for the prepared PDF.
        document_name: Original filename used by the page header.
        watermark_text: Text to draw diagonally on each page, if non-empty.
        header_footer: Whether to add the filename, date, and page count.

    Returns:
        The path to the prepared PDF.

    Raises:
        PrinterError: If the input PDF cannot be read or prepared.
    """
    converted_path: Path | None = None
    try:
        pdf_source = source_path
        if source_path.suffix.lower() != ".pdf":
            converted_path = output_path.with_name(
                f"{output_path.stem}-source.pdf"
            )
            _convert_image_to_pdf(source_path, converted_path)
            pdf_source = converted_path

        writer = PdfWriter()
        with pdf_source.open("rb") as source_file:
            reader = PdfReader(source_file)
            if reader.is_encrypted:
                raise PrinterError(MessageCode.PROTECTED_PDF)
            page_count = len(reader.pages)
            for page_number, page in enumerate(reader.pages, start=1):
                page_width = float(page.mediabox.width)
                page_height = float(page.mediabox.height)
                overlay = _make_overlay(
                    _OverlaySettings(
                        page_width=page_width,
                        page_height=page_height,
                        page_number=page_number,
                        page_count=page_count,
                        document_name=document_name,
                        watermark_text=watermark_text,
                        header_footer=header_footer,
                    )
                )
                try:
                    overlay_reader = PdfReader(overlay)
                    page.merge_page(overlay_reader.pages[0])
                    writer.add_page(page)
                finally:
                    overlay.close()
        with output_path.open("wb") as output_file:
            writer.write(output_file)
    except (OSError, PdfReadError, ValueError) as err:
        raise PrinterError(MessageCode.PRINT_OVERLAY_FAILED) from err
    finally:
        if converted_path is not None:
            converted_path.unlink(missing_ok=True)
    return output_path


def _convert_image_to_pdf(source_path: Path, output_path: Path) -> None:
    """Convert a raster upload, including multipage TIFF, to PDF.

    Args:
        source_path: Source image path.
        output_path: Destination PDF path.

    Raises:
        PrinterError: If the source has no frames or cannot be converted.
    """
    pages: list[Image.Image] = []
    try:
        with Image.open(source_path) as source:
            pages.extend(
                frame.convert("RGB")
                for frame in ImageSequence.Iterator(source)
            )
        if not pages:
            raise PrinterError(MessageCode.IMAGE_HAS_NO_PRINTABLE_PAGES)
        pages[0].save(
            output_path,
            format="PDF",
            save_all=True,
            append_images=pages[1:],
            resolution=150,
        )
    except (OSError, ValueError) as err:
        raise PrinterError(MessageCode.IMAGE_TO_PDF_FAILED) from err
    finally:
        for page in pages:
            page.close()


def _make_overlay(settings: _OverlaySettings) -> BytesIO:
    """Draw watermark and header or footer text on one PDF page.

    Args:
        settings: Page dimensions and overlay content.

    Returns:
        A rewound in-memory PDF containing the overlay page.
    """
    buffer = BytesIO()
    page = _CanvasAdapter(
        Canvas(
            buffer,
            pagesize=(settings.page_width, settings.page_height),
            pageCompression=1,
        ),
    )
    if settings.watermark_text:
        page.save_state()
        page.set_fill_alpha(0.15)
        page.set_fill_color(colors.HexColor("#334155"))
        page.set_font(
            "Helvetica-Bold",
            max(24, min(settings.page_width, settings.page_height) * 0.08),
        )
        page.translate(settings.page_width / 2, settings.page_height / 2)
        page.rotate(35)
        page.draw_centered_string(
            0,
            0,
            _pdf_text(settings.watermark_text),
        )
        page.restore_state()
    if settings.header_footer:
        page.save_state()
        page.set_fill_alpha(1)
        page.set_fill_color(colors.HexColor("#475569"))
        page.set_font("Helvetica", 8)
        margin = 24
        footer_y = max(12, margin)
        header_y = settings.page_height - margin
        page.draw_string(
            margin,
            header_y,
            _pdf_text(settings.document_name[:72]),
        )
        page.draw_right_string(
            settings.page_width - margin,
            header_y,
            datetime.now().astimezone().strftime("%d/%m/%Y"),
        )
        page.draw_centered_string(
            settings.page_width / 2,
            footer_y,
            f"{settings.page_number} / {settings.page_count}",
        )
        page.restore_state()
    page.save()
    _ = buffer.seek(0)
    return buffer


def _pdf_text(value: str) -> str:
    """Replace characters outside the built-in PDF font encoding.

    Args:
        value: Text to normalize for the standard PDF fonts.

    Returns:
        Text encoded with Latin-1 replacement for unsupported characters.
    """
    return value.encode("latin-1", "replace").decode("latin-1")


def get_printer_status(queue: str) -> bool:
    """Inspect a CUPS queue and report whether it is ready.

    Args:
        queue: CUPS destination queue name.

    Returns:
        True when the queue is active and can accept print jobs.
    """
    try:
        result = run_process(
            constants.LPSTAT_EXECUTABLE,
            ["-p", queue, "-l"],
            timeout_seconds=constants.PRINTER_STATUS_TIMEOUT_SECONDS,
        )
    except ProcessTimeoutError:
        return False
    except FileNotFoundError:
        return False

    if result.return_code != 0:
        return False
    output = result.stdout.strip()
    return "disabled" not in output.lower() and "stopped" not in output.lower()


def _choice(value: str | None, choices: frozenset[str], default: str) -> str:
    """Return a form value only when it belongs to the allowed set.

    Args:
        value: Submitted string or None when the field was omitted.
        choices: Allowed values for the form field.
        default: Value used when the field is omitted.

    Returns:
        The submitted value or its default.

    Raises:
        MessageError: If the submitted value is outside the allowed set.
    """
    selected = value if value is not None else default
    if selected not in choices:
        raise MessageError(MessageCode.INVALID_PRINT_OPTION)
    return selected


def _integer(value: str | None, default: int, field: str) -> int:
    """Parse an integer setting with a user-facing validation error.

    Args:
        value: Submitted integer text or None when the field was omitted.
        default: Value used when the field is omitted.
        field: English API identifier for the field named in the error.

    Returns:
        The parsed integer or its default.

    Raises:
        MessageError: If the submitted value is not an integer.
    """
    try:
        return int(value) if value is not None else default
    except ValueError as err:
        raise MessageError(
            MessageCode.INTEGER_REQUIRED,
            {"field": field},
        ) from err


def _integer_choice(
    value: str | None,
    choices: frozenset[int],
    default: int,
    field: str,
) -> int:
    """Parse an integer supported by the printer driver.

    Args:
        value: Submitted integer text or None when the field was omitted.
        choices: Allowed integer values for the form field.
        default: Value used when the field is omitted.
        field: English API identifier for the field named in the error.

    Returns:
        The parsed supported integer.

    Raises:
        MessageError: If the value is not an integer or is unsupported.
    """
    selected = _integer(value, default, field)
    if selected not in choices:
        raise MessageError(
            MessageCode.FIELD_UNAVAILABLE,
            {"field": field},
        )
    return selected


def _checked(value: str | None) -> bool:
    """Interpret common HTML checkbox values.

    Args:
        value: Submitted checkbox value or None when unchecked.

    Returns:
        True when the value represents a checked box.
    """
    return value in {"1", "true", "on", "yes"}
