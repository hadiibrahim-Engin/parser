"""Data structures shared by the transformation steps."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from excelToCsv.issues import IssueCollector
from excelToCsv.relevance import RelevanceColumn


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


def subsetRows(rows: RowSet, mask: np.ndarray) -> RowSet:
    """Cut a subset out of a ``RowSet`` using a row mask."""
    return RowSet(
        frame=rows.frame.loc[mask].reset_index(drop=True),
        rowNumbers=rows.rowNumbers[mask],
        elementIds=rows.elementIds[mask],
        elementTypes=rows.elementTypes[mask],
    )


def emptyColumn(rowCount: int) -> np.ndarray:
    """Build a column of empty strings (fields without a defined source)."""
    return np.full(rowCount, "", dtype=object)
