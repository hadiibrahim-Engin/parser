"""Transformation of the ``SUB`` rows into ``Stationen.csv``."""

from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd

from excelToCsv.context import ConversionContext, RowSet, emptyColumn
from excelToCsv.errors import NormalizationError
from excelToCsv.normalize import (
    LATITUDE_RANGE,
    LONGITUDE_RANGE,
    decimalPlaceCount,
    isVirtualStation,
    normalizeCoordinate,
    normalizeDate,
    splitStationId,
    splitVoltages,
)
from excelToCsv.reader import applyNormalizer, columnValues, textColumn
from excelToCsv.relevance import buildRelevantFor, toJsonList
from excelToCsv.schema import (
    COL_DESCRIPTION,
    COL_ELEMENT_ID,
    COL_ENDLIFETIME,
    COL_LATITUDE,
    COL_LONG_NAME,
    COL_LONGITUDE,
    COL_STARTLIFETIME,
    COL_TSO,
    COL_UCTE_CODE,
    COL_VOLTAGE_LEVEL,
    REAL_STATION_FALSE,
    REAL_STATION_TRUE,
    STATION_COLUMNS,
)


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


def _normalizeCoordinateColumn(
    rows: RowSet,
    column: str,
    limits: tuple[float, float],
    context: ConversionContext,
) -> np.ndarray:
    """Normalize a coordinate column, repairing forgotten decimal separators.

    Runs in two passes. The first pass normalizes everything that is already
    well-formed and records how many decimal places this column uses. The second
    pass retries only the failures, using that precision to reinsert a decimal
    separator that was forgotten when the sheet was filled in. Every repair is
    reported as a ``WARNING`` with the full row context; whatever still fails is
    reported as a fatal error.
    """
    raw = columnValues(rows.frame, column)
    values = np.empty(len(raw), dtype=object)
    precisionCounts: Counter[int] = Counter()
    failures: dict[int, NormalizationError] = {}
    repairs: list[tuple[int, str]] = []

    for position, value in enumerate(raw):
        try:
            outcome = normalizeCoordinate(value, limits=limits)
        except NormalizationError as error:
            values[position] = ""
            failures[position] = error
            continue
        values[position] = outcome.text
        precisionCounts[decimalPlaceCount(outcome.text)] += 1
        if outcome.repair:
            repairs.append((position, outcome.repair))

    decimalPlaces = dominantDecimalPlaces(precisionCounts)
    if failures and decimalPlaces is not None:
        for position in list(failures):
            try:
                outcome = normalizeCoordinate(
                    raw[position], limits=limits, decimalPlaces=decimalPlaces
                )
            except NormalizationError as error:
                failures[position] = error
                continue
            values[position] = outcome.text
            del failures[position]
            if outcome.repair:
                repairs.append((position, outcome.repair))

    for position, repair in sorted(repairs):
        context.collector.warning(
            repair,
            field=column,
            value=raw[position],
            expected="A decimal number using '.' or ',' as decimal separator.",
            action=f"Writing the corrected value {values[position]} and continuing.",
            **rows.context(position),
        )

    for position, error in sorted(failures.items()):
        context.collector.error(
            error.problem,
            field=column,
            value=raw[position],
            expected=error.expected,
            **rows.context(position),
        )

    return values


def _normalizeDateColumn(
    rows: RowSet,
    column: str,
    targetColumn: str,
    context: ConversionContext,
) -> np.ndarray:
    """Normalize a date column to ``DD.MM.YYYY``; defects are fatal."""
    raw = columnValues(rows.frame, column)
    values, failures = applyNormalizer(raw, normalizeDate)
    for position, error in failures:
        context.collector.error(
            error.problem,
            field=column,
            value=raw[position],
            expected=f"{error.expected} Target column: {targetColumn} (DD.MM.YYYY).",
            **rows.context(position),
        )
    return values


def convertStations(rows: RowSet, context: ConversionContext) -> pd.DataFrame:
    """Build the station records from all ``SUB`` rows.

    Validates the mandatory fields (ELEMENT ID, coordinates, date formats) and
    reports every violation to the collector. Nothing is written here - writing
    only happens after all validations have passed.
    """
    rowCount = len(rows)
    context.logger.info("Found %d station(s).", rowCount)

    elementIds = rows.elementIds
    for position, elementId in enumerate(elementIds):
        if not elementId:
            context.collector.error(
                "Station is missing its identifier.",
                field=COL_ELEMENT_ID,
                value=None,
                expected="Every SUB row requires a non-empty ELEMENT ID (the MJAP-ID).",
                **rows.context(position),
            )

    latitudes = _normalizeCoordinateColumn(rows, COL_LATITUDE, LATITUDE_RANGE, context)
    longitudes = _normalizeCoordinateColumn(rows, COL_LONGITUDE, LONGITUDE_RANGE, context)
    startDates = _normalizeDateColumn(rows, COL_STARTLIFETIME, "IBN", context)
    endDates = _normalizeDateColumn(rows, COL_ENDLIFETIME, "ABN", context)

    voltages = np.fromiter(
        (toJsonList(splitVoltages(value)) for value in columnValues(rows.frame, COL_VOLTAGE_LEVEL)),
        dtype=object,
        count=rowCount,
    )

    realStation = np.empty(rowCount, dtype=object)
    for position, elementId in enumerate(elementIds):
        if not elementId:
            realStation[position] = REAL_STATION_TRUE
            continue
        virtual = isVirtualStation(elementId)
        realStation[position] = REAL_STATION_FALSE if virtual else REAL_STATION_TRUE
        if virtual:
            name, _ = splitStationId(elementId)
            context.logger.debug(
                "Row %d: station %s is a virtual X node (name %r) - reales UW = %s.",
                rows.rowNumbers[position],
                elementId,
                name,
                REAL_STATION_FALSE,
            )
        elif "_" not in elementId:
            context.logger.warning(
                "Row %d: station ELEMENT ID %r does not follow '<name>_<voltage>'; "
                "the full ID was used as the station name.",
                rows.rowNumbers[position],
                elementId,
            )

    longNames = textColumn(rows.frame, COL_LONG_NAME)
    ucteCodes = textColumn(rows.frame, COL_UCTE_CODE)
    relevantFor = buildRelevantFor(
        rows.frame,
        context.relevanceColumns,
        rows.rowNumbers,
        elementIds,
        rows.elementTypes,
        context.collector,
    )

    data = {
        "Eigentümer": textColumn(rows.frame, COL_TSO),
        "MJAP-ID": elementIds,
        "Stationsname - Langname": longNames,
        "lat": latitudes,
        "long": longitudes,
        "Spannung": voltages,
        "IBN": startDates,
        "ABN": endDates,
        "Stationsname - Kurzname": longNames,
        "reales UW": realStation,
        "Stationsname - OPC-Name": emptyColumn(rowCount),
        "ID-GUID intern-1": emptyColumn(rowCount),
        "ID-GUID intern-2": emptyColumn(rowCount),
        "ID-OPC": emptyColumn(rowCount),
        "ID-UCTE": ucteCodes,
        "relevant für": relevantFor,
        "ID": ucteCodes,
        "Kommentar": textColumn(rows.frame, COL_DESCRIPTION),
        "IBN - Mehrfach": emptyColumn(rowCount),
        "ABN - Mehrfach": emptyColumn(rowCount),
    }
    return pd.DataFrame(data, columns=list(STATION_COLUMNS), dtype=object)
