"""Tests for the output contract and the write path (cases 23-25)."""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

import pytest
from conftest import RecordingHandler, convertRows, elementRow, stationRow, writeExcel

from excelToCsv.cli import EXIT_CONVERSION_ERROR, EXIT_SUCCESS, main
from excelToCsv.errors import ConversionError
from excelToCsv.pipeline import runConversion
from excelToCsv.schema import (
    NETWORK_ELEMENT_COLUMNS,
    NETWORK_ELEMENTS_FILENAME,
    STATION_COLUMNS,
    STATIONS_FILENAME,
)

EXPECTED_STATION_HEADER = (
    '"Eigentümer","MJAP-ID","Stationsname - Langname","lat","long","Spannung","IBN","ABN",'
    '"Stationsname - Kurzname","reales UW","Stationsname - OPC-Name","ID-GUID intern-1",'
    '"ID-GUID intern-2","ID-OPC","ID-UCTE","relevant für","ID","Kommentar","IBN - Mehrfach",'
    '"ABN - Mehrfach"'
)

EXPECTED_NETWORK_ELEMENT_HEADER = (
    '"Eigentümer","MJAP-ID","Stromkreisname - Langname","Region","Element Typ","Spannung",'
    '"relevant für","IBN","ABN","IBN - Mehrfach","ABN - Mehrfach","Station Anfang",'
    '"Station Ende","Station T-1","Station T-2","Y-Knoten-1","Y-Knoten-2",'
    '"Stromkreisname - Kurzname","Stromkreisname - OPC-Name","ID-GUID intern-1",'
    '"ID-GUID intern-2","ID-OPC","ID-UCTE","ID","Station Anfang:MJAP-ID","Station Ende:MJAP-ID",'
    '"Station T-1:MJAP-ID","Station T-2:MJAP-ID","Y-Knoten-1: MJAP-ID","Y-Knoten-2: MJAP-ID"'
)


def parseHeaderSpec(headerLine: str) -> list[str]:
    """Parse the header line exactly as given in the specification."""
    return next(csv.reader([headerLine]))


def sampleRows() -> list[dict[str, object]]:
    """A small, business-valid sample with stations and a network element."""
    return [
        stationRow(),
        stationRow(
            **{
                "ELEMENT ID": "Hamburg_380",
                "LONG-NAME": "Umspannwerk Hämburg",
                "Latitude": "53.551086",
                "Longitude": "9.993682",
                "UCTE CODE": "DHAMBRG1",
                "Interesting/Relevant for (50Hertz)": 1,
            }
        ),
        elementRow(),
    ]


def testStationHeaderMatchesSpecification() -> None:
    """Case 23: exact header order of Stationen.csv."""
    assert list(STATION_COLUMNS) == parseHeaderSpec(EXPECTED_STATION_HEADER)


def testNetworkElementHeaderMatchesSpecification() -> None:
    """Case 24: exact header order of Netzelemente.csv."""
    assert list(NETWORK_ELEMENT_COLUMNS) == parseHeaderSpec(EXPECTED_NETWORK_ELEMENT_HEADER)


def testWrittenCsvHeadersAreExact(tmp_path: Path, logger: logging.Logger) -> None:
    inputFile = writeExcel(sampleRows(), tmp_path / "input.xlsx")
    runConversion(inputFile, tmp_path / "out", logger)

    stationsFile = tmp_path / "out" / STATIONS_FILENAME
    elementsFile = tmp_path / "out" / NETWORK_ELEMENTS_FILENAME

    with stationsFile.open(encoding="utf-8", newline="") as handle:
        assert next(csv.reader(handle)) == list(STATION_COLUMNS)
    with elementsFile.open(encoding="utf-8", newline="") as handle:
        assert next(csv.reader(handle)) == list(NETWORK_ELEMENT_COLUMNS)


def testWrittenCsvContentIsClean(tmp_path: Path, logger: logging.Logger) -> None:
    inputFile = writeExcel(sampleRows(), tmp_path / "input.xlsx")
    runConversion(inputFile, tmp_path / "out", logger)

    text = (tmp_path / "out" / STATIONS_FILENAME).read_text(encoding="utf-8")
    assert "Hämburg" in text, "umlauts must be preserved"
    # JSON lists are quoted per RFC 4180 ("" for an inner ").
    assert '"[""380""]"' in text

    with (tmp_path / "out" / STATIONS_FILENAME).open(encoding="utf-8", newline="") as handle:
        records = list(csv.DictReader(handle))
    assert len(records) == 2
    # Round trip: the CSV field yields exactly the JSON list again.
    assert records[0]["Spannung"] == '["380"]'
    assert json.loads(records[0]["Spannung"]) == ["380"]
    assert records[1]["relevant für"] == "50Hertz"
    assert all("nan" not in value.lower() for record in records for value in record.values())

    with (tmp_path / "out" / NETWORK_ELEMENTS_FILENAME).open(
        encoding="utf-8", newline=""
    ) as handle:
        elementRecords = list(csv.DictReader(handle))
    assert len(elementRecords) == 1
    assert records[0]["MJAP-ID"] == "Amprion_Berlin_380"
    assert elementRecords[0]["MJAP-ID"] == "Amprion_LINE_471"
    assert elementRecords[0]["Station Anfang"] == "Berlin_380"
    assert elementRecords[0]["Station Anfang:MJAP-ID"] == "Amprion_Berlin_380"
    assert elementRecords[0]["Station Ende:MJAP-ID"] == "Amprion_Hamburg_380"
    assert elementRecords[0]["Region"] == ""


