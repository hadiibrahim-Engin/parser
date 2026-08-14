"""Gemeinsame Datenstrukturen der Transformationsschritte."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from excelToCsv.issues import IssueCollector
from excelToCsv.relevance import RelevanceColumn


@dataclass(slots=True)
class RowSet:
    """Eine Teilmenge der Inputzeilen samt vorberechnetem Zeilenkontext.

    Zeilennummer, ELEMENT ID und ELEMENT-TYPE werden einmal berechnet und
    weitergereicht, damit jede Fehlermeldung ohne erneutes Nachschlagen
    vollständig ist.
    """

    frame: pd.DataFrame
    rowNumbers: np.ndarray
    elementIds: np.ndarray
    elementTypes: np.ndarray

    def __len__(self) -> int:
        return len(self.frame)

    def context(self, position: int) -> dict[str, object]:
        """Liefert den Log-Kontext (Zeile, ID, Typ) für eine Position."""
        return {
            "row": int(self.rowNumbers[position]),
            "elementId": self.elementIds[position],
            "elementType": self.elementTypes[position],
        }


@dataclass(slots=True)
class ConversionContext:
    """Querschnittsobjekte, die alle Transformationsschritte benötigen."""

    relevanceColumns: list[RelevanceColumn]
    collector: IssueCollector
    logger: logging.Logger


def subsetRows(rows: RowSet, mask: np.ndarray) -> RowSet:
    """Schneidet eine Teilmenge aus einem ``RowSet`` heraus (Maske über Zeilen)."""
    return RowSet(
        frame=rows.frame.loc[mask].reset_index(drop=True),
        rowNumbers=rows.rowNumbers[mask],
        elementIds=rows.elementIds[mask],
        elementTypes=rows.elementTypes[mask],
    )


def emptyColumn(rowCount: int) -> np.ndarray:
    """Erzeugt eine Spalte aus leeren Strings (Felder ohne definierte Quelle)."""
    return np.full(rowCount, "", dtype=object)
