"""Tests for the station transformation (cases 1-4, 8, 22)."""

from __future__ import annotations

import logging

import pytest
from conftest import RecordingHandler, convertRows, elementRow, stationRow

from excelToCsv.errors import ConversionError


def testRealStationIsMappedCompletely(logger: logging.Logger) -> None:
    """Case 1: a normal, real SUB station."""
    result = convertRows([stationRow()], logger)

    assert len(result.stations) == 1
    assert len(result.networkElements) == 0
    station = result.stations.iloc[0]
    assert station["Eigentümer"] == "Amprion"
    assert station["MJAP-ID"] == "Berlin_380"
    assert station["Stationsname - Langname"] == "Umspannwerk Berlin"
    assert station["Stationsname - Kurzname"] == "Umspannwerk Berlin"
    assert station["lat"] == "52.459373"
    assert station["long"] == "13.361402"
    assert station["Spannung"] == '["380"]'
    assert station["IBN"] == "09.05.2025"
    assert station["ABN"] == ""
    assert station["reales UW"] == "Wahr"
    assert station["ID-UCTE"] == "DBERLIN1"
    assert station["ID"] == "DBERLIN1"
    assert station["Kommentar"] == "Beispielkommentar"
    assert station["Stationsname - OPC-Name"] == ""
    assert station["ID-GUID intern-1"] == ""
    assert station["ID-GUID intern-2"] == ""
    assert station["ID-OPC"] == ""
    assert station["IBN - Mehrfach"] == ""
    assert station["ABN - Mehrfach"] == ""


def testVirtualStationIsFlagged(logger: logging.Logger) -> None:
    """Case 2: virtual X station -> reales UW = Falsch."""
    result = convertRows(
        [stationRow(**{"ELEMENT ID": "Xb_380", "LONG-NAME": "X-Knoten b"})],
        logger,
    )
    station = result.stations.iloc[0]
    assert station["MJAP-ID"] == "Xb_380"
    assert station["reales UW"] == "Falsch"


def testMissingLatitudeIsFatal(logger: logging.Logger, logCapture: RecordingHandler) -> None:
    """Case 3: SUB without a latitude."""
    with pytest.raises(ConversionError):
        convertRows([stationRow(Latitude="")], logger)

    errors = logCapture.text(logging.ERROR)
    assert "Missing station coordinate." in errors
    assert "Field: Latitude" in errors
    assert "Row: 2" in errors
    assert "ELEMENT ID: Berlin_380" in errors
    assert "ELEMENT-TYPE: SUB" in errors
    assert "Expected: Every SUB station requires Latitude and Longitude." in errors


def testMissingLongitudeIsFatal(logger: logging.Logger, logCapture: RecordingHandler) -> None:
    """Case 4: SUB without a longitude."""
    with pytest.raises(ConversionError):
        convertRows([stationRow(Longitude=None)], logger)

    errors = logCapture.text(logging.ERROR)
    assert "Field: Longitude" in errors
    assert "Value: <empty>" in errors


def testVirtualStationAlsoRequiresCoordinates(logger: logging.Logger) -> None:
    """Virtual stations need coordinates as well."""
    with pytest.raises(ConversionError):
        convertRows([stationRow(**{"ELEMENT ID": "Xb_380", "Latitude": ""})], logger)


def testCoordinateWithDecimalCommaIsAccepted(logger: logging.Logger) -> None:
    """Case 5 (end to end): a decimal comma is normalized to a dot."""
    result = convertRows(
        [stationRow(Latitude="52,459373", Longitude="13,361402")],
        logger,
    )
    station = result.stations.iloc[0]
    assert station["lat"] == "52.459373"
    assert station["long"] == "13.361402"


def testStationVoltageIsJsonList(logger: logging.Logger) -> None:
    """Case 8: station voltage as a JSON list."""
    single = convertRows([stationRow(**{"VOLTAGE-LEVEL": "380.0"})], logger)
    assert single.stations.iloc[0]["Spannung"] == '["380"]'

    multiple = convertRows([stationRow(**{"VOLTAGE-LEVEL": "380.0/110.0"})], logger)
    assert multiple.stations.iloc[0]["Spannung"] == '["380","110"]'

    empty = convertRows([stationRow(**{"VOLTAGE-LEVEL": ""})], logger)
    assert empty.stations.iloc[0]["Spannung"] == "[]"


def testInvalidDateIsFatal(logger: logging.Logger, logCapture: RecordingHandler) -> None:
    """Case 10: an invalid date."""
    with pytest.raises(ConversionError):
        convertRows([stationRow(STARTLIFETIME="irgendwann")], logger)

    errors = logCapture.text(logging.ERROR)
    assert "Value is not a valid date." in errors
    assert "Field: STARTLIFETIME" in errors
    assert "Value: irgendwann" in errors


