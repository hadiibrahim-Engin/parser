"""``Stationen.csv``: real stations from SUB rows, virtual stations from tripods."""

from __future__ import annotations

import json
from collections import Counter

from excelToCsv.context import ConversionContext
from excelToCsv.errors import NormalizationError
from excelToCsv.issues import IssueCollector
from excelToCsv.multipod import Tripod
from excelToCsv.normalize import (
    LATITUDE_RANGE,
    LONGITUDE_RANGE,
    buildMjapId,
    decimalPlaceCount,
    normalizeCoordinate,
    splitVoltages,
)
from excelToCsv.reader import InputRow
from excelToCsv.schema import (
    COL_DESCRIPTION,
    COL_ELEMENT_ID,
    COL_LATITUDE,
    COL_LONG_NAME,
    COL_LONGITUDE,
    COL_TSO,
    COL_UCTE_CODE,
    COL_VOLTAGE_LEVEL,
    REAL_STATION_FALSE,
    REAL_STATION_TRUE,
)

#: A station record: one ``Stationen.csv`` row by column name.
Station = dict[str, str]


def convertStations(rows: list[InputRow], tripods: list[Tripod],
                    context: ConversionContext) -> dict[str, Station]:
    """All stations keyed by ELEMENT ID: every SUB row, then every tripod node.

    Station 1 / Station 2 references are resolved against these keys only.

    SUB rows are the real stations (``reales UW = Wahr``). The node of a tripod
    is virtual (``reales UW = Falsch``); without a SUB row of its own it is
    placed at the centre of the tripod's three outer stations.
    """
    stations = _realStations(rows, context)
    for tripod in tripods:
        if tripod.node in stations:
            stations[tripod.node]["reales UW"] = REAL_STATION_FALSE
            continue
        latitude, longitude = _centre([stations.get(station) for station in tripod.outerStations])
        nameRow = tripod.nameRow
        stations[tripod.node] = stationRecord(
            nameRow.text(COL_TSO), tripod.node, tripod.node, latitude, longitude,
            nameRow.cells.get(COL_VOLTAGE_LEVEL), real=False, ucte="", relevantFor="",
            comment="", planningDates=context.planningDates,
        )
    context.logger.info("Found %d real and %d virtual station(s).", len(rows),
                        sum(record["reales UW"] == REAL_STATION_FALSE for record in stations.values()))
    return stations


def stationRecord(owner: str, elementId: str, name: str, latitude: str, longitude: str,
                  voltage: object, *, real: bool, ucte: str, relevantFor: str, comment: str,
                  planningDates: tuple[str, str]) -> Station:
    start, end = planningDates
    return {
        "Eigentümer": owner,
        "MJAP-ID": buildMjapId(owner, elementId),
        "Stationsname - Langname": name,
        "lat": latitude,
        "long": longitude,
        "Spannung": json.dumps(splitVoltages(voltage), ensure_ascii=False, separators=(",", ":")),
        "IBN": start,
        "ABN": end,
        "Stationsname - Kurzname": name,
        "reales UW": REAL_STATION_TRUE if real else REAL_STATION_FALSE,
        "Stationsname - OPC-Name": "",
        "ID-GUID intern-1": "",
        "ID-GUID intern-2": "",
        "ID-OPC": "",
        "ID-UCTE": ucte,
        "relevant für": relevantFor,
        "ID": ucte,
        "Kommentar": comment,
        "IBN - Mehrfach": "",
        "ABN - Mehrfach": "",
    }


