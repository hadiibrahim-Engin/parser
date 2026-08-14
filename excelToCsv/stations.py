"""Transformation der ``SUB``-Zeilen nach ``Stationen.csv``."""

from __future__ import annotations

import numpy as np
import pandas as pd

from excelToCsv.context import ConversionContext, RowSet, emptyColumn
from excelToCsv.normalize import (
    isVirtualStation,
    normalizeDate,
    normalizeLatitude,
    normalizeLongitude,
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


def _normalizeCoordinateColumn(
    rows: RowSet,
    column: str,
    normalizer,
    context: ConversionContext,
) -> np.ndarray:
    """Normalisiert eine Koordinatenspalte und meldet jeden Defekt als fatal."""
    ambiguous: list[str] = []
    raw = columnValues(rows.frame, column)
    values, failures = applyNormalizer(raw, lambda value: normalizer(value, ambiguous))
    for position, error in failures:
        context.collector.error(
            error.problem,
            field=column,
            value=raw[position],
            expected=error.expected,
            **rows.context(position),
        )
    if ambiguous:
        context.logger.warning(
            "%d coordinate value(s) contained both '.' and ',' - the last separator "
            "was interpreted as the decimal separator (e.g. %r).",
            len(ambiguous),
            ambiguous[0],
        )
    return values


def _normalizeDateColumn(
    rows: RowSet,
    column: str,
    targetColumn: str,
    context: ConversionContext,
) -> np.ndarray:
    """Normalisiert eine Datumsspalte auf ``TT.MM.JJJJ``; Defekte sind fatal."""
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
    """Baut den Stationen-Datensatz aus allen ``SUB``-Zeilen.

    Validiert dabei Pflichtangaben (ELEMENT ID, Koordinaten, Datumsformate) und
    meldet jeden Verstoß als fatalen Fehler an den Collector. Es wird nichts
    geschrieben – das Schreiben passiert erst nach allen Validierungen.
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

    latitudes = _normalizeCoordinateColumn(rows, COL_LATITUDE, normalizeLatitude, context)
    longitudes = _normalizeCoordinateColumn(rows, COL_LONGITUDE, normalizeLongitude, context)
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
