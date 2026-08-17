"""Tests for the JSON-configurable target format."""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

import pytest
from conftest import convertRows, elementRow, stationRow, writeExcel

from excelToCsv.cli import main
from excelToCsv.errors import ConversionError
from excelToCsv.pipeline import runConversion
from excelToCsv.schema import NETWORK_ELEMENTS_FILENAME, STATIONS_FILENAME
from excelToCsv.targetFormat import TargetFormat, loadTargetFormat
from excelToCsv.writer import writeCsvFiles


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


def writeDefinition(tmp_path: Path, definition: dict[str, object]) -> Path:
    path = tmp_path / "targetFormat.json"
    path.write_text(json.dumps(definition), encoding="utf-8")
    return path


def readCsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


# --------------------------------------------------------------------------- #
# Element type translation
# --------------------------------------------------------------------------- #


def testElementTypesAreTranslated(tmp_path: Path, logger: logging.Logger) -> None:
    definition = writeDefinition(
        tmp_path, {"elementTypes": {"LINE": "Stromkreis", "GEN": "Generator"}}
    )
    inputFile = writeExcel(sampleRows(), tmp_path / "input.xlsx")

    runConversion(inputFile, tmp_path / "out", logger, targetFormatPath=definition)

    record = readCsv(tmp_path / "out" / NETWORK_ELEMENTS_FILENAME)[0]
    assert record["Element Typ"] == "Stromkreis"


def testUnmappedElementTypesStayUnchanged(tmp_path: Path, logger: logging.Logger) -> None:
    definition = writeDefinition(tmp_path, {"elementTypes": {"TRA": "Transformator"}})
    inputFile = writeExcel(sampleRows(), tmp_path / "input.xlsx")

    runConversion(inputFile, tmp_path / "out", logger, targetFormatPath=definition)

    assert readCsv(tmp_path / "out" / NETWORK_ELEMENTS_FILENAME)[0]["Element Typ"] == "LINE"


def testTranslationDoesNotTouchTheInputSide(tmp_path: Path, logger: logging.Logger) -> None:
    """A translated type must not break classification or validation."""
    definition = writeDefinition(tmp_path, {"elementTypes": {"SUB": "Station"}})
    inputFile = writeExcel(sampleRows(), tmp_path / "input.xlsx")

    result = runConversion(inputFile, tmp_path / "out", logger, targetFormatPath=definition)

    assert len(result.stations) == 2, "SUB rows are still recognized as stations"
    assert len(result.networkElements) == 1


# --------------------------------------------------------------------------- #
# Column renames
# --------------------------------------------------------------------------- #


def testStationColumnsAreRenamed(tmp_path: Path, logger: logging.Logger) -> None:
    definition = writeDefinition(
        tmp_path, {"stationColumns": {"MJAP-ID": "Anlagen-ID", "Kommentar": "Bemerkung"}}
    )
    inputFile = writeExcel(sampleRows(), tmp_path / "input.xlsx")

    runConversion(inputFile, tmp_path / "out", logger, targetFormatPath=definition)

    with (tmp_path / "out" / STATIONS_FILENAME).open(encoding="utf-8", newline="") as handle:
        header = next(csv.reader(handle))
    assert "Anlagen-ID" in header
    assert "Bemerkung" in header
    assert "MJAP-ID" not in header
    assert header.index("Anlagen-ID") == 1, "the column order is preserved"


def testNetworkElementColumnsAreRenamed(tmp_path: Path, logger: logging.Logger) -> None:
    definition = writeDefinition(
        tmp_path, {"networkElementColumns": {"Element Typ": "Betriebsmitteltyp"}}
    )
    inputFile = writeExcel(sampleRows(), tmp_path / "input.xlsx")

    runConversion(inputFile, tmp_path / "out", logger, targetFormatPath=definition)

    record = readCsv(tmp_path / "out" / NETWORK_ELEMENTS_FILENAME)[0]
    assert record["Betriebsmitteltyp"] == "LINE"
    assert "Element Typ" not in record


def testRenameAndTranslationCombine(tmp_path: Path, logger: logging.Logger) -> None:
    definition = writeDefinition(
        tmp_path,
        {
            "elementTypes": {"LINE": "Stromkreis"},
            "networkElementColumns": {"Element Typ": "Typ"},
        },
    )
    inputFile = writeExcel(sampleRows(), tmp_path / "input.xlsx")

    runConversion(inputFile, tmp_path / "out", logger, targetFormatPath=definition)

    assert readCsv(tmp_path / "out" / NETWORK_ELEMENTS_FILENAME)[0]["Typ"] == "Stromkreis"


