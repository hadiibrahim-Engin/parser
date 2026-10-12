"""``Stationen.csv``: one real station per usable SUB row."""

from __future__ import annotations

import json
from collections import Counter

from excelToCsv.context import ConversionContext
from excelToCsv.errors import ConversionError, NormalizationError
from excelToCsv.mjap import validateShapeId
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
    REAL_STATION_TRUE,
)

#: A station record: one ``Stationen.csv`` row by column name.
Station = dict[str, str]


def convertStations(rows: list[InputRow], context: ConversionContext) -> dict[str, Station]:
    """Stations keyed by ELEMENT ID; Station 1 / Station 2 are resolved against these keys only.

    A SUB row that cannot become a usable station is skipped with a warning:
    no ELEMENT ID, a repeated ELEMENT ID, no TSO, an unreadable coordinate or
    an ID that MJAP cannot store.
    """
    latitudes = normalizeCoordinates(rows, COL_LATITUDE, LATITUDE_RANGE, context)
    longitudes = normalizeCoordinates(rows, COL_LONGITUDE, LONGITUDE_RANGE, context)
    stations: dict[str, Station] = {}
    firstRow: dict[str, int] = {}
    for row, latitude, longitude in zip(rows, latitudes, longitudes):
        if not latitude or not longitude:
            continue  # already reported by normalizeCoordinates
        reason = _skipReason(row, firstRow)
        if reason is not None:
            problem, field, value = reason
            context.collector.skip(problem, field=field, value=value, **row.context())
            continue
        elementId = row.elementId
        firstRow[elementId] = row.number
        stations[elementId] = {
            "Eigentümer": row.text(COL_TSO),
            "MJAP-ID": buildMjapId(row.text(COL_TSO), elementId),
            "Stationsname - Langname": row.text(COL_LONG_NAME),
            "lat": latitude,
            "long": longitude,
            "Spannung": json.dumps(splitVoltages(row.cells.get(COL_VOLTAGE_LEVEL)),
                                   ensure_ascii=False, separators=(",", ":")),
            "IBN": context.planningDates[0],
            "ABN": context.planningDates[1],
            "Stationsname - Kurzname": row.text(COL_LONG_NAME),
            "reales UW": REAL_STATION_TRUE,
            "Stationsname - OPC-Name": "",
            "ID-GUID intern-1": "",
            "ID-GUID intern-2": "",
            "ID-OPC": "",
            "ID-UCTE": row.text(COL_UCTE_CODE),
            "relevant für": context.relevantFor(row),
            "ID": row.text(COL_UCTE_CODE),
            "Kommentar": row.text(COL_DESCRIPTION),
            "IBN - Mehrfach": "",
            "ABN - Mehrfach": "",
        }
    context.logger.info("Found %d station(s) in %d SUB row(s).", len(stations), len(rows))
    return stations


def _skipReason(row: InputRow, firstRow: dict[str, int]) -> tuple[str, str, object] | None:
    """Why a SUB row cannot become a station, as (problem, field, value); ``None`` if it can."""
    elementId, owner = row.elementId, row.text(COL_TSO)
    if not elementId:
        return "Station has no ELEMENT ID.", COL_ELEMENT_ID, None
    if elementId in firstRow:
        return (f"Duplicate station ELEMENT ID (first used in row {firstRow[elementId]}).",
                COL_ELEMENT_ID, elementId)
    if not owner:
        return "Station has no TSO, needed for its MJAP-ID <TSO>_<ELEMENT ID>.", COL_TSO, None
    try:
        validateShapeId(buildMjapId(owner, elementId))
    except ConversionError as error:
        return str(error), COL_ELEMENT_ID, elementId
    return None


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
    right as the range allows). Every repair is a warning; a row whose value
    still fails is skipped.
    """
    collector = context.collector
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
        collector.skip(error.problem, field=column, value=raw[position],
                       expected=error.expected, **rows[position].context())
    return values
