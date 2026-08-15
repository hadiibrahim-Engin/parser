"""Tests for the ``Multipod`` reference of three-legged lines."""

from __future__ import annotations

import logging

import pytest
from conftest import RecordingHandler, convertRows, elementRow, stationRow

from excelToCsv.errors import ConversionError

MULTIPOD = "Multipod"
MAP_MULTIPOD = "Map Multipod"

VIRTUAL_STATION = "XStationK_380"


def virtualStation(**overrides: object) -> dict[str, object]:
    """The virtual SUB row at which the legs of a multipod line meet."""
    return stationRow(
        **{
            "ELEMENT ID": VIRTUAL_STATION,
            "TSO": "50Hertz",
            "LONG-NAME": "X-Knoten StationK",
            "Latitude": "51.123456",
            "Longitude": "11.654321",
            "UCTE CODE": "XSTATK1",
            **overrides,
        }
    )


def legStations() -> list[dict[str, object]]:
    """Three real stations, one per leg."""
    return [
        stationRow(
            **{
                "ELEMENT ID": f"Station{suffix}_380",
                "LONG-NAME": f"Umspannwerk {suffix}",
                "Latitude": "52.459373",
                "Longitude": "13.361402",
                "UCTE CODE": f"DSTAT{suffix}",
            }
        )
        for suffix in ("A", "B", "C")
    ]


def leg(number: int, station: str, **overrides: object) -> dict[str, object]:
    """One leg of the multipod line, running from the virtual node to a station."""
    return elementRow(
        **{
            "ELEMENT ID": f"LINE_00{number}",
            "LONG-NAME": f"Bein {number}",
            "ELEMENT-TYPE": "LINE",
            "Station 1": VIRTUAL_STATION,
            "Station 2": station,
            "UCTE CODE": f"DL00{number}",
            MULTIPOD: VIRTUAL_STATION,
            **overrides,
        }
    )


# --------------------------------------------------------------------------- #
# Case 1: without Multipod the Y node columns stay empty
# --------------------------------------------------------------------------- #


def testLineWithoutMultipodLeavesYNodesEmpty(logger: logging.Logger) -> None:
    rows = [virtualStation(), *legStations(), leg(1, "StationA_380", **{MULTIPOD: ""})]
    element = convertRows(rows, logger).networkElements.iloc[0]

    assert element["Y-Knoten-1"] == ""
    assert element["Y-Knoten-1: MJAP-ID"] == ""
    assert element["Y-Knoten-2"] == ""
    assert element["Y-Knoten-2: MJAP-ID"] == ""


def testMultipodColumnMayBeAbsentEntirely(logger: logging.Logger) -> None:
    """A workbook without the optional column still converts."""
    rows = [
        virtualStation(),
        *legStations(),
        elementRow(
            **{"Station 1": VIRTUAL_STATION, "Station 2": "StationA_380"}
        ),
    ]
    element = convertRows(rows, logger).networkElements.iloc[0]
    assert element["Y-Knoten-1"] == ""
    assert element["Y-Knoten-1: MJAP-ID"] == ""


# --------------------------------------------------------------------------- #
# Cases 2-5: a valid Multipod populates the Y node columns
# --------------------------------------------------------------------------- #


def testValidMultipodPopulatesYNode(logger: logging.Logger) -> None:
    rows = [virtualStation(), *legStations(), leg(1, "StationA_380")]
    result = convertRows(rows, logger)
    element = result.networkElements.iloc[0]

    assert element["Y-Knoten-1"] == VIRTUAL_STATION
    assert element["Y-Knoten-1: MJAP-ID"] == f"50Hertz_{VIRTUAL_STATION}"
    assert result.warningCount == 0, "a well-formed virtual station warns about nothing"


def testStationColumnsAreUnaffectedByMultipod(logger: logging.Logger) -> None:
    """Station Anfang/Ende keep their own mapping."""
    rows = [virtualStation(), *legStations(), leg(1, "StationA_380")]
    element = convertRows(rows, logger).networkElements.iloc[0]

    assert element["Station Anfang"] == VIRTUAL_STATION
    assert element["Station Ende"] == "StationA_380"
    assert element["Station Anfang:MJAP-ID"] == f"50Hertz_{VIRTUAL_STATION}"
    assert element["Station Ende:MJAP-ID"] == "Amprion_StationA_380"


def testMultipodValueIsTrimmed(logger: logging.Logger) -> None:
    rows = [
        virtualStation(),
        *legStations(),
        leg(1, "StationA_380", **{MULTIPOD: f"  {VIRTUAL_STATION} "}),
    ]
    element = convertRows(rows, logger).networkElements.iloc[0]
    assert element["Y-Knoten-1"] == VIRTUAL_STATION


def testYKnoten2StaysEmpty(logger: logging.Logger) -> None:
    """No business rule defines the second Y node yet."""
    rows = [virtualStation(), *legStations(), leg(1, "StationA_380")]
    element = convertRows(rows, logger).networkElements.iloc[0]

    assert element["Y-Knoten-2"] == ""
    assert element["Y-Knoten-2: MJAP-ID"] == ""


# --------------------------------------------------------------------------- #
# Case 6: the three legs stay three separate records
# --------------------------------------------------------------------------- #


