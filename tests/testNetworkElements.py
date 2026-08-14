"""Tests for the network element transformation (cases 11-18)."""

from __future__ import annotations

import logging

import pytest
from conftest import RecordingHandler, convertRows, elementRow, stationRow

from excelToCsv.errors import ConversionError


def twoStations() -> list[dict[str, object]]:
    """Two real stations that network elements can reference."""
    return [
        stationRow(**{"ELEMENT ID": "Berlin_380", "UCTE CODE": "DBERLIN1"}),
        stationRow(
            **{
                "ELEMENT ID": "Hamburg_380",
                "LONG-NAME": "Umspannwerk Hamburg",
                "Latitude": "53.551086",
                "Longitude": "9.993682",
                "UCTE CODE": "DHAMBRG1",
            }
        ),
    ]


def testLineWithTwoValidStations(logger: logging.Logger) -> None:
    """Case 11: LINE with two valid stations."""
    result = convertRows([*twoStations(), elementRow()], logger)

    assert len(result.networkElements) == 1
    element = result.networkElements.iloc[0]
    assert element["MJAP-ID"] == "LINE_471"
    assert element["Element Typ"] == "LINE"
    assert element["Stromkreisname - Langname"] == "Leitung Berlin - Hamburg"
    assert element["Stromkreisname - Kurzname"] == "Leitung Berlin - Hamburg"
    assert element["Spannung"] == "380"
    assert element["Station Anfang"] == "Berlin_380"
    assert element["Station Ende"] == "Hamburg_380"
    assert element["Station Anfang:MJAP-ID"] == "Berlin_380"
    assert element["Station Ende:MJAP-ID"] == "Hamburg_380"
    assert element["ID-UCTE"] == "DLINE471"
    assert element["Region"] == ""
    assert element["ID"] == ""
    assert element["Station T-1"] == ""
    assert element["Y-Knoten-1"] == ""
    assert element["Y-Knoten-2: MJAP-ID"] == ""


@pytest.mark.parametrize(
    ("elementType", "missingColumn"),
    [
        ("LINE", "Station 2"),  # case 12
        ("TRA", "Station 1"),  # case 13
        ("TIE", "Station 2"),  # case 14
        ("DCL", "Station 1"),  # case 15
    ],
)
def testMissingMandatoryStationReferenceIsFatal(
    elementType: str,
    missingColumn: str,
    logger: logging.Logger,
    logCapture: RecordingHandler,
) -> None:
    """Cases 12-15: mandatory types without a station reference abort."""
    row = elementRow(**{"ELEMENT-TYPE": elementType, missingColumn: ""})
    with pytest.raises(ConversionError):
        convertRows([*twoStations(), row], logger)

    errors = logCapture.text(logging.ERROR)
    assert "Required station reference is missing." in errors
    assert f"Field: {missingColumn}" in errors
    assert f"ELEMENT-TYPE: {elementType}" in errors
    assert f"Expected: {elementType} requires Station 1 and Station 2." in errors


def testOptionalStationReferenceBecomesNaN(
    logger: logging.Logger, logCapture: RecordingHandler
) -> None:
    """Case 16: GEN without Station 2 -> literal NaN plus a warning."""
    row = elementRow(
        **{"ELEMENT ID": "GEN_42", "ELEMENT-TYPE": "GEN", "Station 2": ""}
    )
    result = convertRows([*twoStations(), row], logger)

    element = result.networkElements.iloc[0]
    assert element["Station Ende"] == "NaN"
    assert element["Station Ende:MJAP-ID"] == "NaN"
    assert element["Station Anfang"] == "Berlin_380"

    warnings = logCapture.text(logging.WARNING)
    assert "Station reference is missing." in warnings
    assert "ELEMENT ID: GEN_42" in warnings
    assert "Action: Writing NaN and continuing." in warnings
    assert result.warningCount == 1


@pytest.mark.parametrize("elementType", ["CAP", "BUB", "GEN", "IND", "LOAD", "PPL", "PROD"])
def testAllOptionalTypesTolerateMissingStations(
    elementType: str, logger: logging.Logger
) -> None:
    row = elementRow(**{"ELEMENT-TYPE": elementType, "Station 1": "", "Station 2": ""})
    result = convertRows([*twoStations(), row], logger)
    element = result.networkElements.iloc[0]
    assert element["Station Anfang"] == "NaN"
    assert element["Station Ende"] == "NaN"


def testUnknownStationReferenceIsFatal(
    logger: logging.Logger, logCapture: RecordingHandler
) -> None:
    """Case 17: reference to a SUB station that does not exist."""
    row = elementRow(**{"Station 1": "HRA_380", "Station 2": "ABC_380"})
    with pytest.raises(ConversionError):
        convertRows([*twoStations(), row], logger)

    errors = logCapture.text(logging.ERROR)
    assert "Station reference does not match any station." in errors
    assert "Value: ABC_380" in errors
    assert "Value: HRA_380" in errors


def testUnknownElementTypeIsFatal(
    logger: logging.Logger, logCapture: RecordingHandler
) -> None:
    """Case 18: unknown ELEMENT-TYPE."""
    row = elementRow(**{"ELEMENT ID": "ABC", "ELEMENT-TYPE": "XYZ"})
    with pytest.raises(ConversionError):
        convertRows([*twoStations(), row], logger)

    errors = logCapture.text(logging.ERROR)
    assert "Unknown ELEMENT-TYPE." in errors
    assert "ELEMENT ID: ABC" in errors
    assert "ELEMENT-TYPE: XYZ" in errors
    assert "Row: 4" in errors


def testElementTypeIsCaseInsensitive(logger: logging.Logger) -> None:
    result = convertRows([*twoStations(), elementRow(**{"ELEMENT-TYPE": "line"})], logger)
    assert result.networkElements.iloc[0]["Element Typ"] == "LINE"


def testNetworkElementVoltageStaysText(logger: logging.Logger) -> None:
    rows = [
        *twoStations(),
        elementRow(**{"ELEMENT ID": "DCL_1", "ELEMENT-TYPE": "DCL", "VOLTAGE-LEVEL": "DC"}),
        elementRow(**{"ELEMENT ID": "LINE_2", "VOLTAGE-LEVEL": "380.0/110.0"}),
    ]
    result = convertRows(rows, logger)
    assert list(result.networkElements["Spannung"]) == ["DC", "380/110"]


def testIdenticalDuplicateElementsOnlyWarn(
    logger: logging.Logger, logCapture: RecordingHandler
) -> None:
    result = convertRows([*twoStations(), elementRow(), elementRow()], logger)
    assert len(result.networkElements) == 2
    assert "Duplicate network element ELEMENT ID with identical content" in logCapture.text(
        logging.WARNING
    )


def testConflictingDuplicateElementsAreFatal(logger: logging.Logger) -> None:
    with pytest.raises(ConversionError):
        convertRows(
            [*twoStations(), elementRow(), elementRow(**{"LONG-NAME": "Anderer Name"})],
            logger,
        )


def testNetworkElementsResolveStationsRegardlessOfRowOrder(logger: logging.Logger) -> None:
    """Stations may appear after the network elements in the spreadsheet."""
    result = convertRows([elementRow(), *twoStations()], logger)
    assert result.networkElements.iloc[0]["Station Anfang"] == "Berlin_380"
