"""Reading the Excel file and preparing the input schema.

Responsible for: file I/O, header detection, column normalization, schema
validation and dropping completely empty rows. The business transformation
deliberately does NOT happen here.
"""

from __future__ import annotations

import importlib.util
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from excelToCsv.errors import ConversionError, NormalizationError
from excelToCsv.normalize import collapseWhitespace, isBlank, normalizeText
from excelToCsv.schema import KNOWN_INPUT_COLUMNS, REQUIRED_INPUT_COLUMNS

#: Distance between the header row and the first data row (counted 1-based).
HEADER_ROW_OFFSET = 2

#: At most this many rows are scanned when searching for the header row.
MAX_HEADER_SCAN_ROWS = 100

#: Share of the required columns a row should match to be a convincing header.
MIN_HEADER_MATCH_RATIO = 0.5

#: Name given to columns whose header cell is empty (same idea as pandas).
UNNAMED_COLUMN_TEMPLATE = "Unnamed: {position}"

#: Default engine. ``openpyxl`` is always available; ``calamine`` is an optional
#: accelerator (roughly 5x faster reading) and is only used when installed.
DEFAULT_ENGINE = "auto"
FALLBACK_ENGINE = "openpyxl"
FAST_ENGINE = "calamine"


def resolveEngine(engine: str, logger: logging.Logger) -> str:
    """Pick the reading engine; ``auto`` prefers ``calamine``, else ``openpyxl``."""
    if engine != DEFAULT_ENGINE:
        return engine
    if importlib.util.find_spec("python_calamine") is not None:
        logger.debug("Using the optional '%s' engine for faster reading.", FAST_ENGINE)
        return FAST_ENGINE
    return FALLBACK_ENGINE


@dataclass(slots=True)
class InputTable:
    """A prepared input table together with its real Excel row numbers."""

    frame: pd.DataFrame
    rowNumbers: np.ndarray
    sheetName: str
    headerRowNumber: int = 1

    def __len__(self) -> int:
        return len(self.frame)


def loadExcel(
    path: Path,
    sheet: str | int | None,
    logger: logging.Logger,
    engine: str = DEFAULT_ENGINE,
) -> tuple[pd.DataFrame, str]:
    """Read a worksheet raw - without assuming where the header is.

    Reading uses ``header=None`` so the header row can be determined afterwards.
    ``dtype=object`` prevents pandas from converting values (ids, voltages,
    codes) into numbers on its own. Without an explicit selection the first
    worksheet is used and its name is logged.

    Raises:
        ConversionError: File missing, unreadable, or the sheet does not exist.
    """
    if not path.is_file():
        logger.error("Input file not found: %s", path)
        raise ConversionError(f"Input file not found: {path}")

    selectedEngine = resolveEngine(engine, logger)
    logger.info("Reading input file: %s", path)
    try:
        with pd.ExcelFile(path, engine=selectedEngine) as workbook:
            sheetNames = list(workbook.sheet_names)
            if not sheetNames:
                logger.error("Workbook contains no worksheet: %s", path)
                raise ConversionError(f"Workbook contains no worksheet: {path}")

            if sheet is None:
                selected = sheetNames[0]
                if len(sheetNames) > 1:
                    logger.info(
                        "Workbook contains %d worksheets %s - using the first one.",
                        len(sheetNames),
                        sheetNames,
                    )
            elif isinstance(sheet, int):
                if not 0 <= sheet < len(sheetNames):
                    logger.error(
                        "Sheet index %d is out of range (workbook has %d worksheets).",
                        sheet,
                        len(sheetNames),
                    )
                    raise ConversionError(f"Sheet index out of range: {sheet}")
                selected = sheetNames[sheet]
            else:
                if sheet not in sheetNames:
                    logger.error("Sheet '%s' not found. Available: %s", sheet, sheetNames)
                    raise ConversionError(f"Sheet not found: {sheet}")
                selected = sheet

            logger.info("Using worksheet: %s", selected)
            frame = workbook.parse(sheet_name=selected, dtype=object, header=None)
    except ConversionError:
        raise
    except Exception as exc:  # openpyxl/pandas raise very heterogeneous errors
        if selectedEngine != FALLBACK_ENGINE and engine == DEFAULT_ENGINE:
            logger.warning(
                "Reading with the '%s' engine failed (%s) - retrying with '%s'.",
                selectedEngine,
                exc,
                FALLBACK_ENGINE,
            )
            return loadExcel(path, sheet, logger, engine=FALLBACK_ENGINE)
        logger.error("Failed to read Excel file %s: %s", path, exc)
        raise ConversionError(f"Failed to read Excel file: {path}") from exc

    logger.info(
        "Read %d raw row(s) and %d column(s) using the '%s' engine.",
        len(frame),
        len(frame.columns),
        selectedEngine,
    )
    return frame, selected


