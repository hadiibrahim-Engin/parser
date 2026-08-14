"""Tests der Netzelement-Transformation (Fälle 11-18)."""

from __future__ import annotations

import logging

import pytest
from conftest import RecordingHandler, convertRows, elementRow, stationRow

from excelToCsv.errors import ConversionError


def twoStations() -> list[dict[str, object]]:
    """Zwei reale Stationen, auf die Netzelemente verweisen können."""
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
    """Fall 11: LINE mit zwei gültigen Stationen."""
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
        ("LINE", "Station 2"),  # Fall 12
        ("TRA", "Station 1"),  # Fall 13
        ("TIE", "Station 2"),  # Fall 14
        ("DCL", "Station 1"),  # Fall 15
    ],
)
def testMissingMandatoryStationReferenceIsFatal(
    elementType: str,
    missingColumn: str,
    logger: logging.Logger,
    logCapture: RecordingHandler,
) -> None:
    """Fälle 12-15: Pflichttypen ohne Stationsreferenz brechen ab."""
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
    """Fall 16: GEN ohne Station 2 -> Literal NaN plus Warning."""
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
    """Fall 17: Referenz auf nicht vorhandene SUB-Station."""
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
    """Fall 18: unbekannter ELEMENT-TYPE."""
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
    """Stationen dürfen im Excel nach den Netzelementen stehen."""
    result = convertRows([elementRow(), *twoStations()], logger)
    assert result.networkElements.iloc[0]["Station Anfang"] == "Berlin_380"
