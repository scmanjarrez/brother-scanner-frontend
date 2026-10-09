"""Load runtime paths and printer settings from the environment.

The settings object centralizes temporary storage paths and service limits.
"""

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from scanner_app import constants


@dataclass(frozen=True, slots=True)
class AppSettings:
    """Store temporary paths and queue names for the web application.

    The factory reads values from environment variables and applies defaults.

    Attributes:
        temporary_dir: Ephemeral root for active scan sessions.
        printer_queue: CUPS queue name configured by the startup script.
        max_upload_bytes: Maximum size accepted for one print upload.
    """

    temporary_dir: Path
    printer_queue: str
    max_upload_bytes: int

    @classmethod
    def from_environment(cls) -> "AppSettings":
        """Build settings from the container environment.

        Returns:
            Settings populated from environment variables or defaults.

        Raises:
            ValueError: If MAX_UPLOAD_MB is not an integer.
        """
        temporary_dir = (
            Path(tempfile.gettempdir()) / constants.TEMPORARY_DIRECTORY_NAME
        )
        printer_queue = os.environ.get(
            "PRINTER_QUEUE",
            constants.DEFAULT_PRINTER_QUEUE,
        )
        max_upload_mb = int(
            os.environ.get(
                "MAX_UPLOAD_MB",
                str(constants.DEFAULT_MAX_UPLOAD_MB),
            )
        )
        max_upload_bytes = max_upload_mb * constants.BYTES_PER_MEGABYTE
        return cls(
            temporary_dir=temporary_dir,
            printer_queue=printer_queue,
            max_upload_bytes=max_upload_bytes,
        )
