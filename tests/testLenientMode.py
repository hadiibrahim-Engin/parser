"""Tests for the default behaviour: errors are logged, the CSV files still appear."""

from __future__ import annotations

import csv
import logging
from pathlib import Path

import pytest
from conftest import RecordingHandler, convertRows, elementRow, stationRow, writeExcel

from excelToCsv.cli import EXIT_CONVERSION_ERROR, EXIT_SUCCESS, main
from excelToCsv.errors import ConversionError
from excelToCsv.pipeline import runConversion
from excelToCsv.schema import NETWORK_ELEMENTS_FILENAME, STATIONS_FILENAME


def twoStations() -> list[dict[str, object]]:
    """Two valid stations network elements can point at."""
    return [
        stationRow(),
        stationRow(
            **{
                "ELEMENT ID": "Hamburg_380",
                "Latitude": "53.551086",
                "Longitude": "9.993682",
                "UCTE CODE": "DHAMBRG1",
            }
        ),
    ]


# --------------------------------------------------------------------------- #
# Errors no longer stop the conversion
# --------------------------------------------------------------------------- #


def testErrorsDoNotStopTheConversion(
    logger: logging.Logger, logCapture: RecordingHandler
) -> None:
    """A dangling station reference is reported but the records are still built."""
    rows = [*twoStations(), elementRow(**{"Station 2": "GibtsNicht_380"})]
    result = convertRows(rows, logger, strict=False)

    assert result.errorCount == 1
    assert len(result.stations) == 2
    assert len(result.networkElements) == 1
    assert "Station reference does not match any station." in logCapture.text(logging.ERROR)


def testFinalSummaryNamesTheErrorCount(
    logger: logging.Logger, logCapture: RecordingHandler
) -> None:
    rows = [*twoStations(), elementRow(**{"Station 2": "GibtsNicht_380"})]
    convertRows(rows, logger, strict=False)

    critical = logCapture.text(logging.CRITICAL)
    assert "Completed WITH 1 error(s)" in critical
    assert "written anyway" in critical


def testCsvFilesAreWrittenDespiteErrors(tmp_path: Path, logger: logging.Logger) -> None:
    rows = [*twoStations(), elementRow(**{"Station 2": "GibtsNicht_380"})]
    inputFile = writeExcel(rows, tmp_path / "input.xlsx")

    result = runConversion(inputFile, tmp_path / "out", logger)

    assert result.errorCount == 1
    assert (tmp_path / "out" / STATIONS_FILENAME).is_file()
    assert (tmp_path / "out" / NETWORK_ELEMENTS_FILENAME).is_file()


def testCliWritesFilesAndStillSignalsTheErrors(tmp_path: Path) -> None:
    """The files exist, and the exit code still says the run was not clean."""
    rows = [*twoStations(), elementRow(**{"Station 2": "GibtsNicht_380"})]
    inputFile = writeExcel(rows, tmp_path / "input.xlsx")

    exitCode = main([str(inputFile), "-o", str(tmp_path / "out"), "--no-color"])

    assert exitCode == EXIT_CONVERSION_ERROR
    assert (tmp_path / "out" / STATIONS_FILENAME).is_file()
    assert (tmp_path / "out" / NETWORK_ELEMENTS_FILENAME).is_file()


def testCleanRunStillExitsZero(tmp_path: Path) -> None:
    inputFile = writeExcel([*twoStations(), elementRow()], tmp_path / "input.xlsx")
    assert main([str(inputFile), "-o", str(tmp_path / "out"), "--no-color"]) == EXIT_SUCCESS


# --------------------------------------------------------------------------- #
# What a faulty row looks like in the output
# --------------------------------------------------------------------------- #


def testMissingMandatoryStationLeavesTheFieldEmpty(logger: logging.Logger) -> None:
    rows = [*twoStations(), elementRow(**{"Station 2": ""})]
    element = convertRows(rows, logger, strict=False).networkElements.iloc[0]

    assert element["Station Anfang"] == "Berlin_380"
    assert element["Station Ende"] == "", "no NaN literal - the value is genuinely missing"
    assert element["Station Ende:MJAP-ID"] == ""


def testStationWithoutCoordinatesKeepsEmptyCells(logger: logging.Logger) -> None:
    rows = [stationRow(**{"Latitude": "", "Longitude": ""})]
    station = convertRows(rows, logger, strict=False).stations.iloc[0]

    assert station["MJAP-ID"] == "Amprion_Berlin_380"
    assert station["lat"] == ""
    assert station["long"] == ""


def testUnparsableDateLeavesTheCellEmpty(logger: logging.Logger) -> None:
    rows = [stationRow(**{"STARTLIFETIME": "irgendwann"})]
    station = convertRows(rows, logger, strict=False).stations.iloc[0]
    assert station["IBN"] == ""


