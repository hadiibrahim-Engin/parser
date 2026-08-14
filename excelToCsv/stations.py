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
    STATION_ID_SEPARATOR,
    buildMjapId,
    decimalPlaceCount,
    followsStationIdConvention,
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


def buildFallbackStationName(longName: str, elementId: str) -> str:
    """Build a station name for an ELEMENT ID that breaks the naming convention.

    The regular station name comes straight from ``LONG-NAME``. When the
    ``ELEMENT ID`` does not follow ``<name>_<voltage>`` it carries no voltage
    level, so the name is assembled as ``<LONG-NAME>_<ELEMENT ID>`` instead.
    Without a long name the plain ELEMENT ID remains, since a leading separator
    would only add noise.
    """
    if not longName:
        return elementId
    return f"{longName}{STATION_ID_SEPARATOR}{elementId}"


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
    separator that was forgotten when the sheet was filled in.

    If not a single value of the column carries a separator there is no precision
    to derive, and the position is guessed instead (as far right as the range
    allows). Every repair - derived or guessed - is reported as a ``WARNING`` with
    the full row context; whatever still fails is reported as a fatal error.
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
    if failures:
        if decimalPlaces is None:
            context.logger.warning(
                "Column %r contains no value with a decimal separator, so its precision "
                "is unknown. Separator positions will be guessed and must be verified.",
                column,
            )
        for position in list(failures):
            try:
                outcome = normalizeCoordinate(
                    raw[position],
                    limits=limits,
                    decimalPlaces=decimalPlaces,
                    allowWidestFit=decimalPlaces is None,
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
    owners = textColumn(rows.frame, COL_TSO)
    ucteCodes = textColumn(rows.frame, COL_UCTE_CODE)
    mjapIds = np.fromiter(
        (
            buildMjapId(owner, elementId)
            for owner, elementId in zip(owners, elementIds, strict=True)
        ),
        dtype=object,
        count=rowCount,
    )
    for position, elementId in enumerate(elementIds):
        if not elementId:
            context.collector.error(
                "Station is missing its identifier.",
                field=COL_ELEMENT_ID,
                value=None,
                expected="Every SUB row requires a non-empty ELEMENT ID.",
                **rows.context(position),
            )
        if not owners[position]:
            context.collector.error(
                "Station is missing the owner required for its MJAP-ID.",
                field=COL_TSO,
                value=None,
                expected="Every SUB row requires a non-empty TSO value for <owner>_<ELEMENT ID>.",
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

    longNames = textColumn(rows.frame, COL_LONG_NAME)
    voltageLevels = columnValues(rows.frame, COL_VOLTAGE_LEVEL)

    realStation = np.empty(rowCount, dtype=object)
    stationNames = np.empty(rowCount, dtype=object)
    for position, elementId in enumerate(elementIds):
        stationNames[position] = longNames[position]
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

        if not followsStationIdConvention(elementId, voltageLevels[position]):
            stationNames[position] = buildFallbackStationName(
                longNames[position], elementId
            )
            context.collector.warning(
                "Station ELEMENT ID does not follow the '<name>_<voltage>' convention.",
                field=COL_ELEMENT_ID,
                value=elementId,
                expected=(
                    "An ELEMENT ID of the form <name>_<voltage> whose suffix agrees "
                    "with VOLTAGE-LEVEL, e.g. Berlin_380."
                ),
                action=f"Using '{stationNames[position]}' as the station name.",
                **rows.context(position),
            )

    relevantFor = buildRelevantFor(
        rows.frame,
        context.relevanceColumns,
        rows.rowNumbers,
        elementIds,
        rows.elementTypes,
        context.collector,
    )

    data = {
        "Eigentümer": owners,
        "MJAP-ID": mjapIds,
        "Stationsname - Langname": stationNames,
        "lat": latitudes,
        "long": longitudes,
        "Spannung": voltages,
        "IBN": startDates,
        "ABN": endDates,
        "Stationsname - Kurzname": stationNames,
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
