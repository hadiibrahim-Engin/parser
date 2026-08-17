"""Writing the final CSV files.

Both files are first written to temporary files inside the target directory and
only then moved atomically to their final name. That way not even an I/O error
can leave a half-written output behind.
"""

from __future__ import annotations

import csv
import logging
import os
import tempfile
from pathlib import Path

import pandas as pd

from excelToCsv.errors import ConversionError
from excelToCsv.targetFormat import TargetFormat
from excelToCsv.schema import (
    DEFAULT_EMPTY_PLACEHOLDER,
    NETWORK_ELEMENTS_FILENAME,
    STATIONS_FILENAME,
)

#: Line ending per contract: a plain LF, independent of the operating system.
LINE_TERMINATOR = "\n"


def fillFullyEmptyColumns(frame: pd.DataFrame, placeholder: str) -> pd.DataFrame:
    """Put ``placeholder`` into every cell of columns that are empty in all rows.

    Purely a serialization concern: ``pandas.read_csv`` types an all-empty column
    as ``float64``/``NaN``, so a reader cannot use the ``.str`` accessor on it.
    Columns holding at least one real value are left untouched, and the in-memory
    records keep their genuinely empty strings - only the file gets the filler.

    An empty ``placeholder`` disables the behaviour entirely.
    """
    if not placeholder or frame.empty:
        return frame

    fullyEmpty = [
        column
        for column in frame.columns
        if all(value == "" for value in frame[column].to_numpy(dtype=object))
    ]
    if not fullyEmpty:
        return frame

    filled = frame.copy()
    for column in fullyEmpty:
        filled[column] = placeholder
    return filled


def _writeSingleCsv(
    frame: pd.DataFrame,
    target: Path,
    encoding: str,
    quoting: int,
) -> None:
    """Write a DataFrame atomically to ``target``."""
    handle, temporaryName = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
    )
    os.close(handle)
    temporary = Path(temporaryName)
    try:
        frame.to_csv(
            temporary,
            index=False,
            sep=",",
            encoding=encoding,
            quoting=quoting,
            lineterminator=LINE_TERMINATOR,
        )
        os.replace(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def writeCsvFiles(
    stations: pd.DataFrame,
    networkElements: pd.DataFrame,
    outputDir: Path,
    logger: logging.Logger,
    *,
    encoding: str = "utf-8",
    quoteAll: bool = False,
    emptyPlaceholder: str = DEFAULT_EMPTY_PLACEHOLDER,
    targetFormat: TargetFormat | None = None,
) -> tuple[Path, Path]:
    """Write ``Stationen.csv`` and ``Netzelemente.csv``.

    Args:
        stations: Fully validated station records.
        networkElements: Fully validated network element records.
        outputDir: Target directory; created when missing.
        logger: Logger for the status messages.
        encoding: Output encoding (``utf-8-sig`` for an Excel-friendly BOM).
        quoteAll: ``True`` puts every field in quotes.
        emptyPlaceholder: Filler for columns that are empty in every row, so a
            reader does not type them as numeric. ``""`` keeps them truly empty.
        targetFormat: Optional column renames and element type translations,
            applied last so the contract check still sees the canonical names.

    Returns:
        The paths of both written files.

    Raises:
        ConversionError: If the directory or a file is not writable.
    """
    quoting = csv.QUOTE_ALL if quoteAll else csv.QUOTE_MINIMAL
    try:
        outputDir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.error("Cannot create output directory %s: %s", outputDir, exc)
        raise ConversionError(f"Cannot create output directory: {outputDir}") from exc

    stationsPath = outputDir / STATIONS_FILENAME
    networkElementsPath = outputDir / NETWORK_ELEMENTS_FILENAME

    if targetFormat is not None and not targetFormat.isEmpty:
        stations = targetFormat.applyToStations(stations)
        networkElements = targetFormat.applyToNetworkElements(networkElements)

    stations = fillFullyEmptyColumns(stations, emptyPlaceholder)
    networkElements = fillFullyEmptyColumns(networkElements, emptyPlaceholder)

    try:
        _writeSingleCsv(stations, stationsPath, encoding, quoting)
        logger.info("Created %s (%d record(s)).", stationsPath, len(stations))
        _writeSingleCsv(networkElements, networkElementsPath, encoding, quoting)
        logger.info("Created %s (%d record(s)).", networkElementsPath, len(networkElements))
    except OSError as exc:
        logger.error("Failed to write CSV output into %s: %s", outputDir, exc)
        raise ConversionError(f"Failed to write CSV output: {exc}") from exc

    return stationsPath, networkElementsPath