def testDuplicateStationIdIsFatal(logger: logging.Logger, logCapture: RecordingHandler) -> None:
    """Case 22: a duplicate station id names both rows."""
    with pytest.raises(ConversionError):
        convertRows(
            [
                stationRow(**{"ELEMENT ID": "HRA_380"}),
                stationRow(**{"ELEMENT ID": "HRA_380", "LONG-NAME": "Anderer Name"}),
            ],
            logger,
        )

    errors = logCapture.text(logging.ERROR)
    assert "Duplicate station ELEMENT ID" in errors
    assert "row(s): 2, 3" in errors


def testStationWithoutElementIdIsFatal(logger: logging.Logger) -> None:
    with pytest.raises(ConversionError):
        convertRows([stationRow(**{"ELEMENT ID": ""})], logger)


def testForgottenDecimalSeparatorIsRepaired(
    logger: logging.Logger, logCapture: RecordingHandler
) -> None:
    """A coordinate whose decimal separator was forgotten is fixed, with a warning."""
    rows = [
        stationRow(**{"ELEMENT ID": "A_380", "Latitude": "52.459373", "Longitude": "13.361402"}),
        stationRow(**{"ELEMENT ID": "B_380", "Latitude": "53.551086", "Longitude": "9.993682"}),
        stationRow(**{"ELEMENT ID": "C_380", "Latitude": "48123456", "Longitude": "11361402"}),
    ]
    result = convertRows(rows, logger)

    repaired = result.stations.iloc[2]
    assert repaired["lat"] == "48.123456"
    assert repaired["long"] == "11.361402"

    warnings = logCapture.text(logging.WARNING)
    assert "Coordinate had no decimal separator" in warnings
    assert "48123456 -> 48.123456" in warnings
    assert "Action: Writing the corrected value 48.123456 and continuing." in warnings
    assert "ELEMENT ID: C_380" in warnings
    assert "Row: 4" in warnings
    assert result.warningCount == 2, "one warning per repaired coordinate"


def testRepairUsesTheColumnPrecisionNotTheWidestFit(logger: logging.Logger) -> None:
    """With 5-decimal neighbours, 11361402 must become 113.61402, not 11.361402."""
    rows = [
        stationRow(**{"ELEMENT ID": "A_380", "Latitude": "48.12345", "Longitude": "113.61402"}),
        stationRow(**{"ELEMENT ID": "B_380", "Latitude": "48.98765", "Longitude": "114.11111"}),
        stationRow(**{"ELEMENT ID": "C_380", "Latitude": "4812345", "Longitude": "11361402"}),
    ]
    result = convertRows(rows, logger)

    repaired = result.stations.iloc[2]
    assert repaired["lat"] == "48.12345"
    assert repaired["long"] == "113.61402"


def testRepairIsFatalWithoutPrecisionEvidence(
    logger: logging.Logger, logCapture: RecordingHandler
) -> None:
    """Without an intact neighbour the precision is unknown - never guess."""
    with pytest.raises(ConversionError):
        convertRows([stationRow(**{"ELEMENT ID": "C_380", "Latitude": "48123456"})], logger)

    errors = logCapture.text(logging.ERROR)
    assert "decimal separator appears to be missing" in errors


def testValidWholeNumberCoordinateIsNotRepaired(logger: logging.Logger) -> None:
    """52 is a legitimate latitude and must survive untouched."""
    rows = [
        stationRow(**{"ELEMENT ID": "A_380", "Latitude": "52.459373", "Longitude": "13.361402"}),
        stationRow(**{"ELEMENT ID": "B_380", "Latitude": "52", "Longitude": "13"}),
    ]
    result = convertRows(rows, logger)

    assert result.stations.iloc[1]["lat"] == "52"
    assert result.stations.iloc[1]["long"] == "13"
    assert result.warningCount == 0


def testOutOfRangeWithSeparatorRemainsFatal(
    logger: logging.Logger, logCapture: RecordingHandler
) -> None:
    """A genuine out-of-range value must not be silently reinterpreted."""
    rows = [
        stationRow(**{"ELEMENT ID": "A_380", "Latitude": "52.459373", "Longitude": "13.361402"}),
        stationRow(**{"ELEMENT ID": "B_380", "Latitude": "152.5", "Longitude": "13.361402"}),
    ]
    with pytest.raises(ConversionError):
        convertRows(rows, logger)

    assert "Coordinate is out of range." in logCapture.text(logging.ERROR)


def testStationCountsAreLogged(logger: logging.Logger, logCapture: RecordingHandler) -> None:
    convertRows([stationRow(), elementRow(**{"Station 2": "Berlin_380"})], logger)
    info = logCapture.text(logging.INFO)
    assert "Found 1 station(s)." in info
    assert "Found 1 network element(s)." in info
    assert "Validation successful." in info
