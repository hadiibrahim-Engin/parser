"""Transformation aller Nicht-``SUB``-Zeilen nach ``Netzelemente.csv``."""

from __future__ import annotations

import numpy as np
import pandas as pd

from excelToCsv.context import ConversionContext, RowSet, emptyColumn
from excelToCsv.normalize import normalizeDate, normalizeVoltage
from excelToCsv.reader import applyNormalizer, columnValues, textColumn
from excelToCsv.relevance import buildRelevantFor
from excelToCsv.schema import (
    BOTH_STATIONS_REQUIRED,
    COL_ELEMENT_ID,
    COL_ENDLIFETIME,
    COL_LONG_NAME,
    COL_STARTLIFETIME,
    COL_STATION_1,
    COL_STATION_2,
    COL_TSO,
    COL_UCTE_CODE,
    COL_VOLTAGE_LEVEL,
    MISSING_STATION_LITERAL,
    NETWORK_ELEMENT_COLUMNS,
)


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


def resolveStationReferences(
    rows: RowSet,
    column: str,
    context: ConversionContext,
) -> np.ndarray:
    """Bestimmt die Ausgabewerte einer Stationsreferenz-Spalte.

    * Pflichttyp (LINE/TRA/TIE/DCL) ohne Referenz -> fataler Fehler.
    * Sonstiger Typ ohne Referenz -> Literal ``NaN`` plus ``WARNING``.
    * Vorhandene Referenz -> unveränderte Übernahme (Existenzprüfung erfolgt
      später in :mod:`excelToCsv.validate`).
    """
    values = textColumn(rows.frame, column)
    result = np.empty(len(values), dtype=object)
    for position, value in enumerate(values):
        if value:
            result[position] = value
            continue
        elementType = rows.elementTypes[position]
        if elementType in BOTH_STATIONS_REQUIRED:
            result[position] = ""
            context.collector.error(
                "Required station reference is missing.",
                field=column,
                value=None,
                expected=f"{elementType} requires {COL_STATION_1} and {COL_STATION_2}.",
                **rows.context(position),
            )
        else:
            result[position] = MISSING_STATION_LITERAL
            context.collector.warning(
                "Station reference is missing.",
                field=column,
                value=None,
                expected=f"{elementType} may omit a station reference.",
                action=f"Writing {MISSING_STATION_LITERAL} and continuing.",
                **rows.context(position),
            )
    return result


def convertNetworkElements(rows: RowSet, context: ConversionContext) -> pd.DataFrame:
    """Baut den Netzelemente-Datensatz aus allen gültigen Nicht-``SUB``-Zeilen."""
    rowCount = len(rows)
    context.logger.info("Found %d network element(s).", rowCount)

    for position, elementId in enumerate(rows.elementIds):
        if not elementId:
            context.collector.error(
                "Network element is missing its identifier.",
                field=COL_ELEMENT_ID,
                value=None,
                expected="Every network element row requires a non-empty ELEMENT ID.",
                **rows.context(position),
            )

    stationStart = resolveStationReferences(rows, COL_STATION_1, context)
    stationEnd = resolveStationReferences(rows, COL_STATION_2, context)

    voltages = np.fromiter(
        (normalizeVoltage(value) for value in columnValues(rows.frame, COL_VOLTAGE_LEVEL)),
        dtype=object,
        count=rowCount,
    )
    longNames = textColumn(rows.frame, COL_LONG_NAME)

    data = {
        "Eigentümer": textColumn(rows.frame, COL_TSO),
        "MJAP-ID": rows.elementIds,
        "Stromkreisname - Langname": longNames,
        "Region": emptyColumn(rowCount),
        "Element Typ": rows.elementTypes,
        "Spannung": voltages,
        "relevant für": buildRelevantFor(
            rows.frame,
            context.relevanceColumns,
            rows.rowNumbers,
            rows.elementIds,
            rows.elementTypes,
            context.collector,
        ),
        "IBN": _normalizeDateColumn(rows, COL_STARTLIFETIME, "IBN", context),
        "ABN": _normalizeDateColumn(rows, COL_ENDLIFETIME, "ABN", context),
        "IBN - Mehrfach": emptyColumn(rowCount),
        "ABN - Mehrfach": emptyColumn(rowCount),
        "Station Anfang": stationStart,
        "Station Ende": stationEnd,
        "Station T-1": emptyColumn(rowCount),
        "Station T-2": emptyColumn(rowCount),
        "Y-Knoten-1": emptyColumn(rowCount),
        "Y-Knoten-2": emptyColumn(rowCount),
        "Stromkreisname - Kurzname": longNames,
        "Stromkreisname - OPC-Name": emptyColumn(rowCount),
        "ID-GUID intern-1": emptyColumn(rowCount),
        "ID-GUID intern-2": emptyColumn(rowCount),
        "ID-OPC": emptyColumn(rowCount),
        "ID-UCTE": textColumn(rows.frame, COL_UCTE_CODE),
        "ID": emptyColumn(rowCount),
        "Station Anfang:MJAP-ID": stationStart,
        "Station Ende:MJAP-ID": stationEnd,
        "Station T-1:MJAP-ID": emptyColumn(rowCount),
        "Station T-2:MJAP-ID": emptyColumn(rowCount),
        "Y-Knoten-1: MJAP-ID": emptyColumn(rowCount),
        "Y-Knoten-2: MJAP-ID": emptyColumn(rowCount),
    }
    return pd.DataFrame(data, columns=list(NETWORK_ELEMENT_COLUMNS), dtype=object)