# --------------------------------------------------------------------------- #
# Locating the header row
# --------------------------------------------------------------------------- #


def headerKey(value: object) -> str:
    """Comparison key of a header cell (trimmed, lowercased, single-spaced)."""
    return collapseWhitespace(normalizeText(value)).lower()


#: Pre-computed keys of the required columns - built once per process.
_REQUIRED_KEYS: frozenset[str] = frozenset(headerKey(name) for name in REQUIRED_INPUT_COLUMNS)


def scoreHeaderRow(values: np.ndarray) -> int:
    """Count how many required column names appear as headings in this row."""
    return len(_REQUIRED_KEYS & {headerKey(value) for value in values if not isBlank(value)})


def detectHeaderRow(
    raw: pd.DataFrame,
    logger: logging.Logger,
    maxScanRows: int = MAX_HEADER_SCAN_ROWS,
) -> int:
    """Find the row holding the column headings (0-based position).

    Each of the first ``maxScanRows`` rows is scored by how many required column
    names it contains as headings. The first row with the highest score wins; a
    perfect match stops the search immediately. Everything above that row is
    preamble and gets discarded.

    A weakly matching header is deliberately accepted and only reported as a
    ``WARNING``: the schema check that follows then names the exact missing
    column, which is far more useful than a blanket "not found".

    Raises:
        ConversionError: If none of the scanned rows contains even one required
            column name.
    """
    limit = min(len(raw), maxScanRows)
    required = len(REQUIRED_INPUT_COLUMNS)

    bestIndex = -1
    bestScore = 0
    for index in range(limit):
        score = scoreHeaderRow(raw.iloc[index].to_numpy(dtype=object))
        if score > bestScore:
            bestIndex, bestScore = index, score
            if score == required:
                break

    if bestScore == 0:
        logger.error(
            "Could not locate the header row: none of the first %d row(s) contains any of "
            "the %d required column names. Use --header-row to point at it explicitly.",
            limit,
            required,
        )
        raise ConversionError("Could not locate the header row")

    headerRowNumber = bestIndex + 1
    if bestIndex == 0:
        logger.info("Header detected in row %d.", headerRowNumber)
    else:
        logger.info(
            "Header detected in row %d - skipping %d leading row(s) above it.",
            headerRowNumber,
            bestIndex,
        )

    if bestScore < max(1, round(required * MIN_HEADER_MATCH_RATIO)):
        logger.warning(
            "Row %d matched only %d of %d required columns - it may not be the real header. "
            "Use --header-row if the header is somewhere else.",
            headerRowNumber,
            bestScore,
            required,
        )
    elif bestScore < required:
        logger.debug(
            "Header row %d matched %d of %d required columns.",
            headerRowNumber,
            bestScore,
            required,
        )
    return bestIndex


def applyHeaderRow(raw: pd.DataFrame, headerIndex: int) -> pd.DataFrame:
    """Promote ``headerIndex`` to the header row and discard everything above it."""
    headerValues = raw.iloc[headerIndex].to_numpy(dtype=object)
    names = [
        collapseWhitespace(normalizeText(value)) or UNNAMED_COLUMN_TEMPLATE.format(position=position)
        for position, value in enumerate(headerValues)
    ]
    frame = raw.iloc[headerIndex + 1 :].reset_index(drop=True)
    frame.columns = pd.Index(names)
    return frame


def resolveHeaderIndex(
    raw: pd.DataFrame,
    headerRow: int | None,
    logger: logging.Logger,
) -> int:
    """Determine the header row - either explicitly given or detected.

    Args:
        raw: Raw table without any header assumption.
        headerRow: 1-based Excel row number, or ``None`` for automatic detection.

    Raises:
        ConversionError: On an invalid override or an undetectable header.
    """
    if headerRow is None:
        return detectHeaderRow(raw, logger)

    headerIndex = headerRow - 1
    if not 0 <= headerIndex < len(raw):
        logger.error(
            "Header row %d is outside the worksheet (it has %d row(s)).", headerRow, len(raw)
        )
        raise ConversionError(f"Header row out of range: {headerRow}")

    logger.info("Using row %d as the header (explicitly configured).", headerRow)
    if headerIndex:
        logger.info("Skipping %d leading row(s) above the header.", headerIndex)
    return headerIndex


