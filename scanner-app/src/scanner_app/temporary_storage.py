"""Manage temporary directories used during scan sessions.

Scan artifacts remain in a private temporary directory until the session ends.
"""

import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from scanner_app import constants
from scanner_app.messages import MessageCode, MessageError


class ScanSessionError(MessageError):
    """Report an invalid, missing, or expired scan session."""


@dataclass(frozen=True, slots=True)
class ScanSession:
    """Identify one temporary directory containing scan artifacts.

    Attributes:
        session_id: Random identifier used by scan requests.
        directory: Private directory containing the session's files.
    """

    session_id: str
    directory: Path


def create_scan_session(temporary_dir: Path) -> ScanSession:
    """Create a private directory for a new scan session.

    Args:
        temporary_dir: Application temporary storage root.

    Returns:
        Identifier and directory for the new scan session.

    Raises:
        OSError: If the session directory cannot be created.
    """
    scan_root = temporary_dir / "scans"
    scan_root.mkdir(
        parents=True,
        exist_ok=True,
        mode=constants.PRIVATE_DIRECTORY_MODE,
    )
    session_id = uuid4().hex
    directory = scan_root / session_id
    directory.mkdir(mode=constants.PRIVATE_DIRECTORY_MODE)
    return ScanSession(session_id=session_id, directory=directory)


def get_scan_session_directory(
    temporary_dir: Path,
    session_id: str,
) -> Path:
    """Validate a scan session and refresh its inactivity timer.

    Args:
        temporary_dir: Application temporary storage root.
        session_id: Session identifier submitted by the browser.

    Returns:
        Existing private directory for the scan session.

    Raises:
        ScanSessionError: If the identifier is invalid or the session expired.
        OSError: If the session directory cannot be updated.
    """
    if not constants.UUID_HEX_PATTERN.fullmatch(session_id):
        raise ScanSessionError(MessageCode.SCAN_SESSION_INVALID)

    directory = temporary_dir / "scans" / session_id
    try:
        if not directory.is_dir():
            raise ScanSessionError(MessageCode.SCAN_SESSION_EXPIRED)
        os.utime(directory, None)
    except FileNotFoundError as err:
        raise ScanSessionError(MessageCode.SCAN_SESSION_EXPIRED) from err
    return directory


def remove_scan_session(temporary_dir: Path, session_id: str) -> None:
    """Remove all artifacts belonging to one scan session.

    Args:
        temporary_dir: Application temporary storage root.
        session_id: Session identifier submitted by the browser.

    Raises:
        ScanSessionError: If the identifier is invalid.
        OSError: If the session directory cannot be removed.
    """
    if not constants.UUID_HEX_PATTERN.fullmatch(session_id):
        raise ScanSessionError(MessageCode.SCAN_SESSION_INVALID)

    directory = temporary_dir / "scans" / session_id
    try:
        shutil.rmtree(directory)
    except FileNotFoundError:
        return


def cleanup_expired_scan_sessions(temporary_dir: Path) -> None:
    """Remove scan sessions inactive for the configured time limit.

    Args:
        temporary_dir: Application temporary storage root.

    Raises:
        OSError: If an expired session cannot be inspected or removed.
    """
    scan_root = temporary_dir / "scans"
    if not scan_root.is_dir():
        return

    expiration_time = time.time() - constants.SCAN_SESSION_IDLE_SECONDS
    for directory in scan_root.iterdir():
        if not constants.UUID_HEX_PATTERN.fullmatch(directory.name):
            continue
        try:
            if (
                directory.is_dir()
                and directory.stat().st_mtime < expiration_time
            ):
                shutil.rmtree(directory)
        except FileNotFoundError:
            continue