def _realStations(rows: list[InputRow], context: ConversionContext) -> dict[str, Station]:
    collector = context.collector
    latitudes = normalizeCoordinates(rows, COL_LATITUDE, LATITUDE_RANGE, context)
    longitudes = normalizeCoordinates(rows, COL_LONGITUDE, LONGITUDE_RANGE, context)
    stations: dict[str, Station] = {}
    firstRow: dict[str, int] = {}
    for row, latitude, longitude in zip(rows, latitudes, longitudes):
        elementId, owner = row.elementId, row.text(COL_TSO)
        if not elementId:
            collector.error("Station is missing its ELEMENT ID.", field=COL_ELEMENT_ID,
                            expected="Every SUB row requires a non-empty ELEMENT ID.",
                            **row.context())
            continue
        if elementId in stations:
            collector.error(f"Duplicate station ELEMENT ID (first used in row {firstRow[elementId]}).",
                            field=COL_ELEMENT_ID, value=elementId,
                            expected="Every SUB station requires a unique ELEMENT ID.",
                            **row.context())
            continue
        if not owner:
            collector.error("Station is missing the owner required for its MJAP-ID.",
                            field=COL_TSO, expected="A TSO value for <owner>_<ELEMENT ID>.",
                            **row.context())
        firstRow[elementId] = row.number
        stations[elementId] = stationRecord(
            owner, elementId, row.text(COL_LONG_NAME), latitude, longitude,
            row.cells.get(COL_VOLTAGE_LEVEL), real=True, ucte=row.text(COL_UCTE_CODE),
            relevantFor=context.relevantFor(row), comment=row.text(COL_DESCRIPTION),
            planningDates=context.planningDates,
        )
    return stations


def _centre(corners: list[Station | None]) -> tuple[str, str]:
    """Mean lat/long of the outer stations; empty if any of them is unusable."""
    try:
        points = [(float(corner["lat"]), float(corner["long"])) for corner in corners if corner]
    except ValueError:
        return "", ""
    if len(points) != len(corners):
        return "", ""
    return tuple(_formatCoordinate(sum(axis) / len(points)) for axis in zip(*points))


def _formatCoordinate(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


# --------------------------------------------------------------------------- #
# Coordinates with repair of a forgotten decimal separator
# --------------------------------------------------------------------------- #


def dominantDecimalPlaces(counts: Counter[int]) -> int | None:
    """Pick the decimal precision that best represents a coordinate column.

    Only values that actually carry decimals are evidence; whole numbers say
    nothing about the intended precision. On a tie the higher precision wins so
    that a repaired value never loses digits.

    Returns:
        The dominant number of decimal places, or ``None`` without evidence.
    """
    evidence = {places: count for places, count in counts.items() if places > 0}
    if not evidence:
        return None
    return max(evidence.items(), key=lambda item: (item[1], item[0]))[0]


def normalizeCoordinates(rows: list[InputRow], column: str, limits: tuple[float, float],
                         context: ConversionContext) -> list[str]:
    """Normalize a coordinate column, repairing forgotten decimal separators.

    The first pass normalizes every well-formed value and records how many
    decimal places the column uses. The second pass retries the failures with
    that precision to reinsert a separator that was forgotten in the sheet.
    Without any value carrying a separator, the position is guessed (as far
    right as the range allows). Every repair is a warning; whatever still fails
    is an error.
    """
    collector: IssueCollector = context.collector
    raw = [row.cells.get(column) for row in rows]
    values = [""] * len(raw)
    precisionCounts: Counter[int] = Counter()
    failures: dict[int, NormalizationError] = {}
    repairs: list[tuple[int, str]] = []

    for position, value in enumerate(raw):
        try:
            outcome = normalizeCoordinate(value, limits=limits)
        except NormalizationError as error:
            failures[position] = error
            continue
        values[position] = outcome.text
        precisionCounts[decimalPlaceCount(outcome.text)] += 1
        if outcome.repair:
            repairs.append((position, outcome.repair))

    decimalPlaces = dominantDecimalPlaces(precisionCounts)
    if failures and decimalPlaces is None:
        context.logger.warning(
            "Column %r contains no value with a decimal separator, so its precision "
            "is unknown. Separator positions will be guessed and must be verified.", column)
    for position in list(failures):
        try:
            outcome = normalizeCoordinate(raw[position], limits=limits, decimalPlaces=decimalPlaces,
                                          allowWidestFit=decimalPlaces is None)
        except NormalizationError as error:
            failures[position] = error
            continue
        values[position] = outcome.text
        del failures[position]
        if outcome.repair:
            repairs.append((position, outcome.repair))

    for position, repair in sorted(repairs):
        collector.warning(repair, field=column, value=raw[position],
                          expected="A decimal number using '.' or ',' as decimal separator.",
                          action=f"Writing the corrected value {values[position]} and continuing.",
                          **rows[position].context())
    for position, error in sorted(failures.items()):
        collector.error(error.problem, field=column, value=raw[position],
                        expected=error.expected, **rows[position].context())
    return values
