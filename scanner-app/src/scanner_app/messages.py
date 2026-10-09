"""Define stable English API codes and message payloads."""

from collections.abc import Mapping
from enum import StrEnum
from typing import TypedDict


class MessageCode(StrEnum):
    """Identify API messages without storing display copy."""

    PRINT_JOB_SENT = "printJobSentToThePrinter"
    PRINT_JOB_SENT_WITH_ID = "printJobSentWithId"
    PDF_READY = "pdfIsReadyToDownload"
    SCAN_COMPLETE = "scanCompleteDownloadItOrContinueWithAnotherDocument"
    FRONT_CAPTURED = "frontCaptured"
    BACK_CAPTURED = "backCaptured"
    PAGE_ADDED = "pageAddedToTheDocument"
    FILE_TOO_LARGE = "theFileExceedsTheMaximumAllowedSize"
    PRINT_FILE_REQUIRED = "selectAFileToPrint"
    UNSUPPORTED_PRINT_FORMAT = "unsupportedFormatUsePdfPngJpegOrTiff"
    PRINT_PREPARATION_FAILED = "couldNotPrepareTheFileForPrinting"
    CUPS_TIMEOUT = "cupsTookTooLongToReceiveTheDocument"
    CUPS_LP_MISSING = "theCupsLpCommandCouldNotBeFound"
    PRINT_JOB_FAILED = "couldNotRunThePrintJob"
    CUPS_REJECTED_JOB = "cupsRejectedThePrintJob"
    PRINT_OVERLAY_FAILED = "couldNotAddTheWatermarkOrHeader"
    IMAGE_HAS_NO_PRINTABLE_PAGES = "theImageFileContainsNoPrintablePages"
    IMAGE_TO_PDF_FAILED = "couldNotConvertTheImageToPdf"
    INVALID_PRINT_OPTION = "aPrintOptionIsInvalid"
    WATERMARK_REQUIRED = "enterTheWatermarkText"
    SCAN_SELECTION_INVALID = "theSelectedScanWorkflowIsInvalid"
    CARD_SIDE_INVALID = "selectTheFrontOrBackOfTheCard"
    SCAN_WORKFLOW_INVALID = "theScanWorkflowIsInvalid"
    SCAN_PAGE_COUNT_INVALID = "theDocumentMustContainBetween1And100Pages"
    CARD_SIDES_REQUIRED = "cardModeRequiresBothSides"
    RESOLUTION_UNAVAILABLE = "selectedResolutionUnavailable"
    SCAN_MODE_INVALID = "theSelectedScanModeIsInvalid"
    DOCUMENT_SIZE_INVALID = "theSelectedDocumentSizeIsInvalid"
    SCAN_FORMAT_INVALID = "theSelectedOutputFormatIsInvalid"
    SCANNER_NOT_FOUND = "scannerNotFound"
    SCAN_TIMEOUT = "theScanTimedOut"
    SANE_SCANIMAGE_MISSING = "theSaneScanimageCommandCouldNotBeFound"
    SCAN_CAPTURE_FAILED = "theScannerCouldNotCompleteTheCapture"
    IMAGE_ADJUSTMENT_FAILED = "couldNotAdjustTheImageBrightnessOrContrast"
    SCAN_FILE_GENERATION_FAILED = "couldNotCreateTheScannedFile"
    SCAN_PAGE_REQUIRED = "addAtLeastOnePageBeforeFinishing"
    SCAN_DOCUMENT_COMBINE_FAILED = "couldNotCombineTheScannedDocument"
    CARD_PDF_CREATION_FAILED = "couldNotCreateTheCardPdf"
    BACKGROUND_REMOVAL_FAILED = "couldNotRemoveTheImageBackground"
    SCAN_SESSION_INVALID = "theScanSessionIsInvalid"
    SCAN_SESSION_EXPIRED = "theScanSessionExpiredStartANewSession"
    SCAN_PAGE_UNAVAILABLE = "oneOfThePagesIsNoLongerAvailable"
    SCAN_ARTIFACT_NOT_FOUND = "theRequestedFileDoesNotExist"
    PREVIEW_NOT_FOUND = "thePreviewDoesNotExist"
    FILE_HAS_NO_PRINTABLE_PAGES = "theFileContainsNoPrintablePages"
    PROTECTED_PDF = "protectedPdfUnsupported"
    SCALE_RANGE = "scaleRange"
    COPIES_RANGE = "copiesRange"
    WATERMARK_LENGTH = "watermarkLength"
    BRIGHTNESS_CONTRAST_RANGE = "brightnessContrastRange"
    BACKGROUND_LEVEL_RANGE = "backgroundLevelRange"
    JPEG_QUALITY_RANGE = "jpegQualityRange"
    INTEGER_REQUIRED = "integer"
    FIELD_UNAVAILABLE = "unavailable"


class MessagePayload(TypedDict):
    """Store an API code and its interpolation parameters.

    Attributes:
        code: Stable English identifier resolved by the web client.
        params: Values inserted into the translated message template.
    """

    code: str
    params: dict[str, str | int]


class MessageError(Exception):
    """Carry an English API code and parameters through the service layer.

    Attributes:
        code: Stable English identifier resolved by the web client.
        params: Values inserted into the translated message template.
    """

    code: MessageCode
    params: dict[str, str | int]

    def __init__(
        self,
        code: MessageCode,
        params: Mapping[str, str | int] | None = None,
    ) -> None:
        """Create an API error without display copy.

        Args:
            code: Stable English identifier defined by MessageCode.
            params: Optional values used by the translated template.
        """
        self.code = code
        self.params = dict(params) if params is not None else {}
        super().__init__(code.value)

    def to_payload(self) -> MessagePayload:
        """Return the message code and values for an API response.

        Returns:
            A JSON-compatible structured message payload.
        """
        return message_payload(self.code, self.params)


def message_payload(
    code: MessageCode,
    params: Mapping[str, str | int] | None = None,
) -> MessagePayload:
    """Build a coded payload for a successful API response.

    Args:
        code: Stable English identifier defined by MessageCode.
        params: Optional values used by the translated template.

    Returns:
        A JSON-compatible structured message payload.
    """
    return {
        "code": code.value,
        "params": dict(params) if params is not None else {},
    }
