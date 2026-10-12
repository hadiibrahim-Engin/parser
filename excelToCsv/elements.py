"""``Netzelemente.csv``: one record per usable line, its contents transferred 1:1."""

from __future__ import annotations

from excelToCsv.context import ConversionContext
from excelToCsv.errors import ConversionError
from excelToCsv.mjap import validateShapeId
from excelToCsv.normalize import buildMjapId, normalizeVoltage
from excelToCsv.reader import InputRow
from excelToCsv.schema import (
    COL_ELEMENT_ID,
    COL_LONG_NAME,
    COL_STATION_1,
    COL_STATION_2,
    COL_TSO,
    COL_UCTE_CODE,
    COL_VOLTAGE_LEVEL,
)
from excelToCsv.stations import Station

#: A network element record: one ``Netzelemente.csv`` row by column name.
Element = dict[str, str]


def convertElements(rows: list[InputRow], stations: dict[str, Station],
                    context: ConversionContext) -> list[Element]:
    """Network element records in Excel order.

    Station 1 / Station 2 are looked up in the ELEMENT ID column of the SUB
    rows. A line is skipped with a warning when it has no ELEMENT ID or TSO,
    repeats an ELEMENT ID, or its stations are empty, not found, identical or
    at the same coordinates.
    """
    elements: list[Element] = []
    firstRow: dict[str, int] = {}
    for row in rows:
        reason = _skipReason(row, stations, firstRow)
        if reason is not None:
            problem, field, value = reason
            context.collector.skip(problem, field=field, value=value, **row.context())
            continue
        firstRow[row.elementId] = row.number
        start = stations[row.text(COL_STATION_1)]["MJAP-ID"]
        end = stations[row.text(COL_STATION_2)]["MJAP-ID"]
        elements.append(elementRecord(row, start, end, context))
    context.logger.info("Found %d network element(s) in %d line row(s).", len(elements), len(rows))
    return elements


def elementRecord(row: InputRow, start: str, end: str, context: ConversionContext) -> Element:
    """One record with the row's own attributes; ``start`` / ``end`` are station MJAP-IDs."""
    name = row.text(COL_LONG_NAME)
    ibn, abn = context.planningDates
    return {
        "Eigentümer": row.text(COL_TSO),
        "MJAP-ID": buildMjapId(row.text(COL_TSO), row.elementId),
        "Stromkreisname - Langname": name,
        "Region": "",
        "Element Typ": row.elementType,
        "Spannung": normalizeVoltage(row.cells.get(COL_VOLTAGE_LEVEL)),
        "relevant für": context.relevantFor(row),
        "IBN": ibn,
        "ABN": abn,
        "IBN - Mehrfach": "",
        "ABN - Mehrfach": "",
        "Station Anfang": start,
        "Station Ende": end,
        "Station T-1": "",
        "Station T-2": "",
        "Y-Knoten-1": "",
        "Y-Knoten-2": "",
        "Stromkreisname - Kurzname": name,
        "Stromkreisname - OPC-Name": "",
        "ID-GUID intern-1": "",
        "ID-GUID intern-2": "",
        "ID-OPC": "",
        "ID-UCTE": row.text(COL_UCTE_CODE),
        "ID": "",
        "Station Anfang:MJAP-ID": start,
        "Station Ende:MJAP-ID": end,
        "Station T-1:MJAP-ID": "",
        "Station T-2:MJAP-ID": "",
        "Y-Knoten-1: MJAP-ID": "",
        "Y-Knoten-2: MJAP-ID": "",
    }


def _skipReason(row: InputRow, stations: dict[str, Station],
                firstRow: dict[str, int]) -> tuple[str, str, object] | None:
    """Why a line cannot be exported, as (problem, field, value); ``None`` if it can."""
    elementId, owner = row.elementId, row.text(COL_TSO)
    if not elementId:
        return "Network element has no ELEMENT ID.", COL_ELEMENT_ID, None
    if elementId in firstRow:
        return (f"Duplicate network element ELEMENT ID (first used in row {firstRow[elementId]}).",
                COL_ELEMENT_ID, elementId)
    if not owner:
        return "Network element has no TSO, needed for its MJAP-ID <TSO>_<ELEMENT ID>.", COL_TSO, None
    for column in (COL_STATION_1, COL_STATION_2):
        station = row.text(column)
        if not station:
            return f"{column} is empty.", column, None
        if station not in stations:
            return (f"Station {station!r} not found in the ELEMENT ID column of the SUB rows.",
                    column, station)
    first, second = row.text(COL_STATION_1), row.text(COL_STATION_2)
    both = f"{COL_STATION_1} / {COL_STATION_2}"
    if first == second:
        return "Station 1 and Station 2 are the same station.", both, first
    if _position(stations[first]) == _position(stations[second]):
        return ("Station 1 and Station 2 have identical coordinates (zero-length line).",
                both, f"{first} / {second}")
    try:
        validateShapeId(buildMjapId(owner, elementId))
    except ConversionError as error:
        return str(error), COL_ELEMENT_ID, elementId
    return None


def _position(station: Station) -> tuple[float, float]:
    return float(station["lat"]), float(station["long"])
