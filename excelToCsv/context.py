"""Data structures shared by the transformation steps."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from excelToCsv.issues import IssueCollector
from excelToCsv.normalize import buildMjapId
from excelToCsv.reader import textColumn
from excelToCsv.relevance import RelevanceColumn
from excelToCsv.schema import COL_ELEMENT_ID, COL_TSO


@dataclass(slots=True)
class RowSet:
    """A subset of the input rows plus pre-computed row context.

    Row number, ELEMENT ID and ELEMENT-TYPE are computed once and passed along,
    so every message is complete without another lookup.
    """

    frame: pd.DataFrame
    rowNumbers: np.ndarray
    elementIds: np.ndarray
    elementTypes: np.ndarray

    def __len__(self) -> int:
        return len(self.frame)

    def context(self, position: int) -> dict[str, object]:
        """Return the log context (row, id, type) for one position."""
        return {
            "row": int(self.rowNumbers[position]),
            "elementId": self.elementIds[position],
            "elementType": self.elementTypes[position],
        }


@dataclass(slots=True)
class ConversionContext:
    """Cross-cutting objects that every transformation step needs."""

    relevanceColumns: list[RelevanceColumn]
    collector: IssueCollector
    logger: logging.Logger
    lifecycleDates: tuple[str, str] | None = None


def subsetRows(rows: RowSet, mask: np.ndarray) -> RowSet:
    """Cut a subset out of a ``RowSet`` using a row mask."""
    return RowSet(
        frame=rows.frame.loc[mask].reset_index(drop=True),
        rowNumbers=rows.rowNumbers[mask],
        elementIds=rows.elementIds[mask],
        elementTypes=rows.elementTypes[mask],
    )


def groupPositions(values: Iterable[str]) -> dict[str, list[int]]:
    """Map every non-empty value to the positions it occurs at, in first-seen order."""
    positionsByValue: dict[str, list[int]] = {}
    for position, value in enumerate(values):
        if value:
            positionsByValue.setdefault(value, []).append(position)
    return positionsByValue


def ownerMjapIds(
    rows: RowSet,
    context: ConversionContext,
    subject: str,
    expectedId: str,
    expectedOwner: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Return the TSO owners and ``<owner>_<ELEMENT ID>`` MJAP-IDs of ``rows``.

    Reports every row missing its ELEMENT ID or owner; ``subject`` names the
    record kind in the message ("Station", "Network element").
    """
    owners = textColumn(rows.frame, COL_TSO)
    mjapIds = np.fromiter(
        (buildMjapId(owner, elementId)
         for owner, elementId in zip(owners, rows.elementIds, strict=True)),
        dtype=object,
        count=len(rows),
    )
    for position, elementId in enumerate(rows.elementIds):
        if not elementId:
            context.collector.error(
                f"{subject} is missing its identifier.",
                field=COL_ELEMENT_ID,
                value=None,
                expected=expectedId,
                **rows.context(position),
            )
        if not owners[position]:
            context.collector.error(
                f"{subject} is missing the owner required for its MJAP-ID.",
                field=COL_TSO,
                value=None,
                expected=expectedOwner,
                **rows.context(position),
            )
    return owners, mjapIds


def emptyColumn(rowCount: int) -> np.ndarray:
    """Build a column of empty strings (fields without a defined source)."""
    return np.full(rowCount, "", dtype=object)
