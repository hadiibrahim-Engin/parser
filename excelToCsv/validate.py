"""All validations that reach beyond a single cell.

Deliberately separated from the transformation: first every record is built,
then everything is checked, and only afterwards may anything be written.
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
    """Report every unknown ``ELEMENT-TYPE`` as a fatal error."""
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
    """Build the ``ELEMENT ID -> Excel row`` index over all ``SUB`` rows.

    Duplicate station ids are not silently overwritten but reported as a fatal
    error naming every affected row.
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
    """Check duplicate network element ids.

    Fully identical records are tolerable (``WARNING``); conflicting records
    sharing an id are fatal.
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
    """Check that every populated station reference points at a ``SUB`` row."""
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
    """Check target columns, their order and the absence of NA values.

    Raises:
        ConversionError: On any deviation from the agreed output contract.
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
