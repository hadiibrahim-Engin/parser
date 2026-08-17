"""Tests for the placeholder that keeps all-empty columns readable as text.

Background: ``pandas.read_csv`` types a column that is empty in every row as
``float64`` full of ``NaN``. A downstream reader then cannot use the ``.str``
accessor on it (``Can only use .str accessor with string values``). The columns
without a defined source - ``Region``, ``IBN - Mehrfach``, ``ID`` and friends -
are exactly that case, so the written file carries a neutral filler.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

import pandas as pd
import pytest
from conftest import convertRows, elementRow, stationRow, writeExcel

from excelToCsv.cli import main
from excelToCsv.pipeline import runConversion
from excelToCsv.schema import (
    DEFAULT_EMPTY_PLACEHOLDER,
    NETWORK_ELEMENTS_FILENAME,
    STATIONS_FILENAME,
)
from excelToCsv.writer import fillFullyEmptyColumns, writeCsvFiles

#: Columns of Netzelemente.csv that never carry a value.
SOURCELESS_COLUMNS = (
    "Region",
    "ID",
    "IBN - Mehrfach",
    "ABN - Mehrfach",
    "Station T-1",
    "Station T-2",
    "Y-Knoten-2",
    "ID-GUID intern-1",
    "ID-GUID intern-2",
    "ID-OPC",
    "Stromkreisname - OPC-Name",
)


def sampleRows() -> list[dict[str, object]]:
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
        elementRow(),
    ]


def convertToFiles(tmp_path: Path, logger: logging.Logger, **options: object) -> Path:
    """Run a full conversion and return the output directory."""
    inputFile = writeExcel(sampleRows(), tmp_path / "input.xlsx")
    outputDir = tmp_path / "out"
    runConversion(inputFile, outputDir, logger, **options)  # type: ignore[arg-type]
    return outputDir


# --------------------------------------------------------------------------- #
# The actual downstream failure
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("column", SOURCELESS_COLUMNS)
def testSourcelessColumnsReadBackAsText(
    column: str, tmp_path: Path, logger: logging.Logger
) -> None:
    """A plain ``read_csv`` - exactly what the downstream library does."""
    outputDir = convertToFiles(tmp_path, logger)
    frame = pd.read_csv(outputDir / NETWORK_ELEMENTS_FILENAME)

    assert frame[column].dtype != "float64"
    frame[column].str.split(";")  # must not raise AttributeError


def testColumnThatHappensToBeEmptyIsCoveredToo(tmp_path: Path, logger: logging.Logger) -> None:
    """``IBN`` has a source but can still be empty in every row of a file."""
    rows = [row | {"STARTLIFETIME": "", "ENDLIFETIME": ""} for row in sampleRows()]
    inputFile = writeExcel(rows, tmp_path / "input.xlsx")
    runConversion(inputFile, tmp_path / "out", logger)

    frame = pd.read_csv(tmp_path / "out" / STATIONS_FILENAME)
    assert frame["IBN"].dtype != "float64"
    frame["IBN"].str.split(";")


def testColumnsWithRealValuesAreUntouched(tmp_path: Path, logger: logging.Logger) -> None:
    outputDir = convertToFiles(tmp_path, logger)
    with (outputDir / NETWORK_ELEMENTS_FILENAME).open(encoding="utf-8", newline="") as handle:
        record = next(iter(csv.DictReader(handle)))

    assert record["MJAP-ID"] == "Amprion_LINE_471"
    assert record["Station Anfang"] == "Amprion_Berlin_380"
    assert record["Element Typ"] == "LINE"
    assert record["IBN"] == "09.05.2025", "a populated column keeps its exact values"


def testPlaceholderIsBlankNotABusinessValue(tmp_path: Path, logger: logging.Logger) -> None:
    """The filler must never look like data - it has to strip to nothing."""
    outputDir = convertToFiles(tmp_path, logger)
    with (outputDir / NETWORK_ELEMENTS_FILENAME).open(encoding="utf-8", newline="") as handle:
        record = next(iter(csv.DictReader(handle)))

    for column in SOURCELESS_COLUMNS:
        assert record[column] == DEFAULT_EMPTY_PLACEHOLDER
        assert record[column].strip() == "", f"{column} must not carry invented content"


def testSingleMissingValueStaysTrulyEmpty(tmp_path: Path, logger: logging.Logger) -> None:
    """Only whole empty columns are filled, never an individual gap."""
    rows = [
        stationRow(),
        stationRow(
            **{
                "ELEMENT ID": "Hamburg_380",
                "Latitude": "53.551086",
                "Longitude": "9.993682",
                "UCTE CODE": "DHAMBRG1",
                "STARTLIFETIME": "",
            }
        ),
    ]
    inputFile = writeExcel(rows, tmp_path / "input.xlsx")
    runConversion(inputFile, tmp_path / "out", logger)

    with (tmp_path / "out" / STATIONS_FILENAME).open(encoding="utf-8", newline="") as handle:
        records = list(csv.DictReader(handle))

    assert records[0]["IBN"] == "09.05.2025"
    assert records[1]["IBN"] == "", "the column has values, so the gap stays a real gap"


# --------------------------------------------------------------------------- #
# The in-memory records stay clean
# --------------------------------------------------------------------------- #


def testInMemoryRecordsKeepGenuineEmptyStrings(logger: logging.Logger) -> None:
    """The filler is a serialization concern, not part of the transformation."""
    result = convertRows(sampleRows(), logger)

    assert result.networkElements.iloc[0]["Region"] == ""
    assert result.networkElements.iloc[0]["ID"] == ""
    assert result.stations.iloc[0]["ID-OPC"] == ""


# --------------------------------------------------------------------------- #
# fillFullyEmptyColumns in isolation
# --------------------------------------------------------------------------- #


def testFillOnlyTouchesFullyEmptyColumns() -> None:
    frame = pd.DataFrame(
        {"populated": ["a", ""], "empty": ["", ""], "alsoEmpty": ["", ""]}, dtype=object
    )
    filled = fillFullyEmptyColumns(frame, " ")

    assert list(filled["populated"]) == ["a", ""], "a gap in a populated column stays a gap"
    assert list(filled["empty"]) == [" ", " "]
    assert list(filled["alsoEmpty"]) == [" ", " "]


def testFillLeavesTheOriginalFrameAlone() -> None:
    frame = pd.DataFrame({"empty": ["", ""]}, dtype=object)
    fillFullyEmptyColumns(frame, " ")
    assert list(frame["empty"]) == ["", ""]


def testEmptyPlaceholderDisablesTheBehaviour() -> None:
    frame = pd.DataFrame({"empty": ["", ""]}, dtype=object)
    assert list(fillFullyEmptyColumns(frame, "")["empty"]) == ["", ""]


def testFillHandlesAnEmptyFrame() -> None:
    frame = pd.DataFrame({"a": []}, dtype=object)
    assert fillFullyEmptyColumns(frame, " ").empty


# --------------------------------------------------------------------------- #
# Opting out
# --------------------------------------------------------------------------- #


def testWriterCanKeepColumnsTrulyEmpty(tmp_path: Path, logger: logging.Logger) -> None:
    result = convertRows(sampleRows(), logger)
    writeCsvFiles(
        result.stations, result.networkElements, tmp_path, logger, emptyPlaceholder=""
    )

    with (tmp_path / NETWORK_ELEMENTS_FILENAME).open(encoding="utf-8", newline="") as handle:
        record = next(iter(csv.DictReader(handle)))
    assert record["Region"] == ""


def testCliCanDisableThePlaceholder(tmp_path: Path) -> None:
    inputFile = writeExcel(sampleRows(), tmp_path / "input.xlsx")
    main(
        [
            str(inputFile),
            "-o",
            str(tmp_path / "out"),
            "--empty-placeholder",
            "",
            "--no-color",
        ]
    )

    frame = pd.read_csv(tmp_path / "out" / NETWORK_ELEMENTS_FILENAME)
    assert frame["Region"].dtype == "float64", "opting out restores the old behaviour"


def testHeaderIsUnaffectedByThePlaceholder(tmp_path: Path, logger: logging.Logger) -> None:
    """The output contract itself must not shift."""
    from excelToCsv.schema import NETWORK_ELEMENT_COLUMNS, STATION_COLUMNS

    outputDir = convertToFiles(tmp_path, logger)
    for name, columns in (
        (STATIONS_FILENAME, STATION_COLUMNS),
        (NETWORK_ELEMENTS_FILENAME, NETWORK_ELEMENT_COLUMNS),
    ):
        with (outputDir / name).open(encoding="utf-8", newline="") as handle:
            assert next(csv.reader(handle)) == list(columns)
