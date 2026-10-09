"""Capture scans through SANE and assemble output documents.

The module supports single pages, continuous documents, and ID-card layouts.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, ImageEnhance, ImageOps

from scanner_app import constants
from scanner_app.messages import MessageCode, MessageError
from scanner_app.processes import ProcessTimeoutError, run_process

OutputFormat = Literal["pdf", "png", "jpeg"]


class ScannerError(MessageError):
    """Report a scanner discovery or capture failure.

    The exception carries an English API code for the web client.
    """


@dataclass(frozen=True, slots=True)
class ScanSettings:
    """Store validated scan options selected in the web form.

    The values are normalized for the Brother SANE backend and output tools.

    Attributes:
        resolution: Scan resolution in dots per inch.
        mode: SANE mode name used by the Brother backend.
        paper_size: Scanner-bed crop preset.
        brightness: Brightness adjustment applied to the captured image.
        contrast: Contrast adjustment applied to the captured image.
        remove_background: Whether to whiten near-white pixels after scanning.
        background_level: Strength of the background whitening threshold.
        output_format: File format selected for a single scan.
        jpeg_quality: Compression quality for JPEG output.
    """

    resolution: int
    mode: str
    paper_size: str
    brightness: int
    contrast: int
    remove_background: bool
    background_level: int
    output_format: OutputFormat
    jpeg_quality: int


def parse_scan_settings(form: Mapping[str, str]) -> ScanSettings:
    """Validate scan options and translate the selected mode for SANE.

    Args:
        form: Submitted scan options from the web request.

    Returns:
        Validated settings ready for the scanner backend.

    Raises:
        MessageError: If an option is unsupported or outside its allowed range.
    """
    resolution = _parse_int(
        form.get("resolution"),
        constants.DEFAULT_SCAN_RESOLUTION,
        "resolution",
    )
    if resolution not in constants.SCAN_RESOLUTIONS:
        raise MessageError(MessageCode.RESOLUTION_UNAVAILABLE)

    mode_key = form.get("scan_mode", "color")
    if mode_key not in constants.SCAN_MODES:
        raise MessageError(MessageCode.SCAN_MODE_INVALID)

    paper_size = form.get("paper_size", "A4")
    if paper_size not in constants.PAPER_DIMENSIONS_MM:
        raise MessageError(MessageCode.DOCUMENT_SIZE_INVALID)

    brightness = _parse_int(form.get("brightness"), 0, "brightness")
    contrast = _parse_int(form.get("contrast"), 0, "contrast")
    background_level = _parse_int(
        form.get("background_level"),
        constants.DEFAULT_BACKGROUND_LEVEL,
        "backgroundLevel",
    )
    jpeg_quality = _parse_int(
        form.get("jpeg_quality"),
        constants.DEFAULT_JPEG_QUALITY,
        "jpegQuality",
    )
    if not (
        constants.MIN_BRIGHTNESS <= brightness <= constants.MAX_BRIGHTNESS
    ) or not (
        constants.MIN_BRIGHTNESS <= contrast <= constants.MAX_BRIGHTNESS
    ):
        raise MessageError(
            MessageCode.BRIGHTNESS_CONTRAST_RANGE,
            {
                "min": constants.MIN_BRIGHTNESS,
                "max": constants.MAX_BRIGHTNESS,
            },
        )
    if not (
        constants.MIN_BACKGROUND_LEVEL
        <= background_level
        <= constants.MAX_BACKGROUND_LEVEL
    ):
        raise MessageError(
            MessageCode.BACKGROUND_LEVEL_RANGE,
            {
                "min": constants.MIN_BACKGROUND_LEVEL,
                "max": constants.MAX_BACKGROUND_LEVEL,
            },
        )
    if not (
        constants.MIN_JPEG_QUALITY
        <= jpeg_quality
        <= constants.MAX_JPEG_QUALITY
    ):
        raise MessageError(
            MessageCode.JPEG_QUALITY_RANGE,
            {
                "min": constants.MIN_JPEG_QUALITY,
                "max": constants.MAX_JPEG_QUALITY,
            },
        )

    output_format_value = form.get(
        "output_format",
        constants.DEFAULT_SCAN_OUTPUT_FORMAT,
    )
    if output_format_value == "pdf":
        output_format: OutputFormat = "pdf"
    elif output_format_value == "png":
        output_format = "png"
    elif output_format_value == "jpeg":
        output_format = "jpeg"
    else:
        raise MessageError(MessageCode.SCAN_FORMAT_INVALID)

    return ScanSettings(
        resolution=resolution,
        mode=constants.SCAN_MODES[mode_key],
        paper_size=paper_size,
        brightness=brightness,
        contrast=contrast,
        remove_background=_checked(form.get("remove_background")),
        background_level=background_level,
        output_format=output_format,
        jpeg_quality=jpeg_quality,
    )


def list_scanners() -> list[str]:
    """Return scanner identifiers currently visible to SANE.

    Returns:
        Device identifiers found by scanimage, or an empty list on failure.
    """
    try:
        result = run_process(
            constants.SCANIMAGE_EXECUTABLE,
            ["-L"],
            timeout_seconds=constants.SCANNER_DISCOVERY_TIMEOUT_SECONDS,
        )
    except ProcessTimeoutError:
        return []
    except FileNotFoundError:
        return []

    output = f"{result.stdout}\n{result.stderr}"
    return re.findall(r"device [`']([^`']+)[`']", output)


def scan_to_png(
    settings: ScanSettings,
    destination: Path,
    *,
    card_mode: bool = False,
) -> Path:
    """Scan one page into a PNG file.

    Args:
        settings: Validated scan options.
        destination: PNG path to create for the captured page.
        card_mode: Whether to use the ID-card bed dimensions.

    Returns:
        The path to the captured PNG page.

    Raises:
        ScannerError: If no scanner is visible or the scan fails.
    """
    devices = list_scanners()
    if not devices:
        raise ScannerError(MessageCode.SCANNER_NOT_FOUND)

    width_mm, height_mm = (
        constants.CARD_DIMENSIONS_MM
        if card_mode
        else constants.PAPER_DIMENSIONS_MM[settings.paper_size]
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    arguments = [
        "--device-name",
        devices[0],
        "--format=png",
        f"--output-file={destination}",
        f"--resolution={settings.resolution}",
        f"--mode={settings.mode}",
        "-x",
        str(width_mm),
        "-y",
        str(height_mm),
    ]
    try:
        result = run_process(
            constants.SCANIMAGE_EXECUTABLE,
            arguments,
            timeout_seconds=constants.SCAN_CAPTURE_TIMEOUT_SECONDS,
        )
    except ProcessTimeoutError as err:
        destination.unlink(missing_ok=True)
        raise ScannerError(MessageCode.SCAN_TIMEOUT) from err
    except FileNotFoundError as err:
        destination.unlink(missing_ok=True)
        raise ScannerError(MessageCode.SANE_SCANIMAGE_MISSING) from err

    if result.return_code != 0 or not destination.is_file():
        destination.unlink(missing_ok=True)
        raise ScannerError(MessageCode.SCAN_CAPTURE_FAILED)

    if settings.brightness or settings.contrast:
        _adjust_brightness_contrast(
            destination,
            settings.brightness,
            settings.contrast,
        )
    if settings.remove_background:
        _remove_background(destination, settings.background_level)
    return destination


def _adjust_brightness_contrast(
    image_path: Path,
    brightness: int,
    contrast: int,
) -> None:
    """Apply brightness and contrast after the scan is captured.

    Args:
        image_path: PNG file to modify in place.
        brightness: Brightness adjustment from -50 through 50.
        contrast: Contrast adjustment from -50 through 50.

    Raises:
        ScannerError: If the image cannot be adjusted or rewritten.
    """
    try:
        with Image.open(image_path) as source:
            adjusted = source.convert("RGB")
        try:
            if brightness:
                brightened = ImageEnhance.Brightness(adjusted).enhance(
                    (constants.PERCENTAGE_BASE + brightness)
                    / constants.PERCENTAGE_BASE
                )
                adjusted.close()
                adjusted = brightened
            if contrast:
                contrasted = ImageEnhance.Contrast(adjusted).enhance(
                    (constants.PERCENTAGE_BASE + contrast)
                    / constants.PERCENTAGE_BASE
                )
                adjusted.close()
                adjusted = contrasted
            adjusted.save(image_path, format="PNG")
        finally:
            adjusted.close()
    except OSError as err:
        raise ScannerError(MessageCode.IMAGE_ADJUSTMENT_FAILED) from err


def export_scan(png_path: Path, settings: ScanSettings) -> Path:
    """Create the requested output next to its PNG preview.

    Args:
        png_path: Source image produced by the scanner.
        settings: Validated scan options, including output format.

    Returns:
        The source PNG path or the generated JPEG or PDF path.

    Raises:
        ScannerError: If the requested file cannot be generated.
    """
    if settings.output_format == "png":
        return png_path

    extension = ".jpg" if settings.output_format == "jpeg" else ".pdf"
    output_path = png_path.with_suffix(extension)
    try:
        with Image.open(png_path) as source:
            converted = source.convert("RGB")
            if settings.output_format == "pdf":
                converted.save(
                    output_path,
                    format="PDF",
                    resolution=settings.resolution,
                )
            else:
                converted.save(
                    output_path,
                    format="JPEG",
                    quality=settings.jpeg_quality,
                    optimize=True,
                )
            converted.close()
    except OSError as err:
        raise ScannerError(MessageCode.SCAN_FILE_GENERATION_FAILED) from err
    return output_path


def compose_document(
    page_paths: list[Path],
    output_path: Path,
    resolution: int,
) -> Path:
    """Assemble scanned PNG pages into a multipage PDF document.

    Args:
        page_paths: PNG files in the order they should appear in the PDF.
        output_path: Destination path for the combined PDF.
        resolution: Output resolution in dots per inch.

    Returns:
        The path to the generated PDF.

    Raises:
        MessageError: If no pages were supplied.
        ScannerError: If one of the pages cannot be converted.
    """
    if not page_paths:
        raise MessageError(MessageCode.SCAN_PAGE_REQUIRED)

    pages: list[Image.Image] = []
    try:
        for page_path in page_paths:
            with Image.open(page_path) as source:
                pages.append(source.convert("RGB"))
        pages[0].save(
            output_path,
            format="PDF",
            save_all=True,
            append_images=pages[1:],
            resolution=resolution,
        )
    except OSError as err:
        raise ScannerError(MessageCode.SCAN_DOCUMENT_COMBINE_FAILED) from err
    finally:
        for page in pages:
            page.close()
    return output_path


def compose_id_card(
    front_path: Path,
    back_path: Path,
    output_path: Path,
) -> Path:
    """Place both sides of an ID card on one A4 page.

    Args:
        front_path: PNG scan of the front of the card.
        back_path: PNG scan of the back of the card.
        output_path: Destination path for the composed PDF.

    Returns:
        The path to the generated PDF.

    Raises:
        ScannerError: If either card image cannot be composed.
    """
    resolution = constants.DEFAULT_SCAN_RESOLUTION
    page_width = round(
        constants.A4_DIMENSIONS_MM[0]
        * resolution
        / constants.MILLIMETERS_PER_INCH
    )
    page_height = round(
        constants.A4_DIMENSIONS_MM[1]
        * resolution
        / constants.MILLIMETERS_PER_INCH
    )
    card_width = round(
        constants.CARD_DIMENSIONS_MM[0]
        * resolution
        / constants.MILLIMETERS_PER_INCH
    )
    card_height = round(
        constants.CARD_DIMENSIONS_MM[1]
        * resolution
        / constants.MILLIMETERS_PER_INCH
    )
    canvas = Image.new("RGB", (page_width, page_height), "white")

    try:
        _paste_card(
            canvas,
            front_path,
            card_width,
            card_height,
            page_height // 3,
        )
        _paste_card(
            canvas,
            back_path,
            card_width,
            card_height,
            (page_height * 2) // 3,
        )
        canvas.save(output_path, format="PDF", resolution=resolution)
    except OSError as err:
        raise ScannerError(MessageCode.CARD_PDF_CREATION_FAILED) from err
    finally:
        canvas.close()
    return output_path


def _paste_card(
    canvas: Image.Image,
    source_path: Path,
    card_width: int,
    card_height: int,
    center_y: int,
) -> None:
    """Resize a scanned card and center it on the A4 canvas.

    Args:
        canvas: Destination A4 image.
        source_path: Scanned card image to place.
        card_width: Target card width in pixels.
        card_height: Target card height in pixels.
        center_y: Vertical center position on the destination canvas.

    Raises:
        OSError: If the source image cannot be opened or pasted.
    """
    with Image.open(source_path) as source:
        rgb_source = source.convert("RGB")
        card = ImageOps.contain(rgb_source, (card_width, card_height))
        rgb_source.close()
    position = ((canvas.width - card.width) // 2, center_y - card.height // 2)
    canvas.paste(card, position)
    card.close()


def _remove_background(image_path: Path, level: int) -> None:
    """Turn near-white pixels into white using the selected strength.

    Args:
        image_path: PNG file to modify in place.
        level: Background removal strength from 1 through 100.

    Raises:
        ScannerError: If the image cannot be read or rewritten.
    """
    try:
        with Image.open(image_path) as source:
            image = source.convert("RGB")
        grayscale = ImageOps.grayscale(image)
        threshold = 255 - round(level * 0.8)
        mask = Image.eval(
            grayscale,
            lambda value: 255 if value >= threshold else 0,
        )
        white = Image.new("RGB", image.size, "white")
        result = Image.composite(white, image, mask)
        result.save(image_path, format="PNG")
        image.close()
        grayscale.close()
        mask.close()
        white.close()
        result.close()
    except OSError as err:
        raise ScannerError(MessageCode.BACKGROUND_REMOVAL_FAILED) from err


def _parse_int(value: str | None, default: int, field: str) -> int:
    """Parse an integer form value and preserve its API field identifier.

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


def _checked(value: str | None) -> bool:
    """Interpret common HTML checkbox values.

    Args:
        value: Submitted checkbox value or None when unchecked.

    Returns:
        True when the value represents a checked box.
    """
    return value in {"1", "true", "on", "yes"}
