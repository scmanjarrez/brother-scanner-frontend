"""Define shared limits, defaults, and device values.

Each module-level constant has an attribute docstring describing its purpose.
"""

import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

UUID_HEX_PATTERN: Final[re.Pattern[str]] = re.compile(r"[0-9a-f]{32}")
"""Match hexadecimal UUID identifiers used for sessions and scan artifacts."""

SCAN_SESSION_IDLE_SECONDS: Final[int] = 60 * 60
"""Set how long an inactive scan session remains on disk."""

PRIVATE_DIRECTORY_MODE: Final[int] = 0o700
"""Restrict temporary document directories to the application user."""

TEMPORARY_DIRECTORY_NAME: Final[str] = "brother-scanner"
"""Name the application directory under the system temporary root."""

DEFAULT_PRINTER_QUEUE: Final[str] = "brother"
"""Select the CUPS queue name when no environment override is set."""

DEFAULT_MAX_UPLOAD_MB: Final[int] = 30
"""Set the maximum print upload size when no environment override is set."""

BYTES_PER_MEGABYTE: Final[int] = 1024 * 1024
"""Convert the configured upload limit from mebibytes to bytes."""

SCAN_RESOLUTIONS: Final[frozenset[int]] = frozenset(
    {100, 150, 200, 300, 400, 600, 1200}
)
"""List scan resolutions supported by the Brother SANE driver."""

SCANIMAGE_EXECUTABLE: Final[str] = "/usr/bin/scanimage"
"""Locate the SANE command used to discover and capture scans."""

SCANNER_DISCOVERY_TIMEOUT_SECONDS: Final[int] = 15
"""Limit the time spent discovering scanners through SANE."""

SCAN_CAPTURE_TIMEOUT_SECONDS: Final[int] = 240
"""Limit the time spent capturing a page from the flatbed scanner."""

DEFAULT_SCAN_RESOLUTION: Final[int] = 300
"""Set the default resolution for scans and composed scan documents."""

MIN_BRIGHTNESS: Final[int] = -50
"""Set the lowest accepted scan brightness adjustment."""

MAX_BRIGHTNESS: Final[int] = 50
"""Set the highest accepted scan brightness adjustment."""

MIN_BACKGROUND_LEVEL: Final[int] = 1
"""Set the lowest accepted strength for background removal."""

MAX_BACKGROUND_LEVEL: Final[int] = 100
"""Set the highest accepted strength for background removal."""

DEFAULT_BACKGROUND_LEVEL: Final[int] = 50
"""Set the default strength used when removing a scan background."""

MIN_JPEG_QUALITY: Final[int] = 40
"""Set the lowest accepted JPEG output quality."""

MAX_JPEG_QUALITY: Final[int] = 100
"""Set the highest accepted JPEG output quality."""

DEFAULT_JPEG_QUALITY: Final[int] = 88
"""Set the default JPEG output quality for scanned images."""

DEFAULT_SCAN_OUTPUT_FORMAT: Final[str] = "pdf"
"""Set the default file format for a single-page scan."""

PERCENTAGE_BASE: Final[int] = 100
"""Convert percentage adjustments into image enhancement factors."""

SCAN_MODES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "black_white": "Black & White",
        "error_diffusion": "Gray[Error Diffusion]",
        "gray": "True Gray",
        "color": "24bit Color[Fast]",
    }
)
"""Map web scan modes to mode names accepted by the SANE driver."""

PAPER_DIMENSIONS_MM: Final[Mapping[str, tuple[int, int]]] = MappingProxyType(
    {
        "A4": (210, 297),
        "A5": (148, 210),
        "A6": (105, 148),
        "JIS_B5": (182, 257),
        "Letter": (216, 279),
        "Legal": (216, 356),
        "Executive": (184, 267),
        "Business_Card": (90, 60),
        "10x15_cm": (100, 150),
        "13x18_cm": (130, 180),
        "Postcard": (100, 148),
    }
)
"""Map scan paper presets to their flatbed crop dimensions in millimeters."""

CARD_DIMENSIONS_MM: Final[tuple[int, int]] = (86, 54)
"""Set the flatbed crop dimensions used to capture one card side."""

A4_DIMENSIONS_MM: Final[tuple[int, int]] = (210, 297)
"""Set the physical dimensions used to compose ID-card output pages."""

MILLIMETERS_PER_INCH: Final[float] = 25.4
"""Convert A4 and card dimensions from millimeters to scan pixels."""

MAX_SCAN_PAGE_COUNT: Final[int] = 100
"""Limit the number of pages accepted in one continuous scan session."""