def testDanglingReferenceKeepsTheRawValueButNoMjapId(logger: logging.Logger) -> None:
    rows = [*twoStations(), elementRow(**{"Station 2": "GibtsNicht_380"})]
    element = convertRows(rows, logger, strict=False).networkElements.iloc[0]

    assert element["Station Ende"] == "GibtsNicht_380", "the source value is not hidden"
    assert element["Station Ende:MJAP-ID"] == "", "but it resolves to nothing"


# --------------------------------------------------------------------------- #
# Unknown element types cannot be routed, so they are dropped
# --------------------------------------------------------------------------- #


def testUnknownElementTypeRowIsDropped(
    logger: logging.Logger, logCapture: RecordingHandler
) -> None:
    rows = [*twoStations(), elementRow(), elementRow(**{"ELEMENT ID": "ABC", "ELEMENT-TYPE": "XYZ"})]
    result = convertRows(rows, logger, strict=False)

    assert len(result.networkElements) == 1, "the unclassifiable row is not written"
    assert list(result.networkElements["Element Typ"]) == ["LINE"]
    assert result.errorCount == 1
    assert "Skipping 1 row(s) with an unknown ELEMENT-TYPE" in logCapture.text(logging.WARNING)
    assert "Unknown ELEMENT-TYPE." in logCapture.text(logging.ERROR)


def testDroppedRowsDoNotShiftTheOthers(logger: logging.Logger) -> None:
    rows = [
        *twoStations(),
        elementRow(**{"ELEMENT ID": "BAD_1", "ELEMENT-TYPE": "???"}),
        elementRow(**{"ELEMENT ID": "LINE_A"}),
        elementRow(**{"ELEMENT ID": "BAD_2", "ELEMENT-TYPE": "NOPE"}),
        elementRow(**{"ELEMENT ID": "LINE_B"}),
    ]
    elements = convertRows(rows, logger, strict=False).networkElements

    assert list(elements["MJAP-ID"]) == ["Amprion_LINE_A", "Amprion_LINE_B"]


def testOutputStaysSchemaCleanDespiteErrors(tmp_path: Path, logger: logging.Logger) -> None:
    """Even a flawed run must not produce NA values or stray 'nan' strings."""
    rows = [
        stationRow(**{"Latitude": "", "STARTLIFETIME": "kaputt"}),
        elementRow(**{"ELEMENT ID": "BAD", "ELEMENT-TYPE": "XYZ"}),
        elementRow(**{"Station 2": "GibtsNicht_380"}),
    ]
    inputFile = writeExcel(rows, tmp_path / "input.xlsx")
    runConversion(inputFile, tmp_path / "out", logger)

    for name in (STATIONS_FILENAME, NETWORK_ELEMENTS_FILENAME):
        with (tmp_path / "out" / name).open(encoding="utf-8", newline="") as handle:
            for record in csv.DictReader(handle):
                assert all(value is not None for value in record.values())
                assert "nan" not in " ".join(record.values()).lower()


# --------------------------------------------------------------------------- #
# --strict restores the original guarantee
# --------------------------------------------------------------------------- #


def testStrictModeStillAborts(logger: logging.Logger) -> None:
    rows = [*twoStations(), elementRow(**{"Station 2": "GibtsNicht_380"})]
    with pytest.raises(ConversionError):
        convertRows(rows, logger, strict=True)


def testStrictModeWritesNothing(tmp_path: Path, logger: logging.Logger) -> None:
    rows = [*twoStations(), elementRow(**{"Station 2": "GibtsNicht_380"})]
    inputFile = writeExcel(rows, tmp_path / "input.xlsx")
    outputDir = tmp_path / "out"

    with pytest.raises(ConversionError):
        runConversion(inputFile, outputDir, logger, strict=True)

    assert not outputDir.exists() or list(outputDir.iterdir()) == []


def testBothModesReportTheSameFindings(
    tmp_path: Path, logger: logging.Logger, logCapture: RecordingHandler
) -> None:
    """Switching mode changes what is written, never what is reported."""
    rows = [*twoStations(), elementRow(**{"Station 2": "GibtsNicht_380"})]

    lenient = convertRows(rows, logger, strict=False)
    lenientErrors = [problem for _, problem in lenient.issues]

    with pytest.raises(ConversionError) as excinfo:
        convertRows(rows, logger, strict=True)
    strictErrors = [problem for _, problem in excinfo.value.issues]  # type: ignore[misc]

    assert [issue.problem for issue in lenientErrors] == [
        issue.problem for issue in strictErrors
    ]


def testSchemaFailuresStayFatalEvenInLenientMode(tmp_path: Path, logger: logging.Logger) -> None:
    """A missing input column is not a data error - it stops the run regardless."""
    import pandas as pd

    inputFile = tmp_path / "input.xlsx"
    pd.DataFrame([{"TSO": "Amprion", "ELEMENT ID": "Berlin_380"}]).to_excel(
        inputFile, index=False, engine="openpyxl"
    )

    with pytest.raises(ConversionError):
        runConversion(inputFile, tmp_path / "out", logger)

    assert not (tmp_path / "out" / STATIONS_FILENAME).exists()
