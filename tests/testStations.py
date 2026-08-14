"""Tests der Stationen-Transformation (Fälle 1-4, 8, 22)."""

from __future__ import annotations

import logging

import pytest
from conftest import RecordingHandler, convertRows, elementRow, stationRow

from excelToCsv.errors import ConversionError


def testRealStationIsMappedCompletely(logger: logging.Logger) -> None:
    """Fall 1: normale reale SUB-Station."""
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
    """Fall 2: virtuelle X-Station -> reales UW = Falsch."""
    result = convertRows(
        [stationRow(**{"ELEMENT ID": "Xb_380", "LONG-NAME": "X-Knoten b"})],
        logger,
    )
    station = result.stations.iloc[0]
    assert station["MJAP-ID"] == "Xb_380"
    assert station["reales UW"] == "Falsch"


def testMissingLatitudeIsFatal(logger: logging.Logger, logCapture: RecordingHandler) -> None:
    """Fall 3: SUB ohne Latitude."""
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
    """Fall 4: SUB ohne Longitude."""
    with pytest.raises(ConversionError):
        convertRows([stationRow(Longitude=None)], logger)

    errors = logCapture.text(logging.ERROR)
    assert "Field: Longitude" in errors
    assert "Value: <empty>" in errors


def testVirtualStationAlsoRequiresCoordinates(logger: logging.Logger) -> None:
    """Auch virtuelle Stationen brauchen Koordinaten."""
    with pytest.raises(ConversionError):
        convertRows([stationRow(**{"ELEMENT ID": "Xb_380", "Latitude": ""})], logger)


def testCoordinateWithDecimalCommaIsAccepted(logger: logging.Logger) -> None:
    """Fall 5 (Ende-zu-Ende): Dezimalkomma wird zu Punkt normalisiert."""
    result = convertRows(
        [stationRow(Latitude="52,459373", Longitude="13,361402")],
        logger,
    )
    station = result.stations.iloc[0]
    assert station["lat"] == "52.459373"
    assert station["long"] == "13.361402"


def testStationVoltageIsJsonList(logger: logging.Logger) -> None:
    """Fall 8: Stationen-Spannung als JSON-Liste."""
    single = convertRows([stationRow(**{"VOLTAGE-LEVEL": "380.0"})], logger)
    assert single.stations.iloc[0]["Spannung"] == '["380"]'

    multiple = convertRows([stationRow(**{"VOLTAGE-LEVEL": "380.0/110.0"})], logger)
    assert multiple.stations.iloc[0]["Spannung"] == '["380","110"]'

    empty = convertRows([stationRow(**{"VOLTAGE-LEVEL": ""})], logger)
    assert empty.stations.iloc[0]["Spannung"] == "[]"


def testInvalidDateIsFatal(logger: logging.Logger, logCapture: RecordingHandler) -> None:
    """Fall 10: ungültiges Datum."""
    with pytest.raises(ConversionError):
        convertRows([stationRow(STARTLIFETIME="irgendwann")], logger)

    errors = logCapture.text(logging.ERROR)
    assert "Value is not a valid date." in errors
    assert "Field: STARTLIFETIME" in errors
    assert "Value: irgendwann" in errors


def testDuplicateStationIdIsFatal(logger: logging.Logger, logCapture: RecordingHandler) -> None:
    """Fall 22: doppelte Stations-ID nennt beide Zeilen."""
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


def testStationCountsAreLogged(logger: logging.Logger, logCapture: RecordingHandler) -> None:
    convertRows([stationRow(), elementRow(**{"Station 2": "Berlin_380"})], logger)
    info = logCapture.text(logging.INFO)
    assert "Found 1 station(s)." in info
    assert "Found 1 network element(s)." in info
    assert "Validation successful." in info
