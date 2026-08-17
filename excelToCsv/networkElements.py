"""Transformation of all non-``SUB`` rows into ``Netzelemente.csv``."""

from __future__ import annotations

import numpy as np
import pandas as pd

from excelToCsv.context import ConversionContext, RowSet, emptyColumn
from excelToCsv.normalize import buildMjapId, normalizeDate, normalizeVoltage
from excelToCsv.reader import applyNormalizer, columnValues, textColumn
from excelToCsv.relevance import buildRelevantFor
from excelToCsv.schema import (
    BOTH_STATIONS_REQUIRED,
    COL_ELEMENT_ID,
    COL_ENDLIFETIME,
    COL_LONG_NAME,
    COL_MULTIPOD,
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


def findElementsWithoutStations(rows: RowSet, context: ConversionContext) -> np.ndarray:
    """Mark the network elements that carry no usable station reference.

    A network element without the stations it connects cannot be placed in the
    grid, so it is reported as a ``WARNING`` - it lands in the issue report - and
    removed from the output instead of being written incomplete.

    Two cases count as "no stations":

    * a mandatory type (LINE/TRA/TIE/DCL) missing either reference,
    * any other type missing **both** references.

    An optional type that still has one station is kept; the missing side keeps
    the literal ``NaN`` as before.

    Returns:
        Boolean mask of the rows to keep.
    """
    first = textColumn(rows.frame, COL_STATION_1)
    second = textColumn(rows.frame, COL_STATION_2)

    keep = np.ones(len(rows), dtype=bool)
    for position in range(len(rows)):
        elementType = rows.elementTypes[position]
        mandatory = elementType in BOTH_STATIONS_REQUIRED
        missing = [
            column
            for column, value in ((COL_STATION_1, first[position]), (COL_STATION_2, second[position]))
            if not value
        ]
        if not missing or (not mandatory and len(missing) < 2):
            continue

        keep[position] = False
        context.collector.warning(
            "Network element has no usable station reference.",
            field=", ".join(missing),
            value=None,
            expected=(
                f"{elementType} requires {COL_STATION_1} and {COL_STATION_2}."
                if mandatory
                else f"{elementType} requires at least one of "
                f"{COL_STATION_1} / {COL_STATION_2}."
            ),
            action="Removing the element from the output and continuing.",
            **rows.context(position),
        )
    return keep


def resolveStationReferences(
    rows: RowSet,
    column: str,
    context: ConversionContext,
) -> np.ndarray:
    """Determine the raw station reference per row.

    Rows without a usable reference are already gone at this point; what remains
    is an optional type that legitimately omits one side, which keeps the literal
    ``NaN``. The existence of a populated reference is checked later in
    :mod:`excelToCsv.validate`.
    """
    values = textColumn(rows.frame, column)
    result = np.empty(len(values), dtype=object)
    for position, value in enumerate(values):
        if value:
            result[position] = value
            continue
        elementType = rows.elementTypes[position]
        result[position] = MISSING_STATION_LITERAL
        context.collector.warning(
            "Station reference is missing.",
            field=column,
            value=None,
            expected=f"{elementType} may omit one of the two station references.",
            action=f"Writing {MISSING_STATION_LITERAL} and continuing.",
            **rows.context(position),
        )
    return result


def stationReferenceMjapIds(
    references: np.ndarray,
    stationMjapByElementId: dict[str, str],
) -> np.ndarray:
    """Resolve station ELEMENT IDs to their ``<owner>_<ELEMENT ID>`` MJAP-IDs."""
    return np.fromiter(
        (
            MISSING_STATION_LITERAL
            if reference == MISSING_STATION_LITERAL
            else stationMjapByElementId.get(reference, "")
            for reference in references
        ),
        dtype=object,
        count=len(references),
    )


def multipodMjapIds(
    multipods: np.ndarray,
    stationMjapByElementId: dict[str, str],
) -> np.ndarray:
    """Resolve multipod references to the MJAP-ID of the virtual station.

    Mirrors :func:`stationReferenceMjapIds`: the plain column keeps the
    referenced ``ELEMENT ID``, the ``:MJAP-ID`` column carries the resolved
    ``<owner>_<ELEMENT ID>``. An empty reference stays empty; an unresolvable
    one is already a fatal error raised by the validation step.
    """
    return np.fromiter(
        (
            stationMjapByElementId.get(reference, "") if reference else ""
            for reference in multipods
        ),
        dtype=object,
        count=len(multipods),
    )


def convertNetworkElements(
    rows: RowSet,
    context: ConversionContext,
    stationMjapByElementId: dict[str, str],
) -> pd.DataFrame:
    """Build the network element records.

    Expects ``rows`` to be free of elements without a usable station reference -
    the pipeline removes those beforehand so the validations that follow see the
    same set of rows as the output.
    """
    rowCount = len(rows)
    context.logger.info("Found %d network element(s).", rowCount)

    owners = textColumn(rows.frame, COL_TSO)
    ucteCodes = textColumn(rows.frame, COL_UCTE_CODE)
    mjapIds = np.fromiter(
        (
            buildMjapId(owner, elementId)
            for owner, elementId in zip(owners, rows.elementIds, strict=True)
        ),
        dtype=object,
        count=rowCount,
    )
    for position, elementId in enumerate(rows.elementIds):
        if not elementId:
            context.collector.error(
                "Network element is missing its identifier.",
                field=COL_ELEMENT_ID,
                value=None,
                expected="Every network element row requires a non-empty ELEMENT ID.",
                **rows.context(position),
            )
        if not owners[position]:
            context.collector.error(
                "Network element is missing the owner required for its MJAP-ID.",
                field=COL_TSO,
                value=None,
                expected=(
                    "Every network element requires a non-empty TSO value for "
                    "<owner>_<ELEMENT ID>."
                ),
                **rows.context(position),
            )

    stationStart = resolveStationReferences(rows, COL_STATION_1, context)
    stationEnd = resolveStationReferences(rows, COL_STATION_2, context)
    stationStartMjap = stationReferenceMjapIds(stationStart, stationMjapByElementId)
    stationEndMjap = stationReferenceMjapIds(stationEnd, stationMjapByElementId)

    # A populated Multipod names the virtual station shared by the legs of a
    # three-legged line. The legs stay separate records - the reference is only
    # carried into the Y node columns.
    multipods = textColumn(rows.frame, COL_MULTIPOD)
    multipodMjap = multipodMjapIds(multipods, stationMjapByElementId)

    voltages = np.fromiter(
        (normalizeVoltage(value) for value in columnValues(rows.frame, COL_VOLTAGE_LEVEL)),
        dtype=object,
        count=rowCount,
    )
    longNames = textColumn(rows.frame, COL_LONG_NAME)

    data = {
        "Eigentümer": owners,
        "MJAP-ID": mjapIds,
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
        "Station Anfang": stationStartMjap,
        "Station Ende": stationEndMjap,
        "Station T-1": emptyColumn(rowCount),
        "Station T-2": emptyColumn(rowCount),
        "Y-Knoten-1": multipods,
        "Y-Knoten-2": emptyColumn(rowCount),
        "Stromkreisname - Kurzname": longNames,
        "Stromkreisname - OPC-Name": emptyColumn(rowCount),
        "ID-GUID intern-1": emptyColumn(rowCount),
        "ID-GUID intern-2": emptyColumn(rowCount),
        "ID-OPC": emptyColumn(rowCount),
        "ID-UCTE": ucteCodes,
        "ID": emptyColumn(rowCount),
        "Station Anfang:MJAP-ID": stationStartMjap,
        "Station Ende:MJAP-ID": stationEndMjap,
        "Station T-1:MJAP-ID": emptyColumn(rowCount),
        "Station T-2:MJAP-ID": emptyColumn(rowCount),
        "Y-Knoten-1: MJAP-ID": multipodMjap,
        "Y-Knoten-2: MJAP-ID": emptyColumn(rowCount),
    }
    return pd.DataFrame(data, columns=list(NETWORK_ELEMENT_COLUMNS), dtype=object)