def testNoCsvFilesOnFatalError(tmp_path: Path, logger: logging.Logger) -> None:
    """Case 25: in strict mode a fatal error creates not a single CSV file."""
    rows = [*sampleRows(), elementRow(**{"ELEMENT ID": "LINE_9", "Station 2": ""})]
    inputFile = writeExcel(rows, tmp_path / "input.xlsx")
    outputDir = tmp_path / "out"

    with pytest.raises(ConversionError):
        runConversion(inputFile, outputDir, logger, strict=True)

    assert not (outputDir / STATIONS_FILENAME).exists()
    assert not (outputDir / NETWORK_ELEMENTS_FILENAME).exists()
    assert not outputDir.exists() or list(outputDir.iterdir()) == []


def testQuoteAllOptionQuotesEveryField(tmp_path: Path, logger: logging.Logger) -> None:
    inputFile = writeExcel(sampleRows(), tmp_path / "input.xlsx")
    runConversion(inputFile, tmp_path / "out", logger, quoteAll=True)

    firstLine = (tmp_path / "out" / STATIONS_FILENAME).read_text(encoding="utf-8").splitlines()[0]
    assert firstLine == EXPECTED_STATION_HEADER


def testCliReturnsZeroOnSuccess(
    tmp_path: Path, logCapture: RecordingHandler
) -> None:
    inputFile = writeExcel(sampleRows(), tmp_path / "input.xlsx")
    exitCode = main([str(inputFile), "--output-dir", str(tmp_path / "out"), "--no-color"])

    assert exitCode == EXIT_SUCCESS
    assert (tmp_path / "out" / STATIONS_FILENAME).is_file()
    assert (tmp_path / "out" / NETWORK_ELEMENTS_FILENAME).is_file()


def testCliReturnsNonZeroOnFatalError(tmp_path: Path) -> None:
    """--strict keeps the original guarantee: no output at all."""
    rows = [*sampleRows(), elementRow(**{"ELEMENT ID": "LINE_9", "Station 1": ""})]
    inputFile = writeExcel(rows, tmp_path / "input.xlsx")
    exitCode = main(
        [str(inputFile), "--output-dir", str(tmp_path / "out"), "--strict", "--no-color"]
    )

    assert exitCode == EXIT_CONVERSION_ERROR
    assert not (tmp_path / "out" / STATIONS_FILENAME).exists()


def testCliReportsMissingInputFile(tmp_path: Path) -> None:
    exitCode = main([str(tmp_path / "missing.xlsx"), "--no-color"])
    assert exitCode == EXIT_CONVERSION_ERROR


def testSheetNameIsLogged(tmp_path: Path, logger: logging.Logger, logCapture: RecordingHandler) -> None:
    inputFile = writeExcel(sampleRows(), tmp_path / "input.xlsx", sheetName="Netzdaten")
    result = runConversion(inputFile, tmp_path / "out", logger)

    assert result.sheetName == "Netzdaten"
    assert "Using worksheet: Netzdaten" in logCapture.text(logging.INFO)


def testMissingRequiredColumnIsFatal(
    tmp_path: Path, logger: logging.Logger, logCapture: RecordingHandler
) -> None:
    import pandas as pd

    frame = pd.DataFrame([{"TSO": "Amprion", "ELEMENT ID": "Berlin_380"}])
    inputFile = tmp_path / "input.xlsx"
    frame.to_excel(inputFile, index=False, engine="openpyxl")

    with pytest.raises(ConversionError):
        runConversion(inputFile, tmp_path / "out", logger)

    assert "Missing required input column: LONG-NAME" in logCapture.text(logging.ERROR)


def testBothReadEnginesProduceIdenticalOutput(tmp_path: Path, logger: logging.Logger) -> None:
    """The optional calamine accelerator must not change the result."""
    pytest.importorskip("python_calamine")
    inputFile = writeExcel(sampleRows(), tmp_path / "input.xlsx")

    runConversion(inputFile, tmp_path / "openpyxl", logger, engine="openpyxl")
    runConversion(inputFile, tmp_path / "calamine", logger, engine="calamine")

    for name in (STATIONS_FILENAME, NETWORK_ELEMENTS_FILENAME):
        assert (tmp_path / "openpyxl" / name).read_bytes() == (
            tmp_path / "calamine" / name
        ).read_bytes()


def testWhitespaceInHeadersIsTolerated(tmp_path: Path, logger: logging.Logger) -> None:
    rows = sampleRows()
    renamed = [{f"  {key} ": value for key, value in row.items()} for row in rows]
    inputFile = writeExcel(renamed, tmp_path / "input.xlsx")

    result = runConversion(inputFile, tmp_path / "out", logger)
    assert len(result.stations) == 2