def normalizeColumns(frame: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    """Trim column headings and map them onto their canonical spelling.

    Matching is case-insensitive and whitespace-tolerant. Unknown columns keep
    their (trimmed) name - they are still needed for the dynamic relevance
    detection.

    Raises:
        ConversionError: If normalization produces duplicate column names.
    """
    canonicalByKey = {collapseWhitespace(name).lower(): name for name in KNOWN_INPUT_COLUMNS}

    renamed: list[str] = []
    for original in frame.columns:
        cleaned = collapseWhitespace(str(original))
        canonical = canonicalByKey.get(cleaned.lower(), cleaned)
        if canonical != str(original):
            logger.debug("Column %r normalized to %r.", str(original), canonical)
        renamed.append(canonical)

    duplicates = sorted({name for name in renamed if renamed.count(name) > 1})
    if duplicates:
        logger.error("Duplicate input columns after normalization: %s", ", ".join(duplicates))
        raise ConversionError(f"Duplicate input columns: {', '.join(duplicates)}")

    normalized = frame.copy()
    normalized.columns = pd.Index(renamed)
    return normalized


def validateRequiredInputColumns(frame: pd.DataFrame, logger: logging.Logger) -> None:
    """Ensure that every mandatory input column is present.

    Raises:
        ConversionError: As soon as at least one required column is missing.
    """
    present = set(frame.columns)
    missing = [name for name in REQUIRED_INPUT_COLUMNS if name not in present]
    if missing:
        for name in missing:
            logger.error("Missing required input column: %s", name)
        raise ConversionError(f"Missing required input column(s): {', '.join(missing)}")
    logger.debug("All %d required input columns are present.", len(REQUIRED_INPUT_COLUMNS))


def dropEmptyRows(
    frame: pd.DataFrame,
    rowNumbers: np.ndarray,
    logger: logging.Logger,
) -> tuple[pd.DataFrame, np.ndarray]:
    """Drop rows that are empty in EVERY column (typical trailing Excel rows)."""
    if frame.empty:
        return frame, rowNumbers

    blank = np.ones(len(frame), dtype=bool)
    for column in frame.columns:
        values = frame[column].to_numpy(dtype=object)
        blank &= np.fromiter((isBlank(value) for value in values), dtype=bool, count=len(values))

    dropped = int(blank.sum())
    if not dropped:
        return frame, rowNumbers

    logger.info("Skipping %d completely empty input row(s).", dropped)
    keep = ~blank
    return frame.loc[keep].reset_index(drop=True), rowNumbers[keep]


def buildInputTable(
    path: Path,
    sheet: str | int | None,
    logger: logging.Logger,
    engine: str = DEFAULT_ENGINE,
    headerRow: int | None = None,
) -> InputTable:
    """The complete read path: Excel -> validated, prepared ``InputTable``.

    The header row is detected automatically (or given via ``headerRow``); every
    row above it counts as preamble and is discarded. The reported row numbers
    still refer to the real Excel row.
    """
    raw, sheetName = loadExcel(path, sheet, logger, engine=engine)
    headerIndex = resolveHeaderIndex(raw, headerRow, logger)

    frame = applyHeaderRow(raw, headerIndex)
    frame = normalizeColumns(frame, logger)
    validateRequiredInputColumns(frame, logger)
    logger.info("Found %d data row(s) below the header.", len(frame))

    rowNumbers = np.arange(len(frame), dtype=np.int64) + headerIndex + HEADER_ROW_OFFSET
    frame, rowNumbers = dropEmptyRows(frame, rowNumbers, logger)
    return InputTable(
        frame=frame,
        rowNumbers=rowNumbers,
        sheetName=sheetName,
        headerRowNumber=headerIndex + 1,
    )


def columnValues(frame: pd.DataFrame, column: str) -> np.ndarray:
    """Return a column as an object array; a missing column yields ``None`` values."""
    if column in frame.columns:
        return frame[column].to_numpy(dtype=object)
    return np.full(len(frame), None, dtype=object)


def textColumn(frame: pd.DataFrame, column: str) -> np.ndarray:
    """Return a column as trimmed text values (empty values become ``""``)."""
    values = columnValues(frame, column)
    return np.fromiter(
        (normalizeText(value) for value in values), dtype=object, count=len(values)
    )


def applyNormalizer(
    values: np.ndarray,
    normalizer: Callable[[Any], str],
) -> tuple[np.ndarray, list[tuple[int, NormalizationError]]]:
    """Apply a normalizer column-wise and collect the individual failures.

    Instead of stopping at the first problem, every faulty value is reported with
    its position, so one run surfaces all errors at once.

    Returns:
        A tuple of normalized values and ``(position, error)`` pairs.
    """
    result = np.empty(len(values), dtype=object)
    failures: list[tuple[int, NormalizationError]] = []
    for position, value in enumerate(values):
        try:
            result[position] = normalizer(value)
        except NormalizationError as error:
            result[position] = ""
            failures.append((position, error))
    return result, failures
