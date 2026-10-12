"""Find tripods (Multipods) and the virtual node at their centre.

In Excel a tripod is four rows:

    MP1   (name row: no Multipod, no stations)
    L1    Multipod = MP1   Station 1 / Station 2 = XK / A
    L2    Multipod = MP1   Station 1 / Station 2 = XK / B
    L3    Multipod = MP1   Station 1 / Station 2 = XK / C

The station shared by all three legs (XK) is the virtual node; A, B and C are
the real outer stations, in the order of the legs.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from excelToCsv.issues import IssueCollector
from excelToCsv.reader import InputRow
from excelToCsv.schema import COL_MULTIPOD, COL_STATION_1, COL_STATION_2


@dataclass(frozen=True, slots=True)
class Tripod:
    nameRow: InputRow
    legs: tuple[InputRow, InputRow, InputRow]
    node: str
    outerStations: tuple[str, str, str]


def findTripods(rows: list[InputRow], collector: IssueCollector) -> tuple[list[Tripod], set[int]]:
    """Return the valid tripods and the Excel rows of every Multipod group.

    Rows of an invalid group are reported and also returned, so they are not
    exported as ordinary lines.
    """
    legsByPod: dict[str, list[InputRow]] = {}
    for row in rows:
        pod = row.text(COL_MULTIPOD)
        if pod and row.elementId != pod:
            legsByPod.setdefault(pod, []).append(row)
    rowsById = {row.elementId: row for row in rows}

    tripods: list[Tripod] = []
    groupRows: set[int] = set()
    for pod, legs in legsByPod.items():
        nameRow = rowsById.get(pod)
        groupRows.update(row.number for row in legs)
        if nameRow is not None:
            groupRows.add(nameRow.number)
        tripod = _buildTripod(nameRow, legs)
        if isinstance(tripod, Tripod):
            tripods.append(tripod)
            continue
        for row in legs if nameRow is None else [nameRow, *legs]:
            collector.error(tripod, field=COL_MULTIPOD, value=pod,
                            expected="One name row (ELEMENT ID = Multipod value) and three legs "
                                     "that share one station and end at three different stations.",
                            **row.context())
    return tripods, groupRows


def _buildTripod(nameRow: InputRow | None, legs: list[InputRow]) -> Tripod | str:
    """The tripod described by these rows, or the problem that prevents it."""
    if nameRow is None:
        return "Tripod name row is missing: no row has this Multipod value as ELEMENT ID."
    if len(legs) != 3:
        return f"A tripod needs exactly 3 legs, found {len(legs)}."
    ends = [(leg.text(COL_STATION_1), leg.text(COL_STATION_2)) for leg in legs]
    if not all(first and second and first != second for first, second in ends):
        return "Every tripod leg needs two different stations in Station 1 and Station 2."
    counts = Counter(station for pair in ends for station in pair)
    nodes = [station for station, count in counts.items() if count == 3]
    if len(nodes) != 1 or len(counts) != 4:
        return "The 3 legs must share exactly one station (the virtual node) and end at 3 different stations."
    node = nodes[0]
    outer = tuple(second if first == node else first for first, second in ends)
    return Tripod(nameRow=nameRow, legs=(legs[0], legs[1], legs[2]), node=node, outerStations=outer)
