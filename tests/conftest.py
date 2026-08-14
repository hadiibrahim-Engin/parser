"""Shared test fixtures and data factories."""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from excelToCsv.loggingSetup import LOGGER_NAME  # noqa: E402
from excelToCsv.pipeline import ConversionResult, convertTable  # noqa: E402
from excelToCsv.reader import (  # noqa: E402
    HEADER_ROW_OFFSET,
    InputTable,
    dropEmptyRows,
    normalizeColumns,
    validateRequiredInputColumns,
)
from excelToCsv.schema import REQUIRED_INPUT_COLUMNS  # noqa: E402

import numpy as np  # noqa: E402

#: Default values of a station row.
STATION_DEFAULTS: dict[str, Any] = {
    "TSO": "Amprion",
    "ELEMENT ID": "Berlin_380",
    "LONG-NAME": "Umspannwerk Berlin",
    "DESCRIPTION": "Beispielkommentar",
    "Latitude": "52.459373",
    "Longitude": "13.361402",
    "Station 1": "",
    "Station 2": "",
    "VOLTAGE-LEVEL": "380.0",
    "ELEMENT-TYPE": "SUB",
    "UCTE CODE": "DBERLIN1",
    "STARTLIFETIME": "2025-05-09",
    "ENDLIFETIME": "",
}

#: Default values of a network element row.
ELEMENT_DEFAULTS: dict[str, Any] = {
    **STATION_DEFAULTS,
    "ELEMENT ID": "LINE_471",
    "LONG-NAME": "Leitung Berlin - Hamburg",
    "Latitude": "",
    "Longitude": "",
    "Station 1": "Berlin_380",
    "Station 2": "Hamburg_380",
    "ELEMENT-TYPE": "LINE",
    "UCTE CODE": "DLINE471",
}


def stationRow(**overrides: Any) -> dict[str, Any]:
    """Build a SUB row with sensible defaults."""
    return {**STATION_DEFAULTS, **overrides}


def elementRow(**overrides: Any) -> dict[str, Any]:
    """Build a network element row with sensible defaults."""
    return {**ELEMENT_DEFAULTS, **overrides}


def columnsOf(rows: list[dict[str, Any]]) -> list[str]:
    """Union of all row keys, preserving their order."""
    if not rows:
        return list(REQUIRED_INPUT_COLUMNS)
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    return columns


def makeTable(rows: list[dict[str, Any]], logger: logging.Logger) -> InputTable:
    """Build an ``InputTable`` from row dicts - without any Excel file."""
    columns = columnsOf(rows)
    frame = pd.DataFrame([{column: row.get(column, "") for column in columns} for row in rows],
                         columns=columns, dtype=object)
    frame = normalizeColumns(frame, logger)
    validateRequiredInputColumns(frame, logger)
    frame = frame.reset_index(drop=True)
    rowNumbers = np.arange(len(frame), dtype=np.int64) + HEADER_ROW_OFFSET
    frame, rowNumbers = dropEmptyRows(frame, rowNumbers, logger)
    return InputTable(frame=frame, rowNumbers=rowNumbers, sheetName="Tabelle1")


def convertRows(rows: list[dict[str, Any]], logger: logging.Logger) -> ConversionResult:
    """Convert row dicts directly (transformation without I/O)."""
    return convertTable(makeTable(rows, logger), logger)


def writeExcel(rows: list[dict[str, Any]], path: Path, sheetName: str = "Tabelle1") -> Path:
    """Write row dicts to an Excel file for end-to-end tests."""
    columns = columnsOf(rows)
    frame = pd.DataFrame([{column: row.get(column, "") for column in columns} for row in rows],
                         columns=columns)
    frame.to_excel(path, index=False, sheet_name=sheetName, engine="openpyxl")
    return path


def writeExcelWithPreamble(
    rows: list[dict[str, Any]],
    path: Path,
    preamble: list[list[Any]],
    sheetName: str = "Tabelle1",
) -> Path:
    """Write a workbook whose header row sits below a preamble."""
    columns = columnsOf(rows)
    grid: list[list[Any]] = []
    for line in preamble:
        padded = list(line)[: len(columns)]
        grid.append(padded + [""] * (len(columns) - len(padded)))
    grid.append(list(columns))
    grid.extend([row.get(column, "") for column in columns] for row in rows)

    pd.DataFrame(grid).to_excel(
        path, index=False, header=False, sheet_name=sheetName, engine="openpyxl"
    )
    return path


class RecordingHandler(logging.Handler):
    """Collect log records so tests can assert on warnings and errors."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def messages(self, level: int) -> list[str]:
        """Return all formatted messages of one level."""
        return [record.getMessage() for record in self.records if record.levelno == level]

    def text(self, level: int) -> str:
        """All messages of one level as a single block (for ``in`` assertions)."""
        return "\n".join(self.messages(level))


@pytest.fixture()
def logCapture() -> Iterator[RecordingHandler]:
    """Attach a recording handler to the converter logger."""
    handler = RecordingHandler()
    logger = logging.getLogger(LOGGER_NAME)
    previousLevel = logger.level
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        yield handler
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previousLevel)


@pytest.fixture()
def logger(logCapture: RecordingHandler) -> logging.Logger:
    """Converter logger without console output, but with recording."""
    return logging.getLogger(LOGGER_NAME)
