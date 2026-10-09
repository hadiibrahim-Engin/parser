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
                "TSO": "TennetD",
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
    assert element["MJAP-ID"] == "Amprion_LINE_471"
    assert element["Element Typ"] == "LINE"
    assert element["Stromkreisname - Langname"] == "Leitung Berlin - Hamburg"
    assert element["Stromkreisname - Kurzname"] == "Leitung Berlin - Hamburg"
    assert element["Spannung"] == "380"
    # All four station columns carry the MJAP-ID of the referenced station,
    # never its name.
    assert element["Station Anfang"] == "Amprion_Berlin_380"
    assert element["Station Ende"] == "TennetD_Hamburg_380"
    assert element["Station Anfang:MJAP-ID"] == "Amprion_Berlin_380"
    assert element["Station Ende:MJAP-ID"] == "TennetD_Hamburg_380"
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
        ("TIE", "Station 2"),  # case 14
        ("DCL", "Station 1"),  # case 15
    ],
)
def testMissingMandatoryStationRemovesTheElement(
    elementType: str,
    missingColumn: str,
    logger: logging.Logger,
    logCapture: RecordingHandler,
) -> None:
    """Cases 12-15: a mandatory type without a station is reported and dropped."""
    row = elementRow(**{"ELEMENT-TYPE": elementType, missingColumn: ""})
    result = convertRows([*twoStations(), row], logger)

    assert len(result.networkElements) == 0, "the element cannot be placed in the grid"
    warnings = logCapture.text(logging.WARNING)
    assert "Network element has no usable station reference." in warnings
    assert f"Field: {missingColumn}" in warnings
    assert f"ELEMENT-TYPE: {elementType}" in warnings
    assert f"Expected: {elementType} requires Station 1 and Station 2." in warnings
    assert "Action: Removing the element from the output and continuing." in warnings


def testOptionalStationReferenceBecomesNaN(
    logger: logging.Logger, logCapture: RecordingHandler
) -> None:
    """Case 16: BUB without Station 2 -> literal NaN plus a warning."""
    row = elementRow(
        **{"ELEMENT ID": "BUB_42", "ELEMENT-TYPE": "BUB", "Station 2": ""}
    )
    result = convertRows([*twoStations(), row], logger)

    element = result.networkElements.iloc[0]
    assert element["Station Ende"] == "NaN"
    assert element["Station Ende:MJAP-ID"] == "NaN"
    assert element["Station Anfang"] == "Amprion_Berlin_380"

    warnings = logCapture.text(logging.WARNING)
    assert "Station reference is missing." in warnings
    assert "ELEMENT ID: BUB_42" in warnings
    assert "Action: Writing NaN and continuing." in warnings
    assert result.warningCount == 1


@pytest.mark.parametrize("elementType", ["BUB"])
def testOptionalTypesWithoutAnyStationAreRemoved(
    elementType: str, logger: logging.Logger, logCapture: RecordingHandler
) -> None:
    """No station at all means the element cannot be placed - it is dropped."""
    row = elementRow(**{"ELEMENT-TYPE": elementType, "Station 1": "", "Station 2": ""})
    result = convertRows([*twoStations(), row], logger)

    assert len(result.networkElements) == 0
    assert "Network element has no usable station reference." in logCapture.text(logging.WARNING)


@pytest.mark.parametrize("elementType", ["BUB"])
def testOptionalTypesKeepOneSidedElements(
    elementType: str, logger: logging.Logger
) -> None:
    """One station is enough; the missing side keeps the NaN literal."""
    row = elementRow(
        **{"ELEMENT-TYPE": elementType, "Station 1": "Berlin_380", "Station 2": ""}
    )
    element = convertRows([*twoStations(), row], logger).networkElements.iloc[0]
    assert element["Station Anfang"] == "Amprion_Berlin_380"
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


def testUnknownElementTypeIsIgnored(logger, logCapture):
    row = elementRow(**{"ELEMENT ID": "ABC", "ELEMENT-TYPE": "XYZ"})
    result = convertRows([*twoStations(), row], logger)
    assert result.networkElements.empty
    assert result.errorCount == result.warningCount == 0
    assert "Ignoring 1 input row(s)" in logCapture.text(logging.INFO)


def testNetworkElementMjapIdDoesNotDependOnUcteCode(logger: logging.Logger) -> None:
    element = convertRows(
        [*twoStations(), elementRow(**{"UCTE CODE": ""})], logger
    ).networkElements.iloc[0]
    assert element["MJAP-ID"] == "Amprion_LINE_471"
    assert element["ID-UCTE"] == ""


def testNetworkElementWithoutOwnerIsFatal(
    logger: logging.Logger, logCapture: RecordingHandler
) -> None:
    with pytest.raises(ConversionError):
        convertRows([*twoStations(), elementRow(**{"TSO": ""})], logger)

    errors = logCapture.text(logging.ERROR)
    assert "Network element is missing the owner required for its MJAP-ID." in errors
    assert "Field: TSO" in errors


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
    assert result.networkElements.iloc[0]["Station Anfang"] == "Amprion_Berlin_380"
