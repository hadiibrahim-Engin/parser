"""``Netzelemente.csv``: ordinary lines 1:1, tripods as four records.

A tripod with outer stations A, B, C (in leg order) and virtual node XK becomes:

    name row  -> complete Y:  A - B, Station T-1 = C, Y-Knoten-1 = XK
    leg 1     -> pair A - B
    leg 2     -> pair B - C
    leg 3     -> pair A - C
"""

from __future__ import annotations

from excelToCsv.context import ConversionContext
from excelToCsv.multipod import Tripod
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
    REAL_STATION_TRUE,
)
from excelToCsv.stations import Station

#: A network element record: one ``Netzelemente.csv`` row by column name.
Element = dict[str, str]


def convertElements(rows: list[InputRow], tripods: list[Tripod], tripodRows: set[int],
                    stations: dict[str, Station], context: ConversionContext) -> list[Element]:
    """Network element records in Excel order; a tripod appears at its name row."""
    _reportDuplicateIds(rows, context)
    tripodByNameRow = {tripod.nameRow.number: tripod for tripod in tripods}
    elements: list[Element] = []
    for row in rows:
        tripod = tripodByNameRow.get(row.number)
        if tripod is not None:
            elements += _tripodRecords(tripod, stations, context)
        elif row.number not in tripodRows:
            start = _stationId(row, COL_STATION_1, row.text(COL_STATION_1), stations, context)
            end = _stationId(row, COL_STATION_2, row.text(COL_STATION_2), stations, context)
            elements.append(elementRecord(row, start, end, context))
    context.logger.info("Found %d network element record(s), %d of them from %d tripod(s).",
                        len(elements), 4 * len(tripods), len(tripods))
    return elements


def elementRecord(row: InputRow, start: str, end: str, context: ConversionContext, *,
                  third: str = "", nodeName: str = "", nodeMjapId: str = "") -> Element:
    """One record with the row's own attributes; station arguments are MJAP-IDs."""
    owner, elementId = row.text(COL_TSO), row.elementId
    if not owner:
        context.collector.error("Network element is missing the owner required for its MJAP-ID.",
                                field=COL_TSO, expected="A TSO value for <owner>_<ELEMENT ID>.",
                                **row.context())
    if not elementId:
        context.collector.error("Network element is missing its ELEMENT ID.", field=COL_ELEMENT_ID,
                                expected="Every network element row requires a non-empty ELEMENT ID.",
                                **row.context())
    name = row.text(COL_LONG_NAME)
    ibn, abn = context.planningDates
    return {
        "Eigentümer": owner,
        "MJAP-ID": buildMjapId(owner, elementId),
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
        "Station T-1": third,
        "Station T-2": "",
        "Y-Knoten-1": nodeName,
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
        "Station T-1:MJAP-ID": third,
        "Station T-2:MJAP-ID": "",
        "Y-Knoten-1: MJAP-ID": nodeMjapId,
        "Y-Knoten-2: MJAP-ID": "",
    }


def _reportDuplicateIds(rows: list[InputRow], context: ConversionContext) -> None:
    firstRow: dict[str, int] = {}
    for row in rows:
        elementId = row.elementId
        if elementId in firstRow:
            context.collector.error(
                f"Duplicate network element ELEMENT ID (first used in row {firstRow[elementId]}).",
                field=COL_ELEMENT_ID, value=elementId,
                expected="Every network element requires a unique ELEMENT ID.", **row.context())
        elif elementId:
            firstRow[elementId] = row.number


def _tripodRecords(tripod: Tripod, stations: dict[str, Station],
                   context: ConversionContext) -> list[Element]:
    first, second, third = tripod.legs
    a, b, c = (_stationId(leg, f"{COL_STATION_1} / {COL_STATION_2}", station, stations, context,
                          realOnly=True)
               for leg, station in zip(tripod.legs, tripod.outerStations))
    return [
        elementRecord(tripod.nameRow, a, b, context, third=c, nodeName=tripod.node,
                      nodeMjapId=stations[tripod.node]["MJAP-ID"]),
        elementRecord(first, a, b, context),
        elementRecord(second, b, c, context),
        elementRecord(third, a, c, context),
    ]


def _stationId(row: InputRow, field: str, station: str, stations: dict[str, Station],
               context: ConversionContext, *, realOnly: bool = False) -> str:
    """MJAP-ID of the station named in Station 1 / Station 2.

    ``stations`` is keyed by the ELEMENT ID of the SUB rows, so a reference is
    matched against ELEMENT ID only - never against LONG-NAME.
    """
    record = stations.get(station)
    if record is not None and (not realOnly or record["reales UW"] == REAL_STATION_TRUE):
        return record["MJAP-ID"]
    problem = ("Station reference is empty." if not station else
               f"Station {station!r} does not exist as SUB row." if record is None else
               f"Outer tripod station {station!r} is itself a virtual node.")
    context.collector.error(problem, field=field, value=station,
                            expected="An ELEMENT ID of a SUB row (or of a tripod node).",
                            **row.context())
    return ""