ID_CARD_PAGE_COUNT: Final[int] = 2
"""Require a front and back image when composing an ID-card scan."""

PRINT_PAPER_SIZES: Final[frozenset[str]] = frozenset(
    {"A4", "A5", "A6", "Letter", "Legal", "Executive"}
)
"""List paper sizes accepted by the print settings form."""

PRINT_ORIENTATIONS: Final[frozenset[str]] = frozenset(
    {"portrait", "landscape"}
)
"""List page orientations accepted by the print settings form."""

PRINT_MEDIA_TYPES: Final[frozenset[str]] = frozenset(
    {"Plain", "Thin", "Thick", "Thicker", "Bond", "Recycled"}
)
"""List media types accepted by the Brother print driver."""

PRINT_RESOLUTIONS: Final[frozenset[int]] = frozenset({300, 600})
"""List print resolutions supported by the configured printer driver."""

PRINT_QUALITIES: Final[frozenset[str]] = frozenset({"Graphics", "Text"})
"""List print optimization modes accepted by the driver."""

PRINT_PAGES_PER_SHEET: Final[frozenset[int]] = frozenset({1, 2, 4, 6, 9, 16})
"""List page counts supported by the print N-up setting."""

PRINT_PAGE_ORDERS: Final[frozenset[str]] = frozenset(
    {"lrtb", "lrbt", "rltb", "rlbt", "tblr", "tbrl", "btlr", "btrl"}
)
"""List page ordering codes accepted by the printer driver."""

PRINT_PAGE_BORDERS: Final[frozenset[str]] = frozenset(
    {"none", "single", "single-thick", "double", "double-thick"}
)
"""List page border styles accepted by the print settings form."""

PRINT_SCALE_MODES: Final[frozenset[str]] = frozenset({"off", "fit", "custom"})
"""List scaling modes accepted by the print settings form."""

PRINT_ALLOWED_SUFFIXES: Final[frozenset[str]] = frozenset(
    {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
)
"""List file suffixes accepted for print uploads."""

LP_EXECUTABLE: Final[str] = "/usr/bin/lp"
"""Locate the CUPS command that submits print jobs."""

LPSTAT_EXECUTABLE: Final[str] = "/usr/bin/lpstat"
"""Locate the CUPS command that reports printer queue status."""

PRINT_JOB_TIMEOUT_SECONDS: Final[int] = 90
"""Limit the time spent submitting a print job to CUPS."""

PRINTER_STATUS_TIMEOUT_SECONDS: Final[int] = 10
"""Limit the time spent checking the CUPS printer queue."""

MIN_PRINT_SCALE_PERCENT: Final[int] = 25
"""Set the lowest accepted print scaling percentage."""

MAX_PRINT_SCALE_PERCENT: Final[int] = 400
"""Set the highest accepted print scaling percentage."""

MIN_PRINT_COPIES: Final[int] = 1
"""Set the minimum number of copies in one print job."""

MAX_PRINT_COPIES: Final[int] = 99
"""Set the maximum number of copies in one print job."""

MAX_WATERMARK_LENGTH: Final[int] = 48
"""Limit the number of characters in print watermark text."""

DEFAULT_PRINT_PAPER_SIZE: Final[str] = "A4"
"""Set the default paper size for a print job."""

DEFAULT_PRINT_ORIENTATION: Final[str] = "portrait"
"""Set the default page orientation for a print job."""

DEFAULT_PRINT_MEDIA_TYPE: Final[str] = "Plain"
"""Set the default media type for a print job."""

DEFAULT_PRINT_RESOLUTION: Final[int] = 600
"""Set the default print resolution in dots per inch."""

DEFAULT_PRINT_QUALITY: Final[str] = "Graphics"
"""Set the default print optimization mode."""

DEFAULT_PRINT_PAGES_PER_SHEET: Final[int] = 1
"""Set the default N-up layout to one page per sheet."""

DEFAULT_PRINT_PAGE_ORDER: Final[str] = "rltb"
"""Set the default page ordering code for N-up printing."""

DEFAULT_PRINT_PAGE_BORDER: Final[str] = "none"
"""Set the default N-up page border style."""

DEFAULT_PRINT_SCALE_MODE: Final[str] = "off"
"""Disable print scaling by default."""

DEFAULT_PRINT_SCALE_PERCENT: Final[int] = 100
"""Set the default print scale to one hundred percent."""

DEFAULT_PRINT_COPIES: Final[int] = 1
"""Set the default number of copies per print job."""