def testThreeLegsStayThreeSeparateRecords(logger: logging.Logger) -> None:
    rows = [
        virtualStation(),
        *legStations(),
        leg(1, "StationA_380"),
        leg(2, "StationB_380"),
        leg(3, "StationC_380"),
    ]
    elements = convertRows(rows, logger).networkElements

    assert len(elements) == 3, "the legs must not be aggregated into one line"
    assert list(elements["MJAP-ID"]) == [
        "Amprion_LINE_001",
        "Amprion_LINE_002",
        "Amprion_LINE_003",
    ]
    assert list(elements["Station Ende"]) == [
        "StationA_380",
        "StationB_380",
        "StationC_380",
    ]
    # All three share the same virtual node.
    assert set(elements["Y-Knoten-1"]) == {VIRTUAL_STATION}
    assert set(elements["Y-Knoten-1: MJAP-ID"]) == {f"50Hertz_{VIRTUAL_STATION}"}


# --------------------------------------------------------------------------- #
# Case 7: unknown reference is fatal
# --------------------------------------------------------------------------- #


def testUnknownMultipodReferenceIsFatal(
    logger: logging.Logger, logCapture: RecordingHandler
) -> None:
    rows = [
        virtualStation(),
        *legStations(),
        leg(1, "StationA_380", **{MULTIPOD: "XDoesNotExist_380"}),
    ]
    with pytest.raises(ConversionError):
        convertRows(rows, logger)

    errors = logCapture.text(logging.ERROR)
    assert "Multipod references an unknown virtual station." in errors
    assert "Field: Multipod" in errors
    assert "Value: XDoesNotExist_380" in errors
    assert "ELEMENT ID: LINE_001" in errors
    assert "ELEMENT-TYPE: LINE" in errors
    assert "Expected: Every Multipod value must reference an existing SUB ELEMENT ID." in errors


def testMultipodPointingAtANetworkElementIsFatal(logger: logging.Logger) -> None:
    """Only SUB rows are valid targets, not another network element."""
    rows = [
        virtualStation(),
        *legStations(),
        leg(1, "StationA_380"),
        leg(2, "StationB_380", **{MULTIPOD: "LINE_001"}),
    ]
    with pytest.raises(ConversionError):
        convertRows(rows, logger)


# --------------------------------------------------------------------------- #
# Case 8: existing station without the X convention only warns
# --------------------------------------------------------------------------- #


def testMultipodWithoutXConventionOnlyWarns(
    logger: logging.Logger, logCapture: RecordingHandler
) -> None:
    rows = [
        virtualStation(**{"ELEMENT ID": "StationK_380"}),
        *legStations(),
        leg(1, "StationA_380", **{"Station 1": "StationK_380", MULTIPOD: "StationK_380"}),
    ]
    result = convertRows(rows, logger)

    warnings = logCapture.text(logging.WARNING)
    assert "does not follow the expected virtual-station X naming convention" in warnings
    assert "Value: StationK_380" in warnings
    assert "Expected: Pattern X<StationName>_<VoltageLevel>" in warnings

    element = result.networkElements.iloc[0]
    assert element["Y-Knoten-1"] == "StationK_380", "the reference is never renamed"
    assert element["Y-Knoten-1: MJAP-ID"] == "50Hertz_StationK_380"


def testConverterNeverInventsAVirtualStation(
    logger: logging.Logger, logCapture: RecordingHandler
) -> None:
    """An old-style ``StationK`` is not rebuilt into ``XStationK_380``."""
    rows = [
        virtualStation(**{"ELEMENT ID": "StationK"}),
        *legStations(),
        leg(1, "StationA_380", **{"Station 1": "StationK", MULTIPOD: "StationK"}),
    ]
    result = convertRows(rows, logger)

    assert result.networkElements.iloc[0]["Y-Knoten-1"] == "StationK"
    assert "does not follow the expected virtual-station X naming convention" in logCapture.text(
        logging.WARNING
    )


# --------------------------------------------------------------------------- #
# Case 9: Map Multipod remains irrelevant
# --------------------------------------------------------------------------- #


def testMapMultipodDoesNotInfluenceAnything(logger: logging.Logger) -> None:
    withoutColumn = convertRows(
        [virtualStation(), *legStations(), leg(1, "StationA_380")], logger
    )
    withColumn = convertRows(
        [
            virtualStation(**{MAP_MULTIPOD: "whatever"}),
            *legStations(),
            leg(1, "StationA_380", **{MAP_MULTIPOD: "XSomethingElse_220"}),
        ],
        logger,
    )

    assert withColumn.networkElements.equals(withoutColumn.networkElements)
    assert withColumn.stations.equals(withoutColumn.stations)


def testMapMultipodIsNotMistakenForMultipod(
    logger: logging.Logger, logCapture: RecordingHandler
) -> None:
    """A dangling ``Map Multipod`` must not trigger the reference check."""
    rows = [
        virtualStation(),
        *legStations(),
        leg(1, "StationA_380", **{MULTIPOD: "", MAP_MULTIPOD: "XDoesNotExist_380"}),
    ]
    result = convertRows(rows, logger)

    assert result.networkElements.iloc[0]["Y-Knoten-1"] == ""
    assert "Multipod references an unknown" not in logCapture.text(logging.ERROR)
