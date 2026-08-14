"""Alle Validierungen, die über eine einzelne Zelle hinausgehen.

Bewusst getrennt von der Transformation: Erst werden alle Datensätze gebaut,
dann vollständig geprüft, und erst danach darf geschrieben werden.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from excelToCsv.context import ConversionContext, RowSet
from excelToCsv.errors import ConversionError
from excelToCsv.issues import IssueCollector
from excelToCsv.normalize import isBlank
from excelToCsv.reader import textColumn
from excelToCsv.schema import (
    COL_ELEMENT_TYPE,
    COL_STATION_1,
    COL_STATION_2,
    STATION_TYPE,
    VALID_ELEMENT_TYPES,
)


def validateElementTypes(
    elementTypes: np.ndarray,
    rows: RowSet,
    collector: IssueCollector,
) -> None:
    """Meldet jeden unbekannten ``ELEMENT-TYPE`` als fatalen Fehler."""
    expected = ", ".join(sorted(VALID_ELEMENT_TYPES))
    for position, elementType in enumerate(elementTypes):
        if elementType not in VALID_ELEMENT_TYPES:
            collector.error(
                "Unknown ELEMENT-TYPE.",
                field=COL_ELEMENT_TYPE,
                value=elementType or None,
                expected=f"One of: {expected}.",
                **rows.context(position),
            )


def buildStationIndex(rows: RowSet, collector: IssueCollector) -> dict[str, int]:
    """Baut den Index ``ELEMENT ID -> Excel-Zeile`` über alle ``SUB``-Zeilen.

    Doppelte Stations-IDs werden nicht stillschweigend überschrieben, sondern
    unter Angabe aller betroffenen Zeilen als fataler Fehler gemeldet.
    """
    positionsById: dict[str, list[int]] = {}
    for position, elementId in enumerate(rows.elementIds):
        if elementId:
            positionsById.setdefault(elementId, []).append(position)

    index: dict[str, int] = {}
    for elementId, positions in positionsById.items():
        index[elementId] = int(rows.rowNumbers[positions[0]])
        if len(positions) == 1:
            continue
        affected = ", ".join(str(int(rows.rowNumbers[position])) for position in positions)
        for position in positions:
            collector.error(
                f"Duplicate station ELEMENT ID (also used in row(s): {affected}).",
                field="ELEMENT ID",
                value=elementId,
                expected="Every SUB station requires a unique ELEMENT ID.",
                **rows.context(position),
            )
    return index


def validateDuplicateNetworkElements(
    rows: RowSet,
    frame: pd.DataFrame,
    collector: IssueCollector,
) -> None:
    """Prüft doppelte Netzelement-IDs.

    Vollständig identische Datensätze sind tolerierbar (``WARNING``);
    widersprüchliche Datensätze mit gleicher ID sind fatal.
    """
    positionsById: dict[str, list[int]] = {}
    for position, elementId in enumerate(rows.elementIds):
        if elementId:
            positionsById.setdefault(elementId, []).append(position)

    values = frame.to_numpy(dtype=object)
    for elementId, positions in positionsById.items():
        if len(positions) == 1:
            continue
        affected = ", ".join(str(int(rows.rowNumbers[position])) for position in positions)
        distinct = {tuple(values[position]) for position in positions}
        if len(distinct) == 1:
            collector.warning(
                f"Duplicate network element ELEMENT ID with identical content "
                f"(row(s): {affected}).",
                field="ELEMENT ID",
                value=elementId,
                action="Keeping all rows and continuing.",
                **rows.context(positions[0]),
            )
            continue
        for position in positions:
            collector.error(
                f"Conflicting duplicate network element ELEMENT ID "
                f"(also used in row(s): {affected}).",
                field="ELEMENT ID",
                value=elementId,
                expected="Duplicate ELEMENT IDs must reference identical records.",
                **rows.context(position),
            )


def validateStationReferences(
    rows: RowSet,
    stationIndex: dict[str, int],
    collector: IssueCollector,
) -> None:
    """Prüft, dass jede gesetzte Stationsreferenz auf eine ``SUB``-Zeile zeigt."""
    for column in (COL_STATION_1, COL_STATION_2):
        for position, reference in enumerate(textColumn(rows.frame, column)):
            if not reference or reference in stationIndex:
                continue
            collector.error(
                "Station reference does not match any station.",
                field=column,
                value=reference,
                expected=(
                    f"A row with {COL_ELEMENT_TYPE} = {STATION_TYPE} and "
                    f"ELEMENT ID = {reference} must exist."
                ),
                **rows.context(position),
            )


def validateOutputSchema(
    frame: pd.DataFrame,
    columns: tuple[str, ...],
    name: str,
    context: ConversionContext,
) -> None:
    """Prüft Zielspalten, Reihenfolge und die Abwesenheit von NA-Werten.

    Raises:
        ConversionError: Bei Abweichungen vom vereinbarten Output-Vertrag.
    """
    actual = tuple(frame.columns)
    if actual != columns:
        context.logger.error(
            "Output schema mismatch for %s.\nExpected: %s\nActual:   %s",
            name,
            list(columns),
            list(actual),
        )
        raise ConversionError(f"Output schema mismatch for {name}")

    for column in columns:
        values = frame[column].to_numpy(dtype=object)
        for position, value in enumerate(values):
            if value is None or (isinstance(value, float) and isBlank(value)):
                context.logger.error(
                    "Unexpected empty (NA) value in %s, column %r, record %d.",
                    name,
                    column,
                    position + 1,
                )
                raise ConversionError(f"Unexpected NA value in {name}, column {column}")
            if not isinstance(value, str):
                context.logger.error(
                    "Non-string value %r in %s, column %r, record %d.",
                    value,
                    name,
                    column,
                    position + 1,
                )
                raise ConversionError(f"Non-string value in {name}, column {column}")

    context.logger.debug("Output schema of %s validated (%d columns).", name, len(columns))
