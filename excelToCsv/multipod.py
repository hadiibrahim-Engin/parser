"""Infer three-legged circuit topology from grouped station references."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from excelToCsv.context import ConversionContext, RowSet
from excelToCsv.normalize import normalizeElementType, normalizeVoltage
from excelToCsv.reader import InputTable, columnValues, textColumn
from excelToCsv.schema import (
    COL_ELEMENT_ID, COL_ELEMENT_TYPE, COL_MULTIPOD,
    COL_STATION_1, COL_STATION_2, COL_VOLTAGE_LEVEL,
    MULTIPOD_ELEMENT_TYPES, STATION_TYPE,
)


@dataclass(frozen=True, slots=True)
class MultipodGroup:
    """Validated topology in Excel order; the group ID need not name a station."""

    identifier: str
    sourceRows: tuple[int, ...]
    nodeId: str
    outerStationIds: tuple[str, ...]


def findMultipodSummaryRows(table: InputTable) -> set[int]:
    """Identify redundant circuit rows before validating missing endpoints.

    A summary's ELEMENT ID matches the Multipod ID declared by other line
    legs. SUB rows are stations, never summaries. A connected member is kept
    when it could be one of the three legs; three other legs must exist before
    a connected row can be considered redundant. Group validation is separate:
    defective or incomplete legs still produce their own findings.
    """
    pods = textColumn(table.frame, COL_MULTIPOD)
    if not any(pods):
        return set()
    types = [normalizeElementType(value)
             for value in columnValues(table.frame, COL_ELEMENT_TYPE)]
    ids = textColumn(table.frame, COL_ELEMENT_ID)
    legCounts = Counter(
        pod for kind, identifier, pod in zip(types, ids, pods)
        if kind in MULTIPOD_ELEMENT_TYPES and pod and identifier != pod
    )
    if not legCounts:
        return set()
    starts = textColumn(table.frame, COL_STATION_1)
    ends = textColumn(table.frame, COL_STATION_2)
    return {
        int(table.rowNumbers[position])
        for position, identifier in enumerate(ids)
        if types[position] != STATION_TYPE
        and identifier in legCounts
        and pods[position] in ('', identifier)
        and ((not starts[position] and not ends[position]) or legCounts[identifier] >= 3)
    }


def detectMultipodGroups(
    rows: RowSet,
    context: ConversionContext,
    stationIds: set[str],
) -> list[MultipodGroup]:
    """Group only by Multipod; derive the virtual node from the three edges.

    A valid star has four distinct stations: one occurs in every edge, and the
    other three occur once each. Neither the group ID nor a station prefix
    participates in node detection. Report every row of an invalid group.
    """
    positionsById: dict[str, list[int]] = {}
    for position, identifier in enumerate(textColumn(rows.frame, COL_MULTIPOD)):
        if identifier:
            positionsById.setdefault(identifier, []).append(position)
    if not positionsById:
        return []

    starts = textColumn(rows.frame, COL_STATION_1)
    ends = textColumn(rows.frame, COL_STATION_2)
    voltages = columnValues(rows.frame, COL_VOLTAGE_LEVEL)
    groups = []
    for identifier, positions in positionsById.items():
        edges = [(starts[p], ends[p]) for p in positions]
        counts = Counter(station for edge in edges for station in edge)
        nodes = [station for station, count in counts.items() if count == 3]
        valid = (
            len(positions) == 3
            and len(counts) == 4
            and len(nodes) == 1
            and sorted(counts.values()) == [1, 1, 1, 3]
            and all(first and second and first != second for first, second in edges)
            and set(counts) <= stationIds
            and len({rows.elementTypes[p] for p in positions}) == 1
            and rows.elementTypes[positions[0]] in MULTIPOD_ELEMENT_TYPES
            and len({normalizeVoltage(voltages[p]) for p in positions}) == 1
        )
        if not valid:
            for position in positions:
                context.collector.error(
                    "Multipod must describe exactly three unambiguous line legs.",
                    field=COL_MULTIPOD,
                    value=identifier,
                    expected=(
                        "Exactly three LINE/TIE/DCL rows of the same type and voltage "
                        "must share this group ID. Their Station 1 / Station 2 references "
                        "must form three distinct outer SUB stations connected to one "
                        "common SUB node. The node name and group ID are independent."
                    ),
                    **rows.context(position),
                )
            continue

        node = nodes[0]
        groups.append(MultipodGroup(
            identifier=identifier,
            sourceRows=tuple(int(rows.rowNumbers[p]) for p in positions),
            nodeId=node,
            outerStationIds=tuple(second if first == node else first
                                  for first, second in edges),
        ))
    return groups
