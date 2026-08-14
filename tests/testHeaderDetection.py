"""Tests for the automatic header row detection."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from conftest import (
    RecordingHandler,
    elementRow,
    stationRow,
    writeExcel,
    writeExcelWithPreamble,
)

from excelToCsv.cli import EXIT_CONVERSION_ERROR, EXIT_SUCCESS, main
from excelToCsv.errors import ConversionError
from excelToCsv.pipeline import runConversion
from excelToCsv.reader import buildInputTable
from excelToCsv.schema import STATIONS_FILENAME

#: A typical preamble: title, metadata, blank line.
PREAMBLE = [
    ["Netzinventar Export"],
    ["Stand: 14.08.2026", "", "Verantwortlich: Netzplanung"],
    [],
    ["Hinweis: Bitte nichts oberhalb der Kopfzeile eintragen"],
]


def sampleRows() -> list[dict[str, object]]:
    """Two stations and one network element."""
    return [
        stationRow(),
        stationRow(
            **{
                "ELEMENT ID": "Hamburg_380",
                "LONG-NAME": "Umspannwerk Hamburg",
                "Latitude": "53.551086",
                "Longitude": "9.993682",
                "UCTE CODE": "DHAMBRG1",
            }
        ),
        elementRow(),
    ]


def testHeaderInFifthRowIsDetected(
    tmp_path: Path, logger: logging.Logger, logCapture: RecordingHandler
) -> None:
    """Header in row 5: everything above it is discarded."""
    inputFile = writeExcelWithPreamble(sampleRows(), tmp_path / "input.xlsx", PREAMBLE)

    result = runConversion(inputFile, tmp_path / "out", logger)

    assert len(result.stations) == 2
    assert len(result.networkElements) == 1
    info = logCapture.text(logging.INFO)
    assert "Header detected in row 5 - skipping 4 leading row(s) above it." in info
    assert "Found 3 data row(s) below the header." in info


def testHeaderInFirstRowStillWorks(
    tmp_path: Path, logger: logging.Logger, logCapture: RecordingHandler
) -> None:
    inputFile = writeExcel(sampleRows(), tmp_path / "input.xlsx")

    result = runConversion(inputFile, tmp_path / "out", logger)

    assert len(result.stations) == 2
    assert "Header detected in row 1." in logCapture.text(logging.INFO)


@pytest.mark.parametrize("preambleLength", [0, 1, 4, 9, 25])
def testRowNumbersMatchTheRealExcelRow(
    preambleLength: int,
    tmp_path: Path,
    logger: logging.Logger,
    logCapture: RecordingHandler,
) -> None:
    """Messages must name the real Excel row, not the position in the data."""
    preamble = [[f"Vorspann {index}"] for index in range(preambleLength)]
    rows = [*sampleRows(), stationRow(**{"ELEMENT ID": "Kaputt_380", "Latitude": ""})]
    inputFile = writeExcelWithPreamble(rows, tmp_path / "input.xlsx", preamble)

    with pytest.raises(ConversionError):
        runConversion(inputFile, tmp_path / "out", logger)

    # Header = preambleLength + 1, first data row = preambleLength + 2,
    # and the faulty row is the fourth data row.
    expectedRow = preambleLength + 2 + 3
    errors = logCapture.text(logging.ERROR)
    assert f"Row: {expectedRow}" in errors
    assert "ELEMENT ID: Kaputt_380" in errors


def testHeaderIndexIsExposedOnTheInputTable(tmp_path: Path, logger: logging.Logger) -> None:
    inputFile = writeExcelWithPreamble(sampleRows(), tmp_path / "input.xlsx", PREAMBLE)
    table = buildInputTable(inputFile, None, logger)

    assert table.headerRowNumber == 5
    assert list(table.rowNumbers) == [6, 7, 8]


def testExplicitHeaderRowOverridesDetection(
    tmp_path: Path, logger: logging.Logger, logCapture: RecordingHandler
) -> None:
    inputFile = writeExcelWithPreamble(sampleRows(), tmp_path / "input.xlsx", PREAMBLE)

    result = runConversion(inputFile, tmp_path / "out", logger, headerRow=5)

    assert len(result.stations) == 2
    assert "Using row 5 as the header (explicitly configured)." in logCapture.text(logging.INFO)


def testExplicitHeaderRowPointingAtPreambleFails(
    tmp_path: Path, logger: logging.Logger, logCapture: RecordingHandler
) -> None:
    inputFile = writeExcelWithPreamble(sampleRows(), tmp_path / "input.xlsx", PREAMBLE)

    with pytest.raises(ConversionError):
        runConversion(inputFile, tmp_path / "out", logger, headerRow=2)

    assert "Missing required input column" in logCapture.text(logging.ERROR)


def testExplicitHeaderRowOutOfRangeFails(
    tmp_path: Path, logger: logging.Logger, logCapture: RecordingHandler
) -> None:
    inputFile = writeExcel(sampleRows(), tmp_path / "input.xlsx")

    with pytest.raises(ConversionError):
        runConversion(inputFile, tmp_path / "out", logger, headerRow=99)

    assert "is outside the worksheet" in logCapture.text(logging.ERROR)


def testWorkbookWithoutHeaderIsReported(
    tmp_path: Path, logger: logging.Logger, logCapture: RecordingHandler
) -> None:
    """Without a detectable header the conversion aborts with a clear hint."""
    import pandas as pd

    inputFile = tmp_path / "input.xlsx"
    pd.DataFrame([["irgendwas", 1], ["noch was", 2]]).to_excel(
        inputFile, index=False, header=False, engine="openpyxl"
    )

    with pytest.raises(ConversionError):
        runConversion(inputFile, tmp_path / "out", logger)

    errors = logCapture.text(logging.ERROR)
    assert "Could not locate the header row" in errors
    assert "--header-row" in errors
    assert not (tmp_path / "out" / STATIONS_FILENAME).exists()


def testIncompleteHeaderWarnsAndNamesTheMissingColumns(
    tmp_path: Path, logger: logging.Logger, logCapture: RecordingHandler
) -> None:
    """A weak header yields the precise missing-column list, not "not found"."""
    import pandas as pd

    inputFile = tmp_path / "input.xlsx"
    pd.DataFrame([{"TSO": "Amprion", "ELEMENT ID": "Berlin_380"}]).to_excel(
        inputFile, index=False, engine="openpyxl"
    )

    with pytest.raises(ConversionError):
        runConversion(inputFile, tmp_path / "out", logger)

    assert "matched only 2 of 13 required columns" in logCapture.text(logging.WARNING)
    assert "Missing required input column: LONG-NAME" in logCapture.text(logging.ERROR)


def testEmptyRowsBetweenPreambleAndHeader(tmp_path: Path, logger: logging.Logger) -> None:
    inputFile = writeExcelWithPreamble(
        sampleRows(), tmp_path / "input.xlsx", [["Titel"], [], [], []]
    )
    result = runConversion(inputFile, tmp_path / "out", logger)
    assert len(result.stations) == 2


def testPreambleMentioningColumnNamesDoesNotWin(tmp_path: Path, logger: logging.Logger) -> None:
    """Preamble text naming a few columns must not outrank the real header."""
    preamble = [["TSO"], ["ELEMENT ID", "LONG-NAME"], ["Latitude", "Longitude", "Station 1"]]
    inputFile = writeExcelWithPreamble(sampleRows(), tmp_path / "input.xlsx", preamble)

    table = buildInputTable(inputFile, None, logger)
    assert table.headerRowNumber == 4


def testUnnamedHeaderCellsAreTolerated(tmp_path: Path, logger: logging.Logger) -> None:
    """Empty cells in the header row get a placeholder name."""
    rows = [{**row, "": "Zusatzspalte"} for row in sampleRows()]
    inputFile = writeExcelWithPreamble(rows, tmp_path / "input.xlsx", PREAMBLE)

    result = runConversion(inputFile, tmp_path / "out", logger)
    assert len(result.stations) == 2


def testBothEnginesDetectTheSameHeader(tmp_path: Path, logger: logging.Logger) -> None:
    pytest.importorskip("python_calamine")
    inputFile = writeExcelWithPreamble(sampleRows(), tmp_path / "input.xlsx", PREAMBLE)

    openpyxlTable = buildInputTable(inputFile, None, logger, engine="openpyxl")
    calamineTable = buildInputTable(inputFile, None, logger, engine="calamine")

    assert openpyxlTable.headerRowNumber == calamineTable.headerRowNumber == 5
    assert list(openpyxlTable.rowNumbers) == list(calamineTable.rowNumbers)


def testCliAcceptsHeaderRowOption(tmp_path: Path) -> None:
    inputFile = writeExcelWithPreamble(sampleRows(), tmp_path / "input.xlsx", PREAMBLE)

    exitCode = main(
        [str(inputFile), "--output-dir", str(tmp_path / "out"), "--header-row", "5", "--no-color"]
    )
    assert exitCode == EXIT_SUCCESS
    assert (tmp_path / "out" / STATIONS_FILENAME).is_file()


def testCliFailsOnWrongHeaderRow(tmp_path: Path) -> None:
    inputFile = writeExcelWithPreamble(sampleRows(), tmp_path / "input.xlsx", PREAMBLE)

    exitCode = main(
        [str(inputFile), "--output-dir", str(tmp_path / "out"), "--header-row", "1", "--no-color"]
    )
    assert exitCode == EXIT_CONVERSION_ERROR