def testWithoutADefinitionTheContractIsUntouched(tmp_path: Path, logger: logging.Logger) -> None:
    inputFile = writeExcel(sampleRows(), tmp_path / "input.xlsx")
    runConversion(inputFile, tmp_path / "out", logger)

    record = readCsv(tmp_path / "out" / NETWORK_ELEMENTS_FILENAME)[0]
    assert record["Element Typ"] == "LINE"
    assert "MJAP-ID" in record


# --------------------------------------------------------------------------- #
# Guard rails
# --------------------------------------------------------------------------- #


def testRenameToAnExistingNameIsRejected(tmp_path: Path, logger: logging.Logger) -> None:
    """Two columns with the same name would make the output ambiguous."""
    definition = writeDefinition(tmp_path, {"stationColumns": {"MJAP-ID": "ID"}})

    with pytest.raises(ConversionError, match="duplicate column"):
        loadTargetFormat(definition, logger)


def testUnknownColumnOnlyWarns(
    tmp_path: Path, logger: logging.Logger, logCapture: object
) -> None:
    definition = writeDefinition(tmp_path, {"stationColumns": {"Gibtsnicht": "Egal"}})
    targetFormat = loadTargetFormat(definition, logger)
    assert targetFormat.stationColumns == {"Gibtsnicht": "Egal"}


def testMissingFileIsFatal(tmp_path: Path, logger: logging.Logger) -> None:
    with pytest.raises(ConversionError, match="not found"):
        loadTargetFormat(tmp_path / "nope.json", logger)


def testBrokenJsonIsFatal(tmp_path: Path, logger: logging.Logger) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{ not json", encoding="utf-8")
    with pytest.raises(ConversionError, match="Cannot read"):
        loadTargetFormat(path, logger)


def testNonStringTargetIsFatal(tmp_path: Path, logger: logging.Logger) -> None:
    definition = writeDefinition(tmp_path, {"elementTypes": {"LINE": 42}})
    with pytest.raises(ConversionError, match="must map to a string"):
        loadTargetFormat(definition, logger)


def testCommentKeysAreAccepted(tmp_path: Path, logger: logging.Logger) -> None:
    """Keys starting with '_' are the usual JSON comment convention."""
    definition = writeDefinition(
        tmp_path, {"_comment": "erklaerender Text", "elementTypes": {"LINE": "Stromkreis"}}
    )
    assert loadTargetFormat(definition, logger).elementTypes == {"LINE": "Stromkreis"}


def testNoDefinitionYieldsAnEmptyFormat(logger: logging.Logger) -> None:
    empty = loadTargetFormat(None, logger)
    assert empty.isEmpty
    assert empty.translateElementType("LINE") == "LINE"


def testShippedExampleFileIsValid(logger: logging.Logger) -> None:
    """The example next to the code must actually load."""
    example = Path(__file__).resolve().parents[1] / "targetFormat.example.json"
    targetFormat = loadTargetFormat(example, logger)
    assert targetFormat.translateElementType("LINE") == "Stromkreis"
    assert targetFormat.translateElementType("SUB") == "SUB", "stations keep their own mapping"


def testCliAcceptsTheOption(tmp_path: Path) -> None:
    definition = writeDefinition(tmp_path, {"elementTypes": {"LINE": "Stromkreis"}})
    inputFile = writeExcel(sampleRows(), tmp_path / "input.xlsx")

    main(
        [
            str(inputFile),
            "-o",
            str(tmp_path / "out"),
            "--target-format",
            str(definition),
            "--no-color",
        ]
    )
    assert readCsv(tmp_path / "out" / NETWORK_ELEMENTS_FILENAME)[0]["Element Typ"] == "Stromkreis"


def testInMemoryRecordsKeepTheContractNames(
    tmp_path: Path, logger: logging.Logger
) -> None:
    """Renaming is a serialization step - convertTable stays on the contract."""
    result = convertRows(sampleRows(), logger)
    assert "Element Typ" in result.networkElements.columns
    assert result.networkElements.iloc[0]["Element Typ"] == "LINE"

    writeCsvFiles(
        result.stations,
        result.networkElements,
        tmp_path,
        logger,
        targetFormat=TargetFormat(elementTypes={"LINE": "Stromkreis"}),
    )
    assert readCsv(tmp_path / NETWORK_ELEMENTS_FILENAME)[0]["Element Typ"] == "Stromkreis"
